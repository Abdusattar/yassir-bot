"""Вход в YassirApp по почте - запасная дверь, когда Telegram не пускает
(07.10.2026, wiki/login_without_telegram.md, этап 1).

Повод. Telegram в части случаев просит деньги за вход на новом телефоне
(первым попался Саламат, устаз G2C: сменил айфон - «купи Premium»). Сам
человек у нас уже есть, учится, просто войти ему нечем. Поэтому почта здесь
не регистрация, а ВТОРОЙ ключ к уже существующему аккаунту: строка
«почта -> Telegram ID + половина». Вся остальная авторизация не меняется -
сессия выдаётся той же web_auth, по тому же users.phone.

Как устроено.
  1. Привязка: супер-админ (scripts/link_email.py) - для застрявших, позже
     сам студент из настроек.
  2. Браузер шлёт адрес -> на него уходит код из 6 цифр (живёт 15 минут,
     5 попыток, в базе только sha256).
  3. Верный код -> обычный код входа web_auth, подтверждённый для половины
     человека. Дальше вкладка забирает сессию тем же /auth/poll, что и после
     Telegram - второй путь выдачи сессий не заводим.

Где лежит. Общая sources/hadiths.db, как и коды входа: на сайте человек не
выбирает половину, письмо шлёт мужской процесс, а сессию выдаст тот, где
человек учится (см. web_auth о разделении по полу).
"""
import hashlib
import logging
import re
import secrets
import sqlite3

import core.sampler as sampler   # HADITHS_DB через модуль: тесты подменяют путь там
from core.db import get_now
from core.web_auth import claim_login_code, new_login_code

log = logging.getLogger(__name__)

CODE_TTL_MINUTES = 15
# 6 цифр и 5 попыток: шанс угадать - 1 к 200 000 на письмо. Писем на адрес
# не больше MAX_SENDS_PER_HOUR, так что перебор упирается в почтовый ящик.
MAX_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 5

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _shared:
    """Соединение с общей базой, повадка как у web_auth._codes."""
    def __enter__(self):
        self.c = sqlite3.connect(str(sampler.HADITHS_DB), timeout=5)
        self.c.row_factory = sqlite3.Row
        self.c.executescript("""
            CREATE TABLE IF NOT EXISTS login_emails(
                email TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                added_at TEXT,
                added_by TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_login_emails_user
                ON login_emails(user_id, profile);
            CREATE TABLE IF NOT EXISTS email_login_codes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                created_at TEXT,
                attempts INTEGER DEFAULT 0,
                used INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_email_login_codes_email
                ON email_login_codes(email);
        """)
        return self.c

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.c.commit()
        self.c.close()
        return False


def _now_iso():
    return get_now().strftime("%Y-%m-%d %H:%M:%S")


def _hash(email, code):
    # Адрес в соли: один и тот же код у двух людей даёт разные хеши.
    return hashlib.sha256(("%s:%s" % (email, code)).encode()).hexdigest()


def normalize_email(email):
    """Нижний регистр и без пробелов по краям. None - если на адрес не похоже.
    Точки и плюсы в Gmail не трогаем: у mail.ru и прочих они значимы."""
    e = (email or "").strip().lower()
    if len(e) > 200 or not _EMAIL_RE.match(e):
        return None
    return e


# ── Привязка ──────────────────────────────────────────────────────────────────

def link_email(email, user_id, profile, added_by=""):
    """Привязать почту к человеку. Одна почта - один человек: перепривязка
    чужой почты молча не делается, ValueError('email_taken')."""
    e = normalize_email(email)
    if not e:
        raise ValueError("email_bad")
    with _shared() as c:
        row = c.execute("SELECT user_id, profile FROM login_emails WHERE email=?",
                        (e,)).fetchone()
        if row and (row["user_id"], row["profile"]) != (str(user_id), profile):
            raise ValueError("email_taken")
        c.execute("INSERT OR REPLACE INTO login_emails(email, user_id, profile, added_at, added_by)"
                  " VALUES(?,?,?,?,?)", (e, str(user_id), profile, _now_iso(), str(added_by)))
    return e


def unlink_email(email):
    e = normalize_email(email)
    with _shared() as c:
        return c.execute("DELETE FROM login_emails WHERE email=?", (e,)).rowcount > 0


def emails_of(user_id, profile):
    with _shared() as c:
        return [r["email"] for r in c.execute(
            "SELECT email FROM login_emails WHERE user_id=? AND profile=? ORDER BY added_at",
            (str(user_id), profile))]


def owner_of(email):
    """(user_id, profile) или None."""
    e = normalize_email(email)
    if not e:
        return None
    with _shared() as c:
        row = c.execute("SELECT user_id, profile FROM login_emails WHERE email=?",
                        (e,)).fetchone()
    return (row["user_id"], row["profile"]) if row else None


# ── Коды ──────────────────────────────────────────────────────────────────────

def issue_code(email):
    """Новый код для привязанной почты. Возвращает (код, None) или
    (None, причина): 'email_bad' | 'not_linked' | 'too_many'.
    Прежние неиспользованные коды этого адреса гасятся: действует последнее
    письмо - так человек не запутается, какое из двух вводить."""
    e = normalize_email(email)
    if not e:
        return None, "email_bad"
    if owner_of(e) is None:
        return None, "not_linked"
    now = _now_iso()
    with _shared() as c:
        sent = c.execute(
            "SELECT COUNT(*) FROM email_login_codes WHERE email=? AND created_at >= datetime(?, '-1 hour')",
            (e, now)).fetchone()[0]
        if sent >= MAX_SENDS_PER_HOUR:
            return None, "too_many"
        code = "%06d" % secrets.randbelow(1_000_000)
        c.execute("UPDATE email_login_codes SET used=1 WHERE email=? AND used=0", (e,))
        c.execute("INSERT INTO email_login_codes(email, code_hash, created_at) VALUES(?,?,?)",
                  (e, _hash(e, code), now))
        # Уборка заодно, как в web_auth.new_login_code.
        c.execute("DELETE FROM email_login_codes WHERE created_at < datetime(?, '-1 day')", (now,))
    return code, None


def check_code(email, code):
    """Проверить код из письма. Верный -> код входа web_auth, уже
    подтверждённый для половины человека: (login_code, profile, None).
    Неверный -> (None, None, причина): 'wrong' | 'expired' | 'not_linked'."""
    e = normalize_email(email)
    code = re.sub(r"\D", "", code or "")
    owner = owner_of(e) if e else None
    if owner is None:
        return None, None, "not_linked"
    now = _now_iso()
    with _shared() as c:
        row = c.execute(
            "SELECT id, code_hash, attempts FROM email_login_codes"
            " WHERE email=? AND used=0 AND created_at >= datetime(?, ?)"
            " ORDER BY id DESC LIMIT 1",
            (e, now, "-%d minutes" % CODE_TTL_MINUTES)).fetchone()
        if row is None or row["attempts"] >= MAX_ATTEMPTS:
            return None, None, "expired"
        if not secrets.compare_digest(row["code_hash"], _hash(e, code)):
            c.execute("UPDATE email_login_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            left = MAX_ATTEMPTS - row["attempts"] - 1
            return None, None, ("wrong" if left > 0 else "expired")
        c.execute("UPDATE email_login_codes SET used=1 WHERE id=?", (row["id"],))
    user_id, profile = owner
    login_code = new_login_code()
    claim_login_code(login_code, user_id, profile)
    log.info("email login: %s -> %s/%s", e, profile, user_id)
    return login_code, profile, None
