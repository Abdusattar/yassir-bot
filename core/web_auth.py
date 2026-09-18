"""Собственный вход в YassirApp — для тех, кто открывает приложение как сайт
(yassirilm.com), а не как Telegram Mini App (10.09.2026).

Зачем отдельный вход. Вся авторизация приложения до сих пор держалась на
Telegram initData (см. mufradat_api.validate_init_data): вне Telegram её нет
вообще, и все 31 эндпоинт отвечают 401. Телефон+SMS не годится — настоящих
номеров у нас нет (users.phone это Telegram ID, см. wiki/infrastructure.md),
а собирать их заново значит лишний экран и лишняя точка отказа.

Как устроено. Браузер просит код, открывает t.me/<бот>?start=login_<код>,
человек жмёт «Начать» — бот его уже знает по Telegram ID и подтверждает код.
Браузер тем временем опрашивает /auth/poll и в момент подтверждения получает
токен сессии. Ни телефона, ни SMS, ни пароля: удостоверяет личность сам
Telegram, как и раньше, просто один раз, а не при каждом запросе.

Где что лежит. СЕССИИ - в профильной базе (quran_male.db / quran_female.db):
токен, выданный мужским процессом, женский в своей базе не найдёт, и это
держит разделение по полу таким же жёстким, каким его делала подпись initData
токеном конкретного бота. А КОДЫ ВХОДА с 18.09.2026 живут в общей
sources/hadiths.db с пометкой профиля. Причина: на сайте больше нет кнопок
«мужская/женская» - человек не должен выбирать сторону сам (решение
пользователя, после того как сестра открыла приложение через мужской бот).
Ссылка ведёт в мужской бот; тот ищет человека у себя, потом у соседа
(core/db.py:other_bot_member) и подтверждает код ДЛЯ ТОГО профиля, где
человек учится. Вкладка узнаёт профиль из /auth/poll, переспрашивает уже
женский процесс, и тот выдаёт сессию из СВОЕЙ базы. Сосед в чужую базу не
пишет никогда - только в общую таблицу кодов.

Токен наружу отдаётся ОДИН раз, в базе лежит только его sha256 — утечка базы
не даёт войти ни за кого.
"""
import hashlib
import logging
import secrets
import sqlite3

import config
import core.sampler as sampler   # HADITHS_DB через модуль: тесты подменяют путь там
from core.db import db, get_now

log = logging.getLogger(__name__)

# Код живёт до подтверждения. Достаточно, чтобы человек успел переключиться в
# Telegram и нажать «Начать», и мало, чтобы забытый в чужой истории код был
# бесполезен.
LOGIN_CODE_TTL_MINUTES = 15

# Сессия долгая осознанно: вход стоит человеку переключения в Telegram, и
# заставлять его повторять это каждую неделю значит вернуть трение, ради
# избавления от которого всё и делается. Плюс iOS чистит хранилище у редко
# открываемых сайтов — короткая сессия выкидывала бы как раз тех, кто
# заходит нечасто.
SESSION_TTL_DAYS = 90

# Приставка к /start в deep-link. Совпадает с core/handlers.py.
LOGIN_START_PREFIX = "login_"


def init_web_auth():
    """Идемпотентно, зовётся из core.db.init() — как остальные наши таблицы.
    Старая web_login_codes в профильной базе (до 18.09.2026) не трогается и
    не читается - коды теперь в общей базе, см. _codes."""
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS web_sessions(
                token_hash TEXT PRIMARY KEY,
                user_id TEXT,
                created_at TEXT,
                last_seen TEXT,
                expires_at TEXT,
                user_agent TEXT,
                revoked INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_web_sessions_user
                ON web_sessions(user_id);
        """)


class _codes:
    """Соединение с общей базой кодов входа (sources/hadiths.db) - контекст с
    той же повадкой, что core.db.db(): Row, commit на выходе. Таблица
    создаётся на месте: отдельного init у общей базы нет (банк насых и след
    приложения делают так же)."""
    def __enter__(self):
        self.c = sqlite3.connect(str(sampler.HADITHS_DB), timeout=5)
        self.c.row_factory = sqlite3.Row
        self.c.execute("""
            CREATE TABLE IF NOT EXISTS web_login_codes(
                code TEXT PRIMARY KEY,
                created_at TEXT,
                user_id TEXT,
                profile TEXT,
                claimed_at TEXT,
                taken INTEGER DEFAULT 0,
                refused INTEGER DEFAULT 0
            )
        """)
        return self.c

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.c.commit()
        self.c.close()
        return False


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _now_iso():
    return get_now().strftime("%Y-%m-%d %H:%M:%S")


# ── Коды входа ────────────────────────────────────────────────────────────────

def new_login_code():
    """Секрет, который знает только этот браузер. 128 бит: перебрать за 15
    минут нельзя, а в start-параметр Telegram (64 знака, [A-Za-z0-9_-]) он
    влезает с запасом."""
    code = secrets.token_urlsafe(16)
    with _codes() as c:
        c.execute("INSERT INTO web_login_codes(code, created_at) VALUES(?,?)",
                  (code, _now_iso()))
        # Заодно подметаем протухшие — отдельная уборка ради этой таблицы не нужна.
        c.execute(
            "DELETE FROM web_login_codes "
            "WHERE created_at < datetime(?, ?)",
            (_now_iso(), f"-{LOGIN_CODE_TTL_MINUTES * 4} minutes"),
        )
    return code


def claim_login_code(code, user_id, profile=None):
    """Бот подтвердил вход. Возвращает True, если код был живой и свободный.

    profile - в базе какого бота человек учится, то есть какой процесс выдаст
    сессию. По умолчанию свой; мужской бот, нашедший сестру у соседа,
    передаёт сюда «female» (core/handlers.py), и код заберёт женский процесс.

    Повторное подтверждение того же кода (человек нажал ссылку дважды) — не
    ошибка, но и не переприсвоение: код уже привязан к первому, кто его занял.
    """
    if not code or not user_id:
        return False
    profile = profile or config.PROFILE
    with _codes() as c:
        row = c.execute(
            "SELECT user_id FROM web_login_codes "
            "WHERE code=? AND created_at >= datetime(?, ?)",
            (code, _now_iso(), f"-{LOGIN_CODE_TTL_MINUTES} minutes"),
        ).fetchone()
        if row is None:
            return False
        if row["user_id"]:
            return row["user_id"] == str(user_id)
        c.execute("UPDATE web_login_codes SET user_id=?, profile=?, claimed_at=? WHERE code=?",
                  (str(user_id), profile, _now_iso(), code))
        return True


def refuse_login_code(code):
    """Бот узнал код, но человека в СВОИХ группах не нашёл — почти всегда это
    значит, что он выбрал не ту сторону (мужскую вместо женской).

    Бот скажет ему об этом в Telegram, но вкладка в браузере в это время
    молча ждёт подтверждения, и человек может не догадаться, что надо
    вернуться и выбрать заново. Поэтому отказ помечается здесь и доезжает до
    вкладки следующим же опросом."""
    if not code:
        return
    with _codes() as c:
        c.execute(
            "UPDATE web_login_codes SET refused=1 "
            "WHERE code=? AND user_id IS NULL",
            (code,),
        )


def poll_login_code(code):
    """Что показать вкладке: 'refused' — не та сторона, None — ещё ждём."""
    if not code:
        return None
    with _codes() as c:
        row = c.execute(
            "SELECT refused FROM web_login_codes WHERE code=?", (code,)
        ).fetchone()
    if row is not None and row["refused"]:
        return "refused"
    return None


def login_code_profile(code):
    """Для какого бота код подтверждён: 'male' / 'female', либо None, пока не
    подтверждён. Вкладка сравнивает с процессом, который опрашивает, и при
    несовпадении переспрашивает соседа (см. handle_auth_poll)."""
    if not code:
        return None
    with _codes() as c:
        row = c.execute(
            "SELECT profile FROM web_login_codes WHERE code=? AND user_id IS NOT NULL",
            (code,),
        ).fetchone()
    return row["profile"] if row else None


def take_session_for_code(code, user_agent=""):
    """Опрос из браузера. Пока код не подтверждён — None. В момент, когда бот
    его подтвердил, ОДИН раз отдаёт свежий токен и гасит код: второй опрос с
    тем же кодом (чужая вкладка, история браузера) уже ничего не получит."""
    if not code:
        return None
    with _codes() as c:
        row = c.execute(
            "SELECT user_id, taken, profile FROM web_login_codes WHERE code=?", (code,)
        ).fetchone()
        if row is None or not row["user_id"] or row["taken"]:
            return None
        # Код подтверждён для соседа - сессию выдаст он, из своей базы.
        if row["profile"] and row["profile"] != config.PROFILE:
            return None
        c.execute("UPDATE web_login_codes SET taken=1 WHERE code=?", (code,))
        user_id = row["user_id"]
    return _create_session(user_id, user_agent), user_id


# ── Сессии ────────────────────────────────────────────────────────────────────

def _create_session(user_id, user_agent=""):
    token = secrets.token_urlsafe(32)
    now = _now_iso()
    with db() as c:
        c.execute(
            "INSERT INTO web_sessions(token_hash, user_id, created_at, last_seen,"
            " expires_at, user_agent) VALUES(?,?,?,?,datetime(?, ?),?)",
            (_hash(token), str(user_id), now, now, now,
             f"+{SESSION_TTL_DAYS} days", (user_agent or "")[:200]),
        )
    return token


def resolve_session(token):
    """Токен → user_id, либо None. Скользящее продление: пока человек
    заходит, срок отодвигается, и активный студент не выпадает никогда.
    last_seen пишем не чаще раза в сутки — иначе каждый запрос приложения
    (heartbeat раз в 20 секунд) был бы записью в базу."""
    if not token:
        return None
    h = _hash(token)
    with db() as c:
        row = c.execute(
            "SELECT user_id, last_seen FROM web_sessions "
            "WHERE token_hash=? AND revoked=0 AND expires_at > ?",
            (h, _now_iso()),
        ).fetchone()
        if row is None:
            return None
        if not row["last_seen"] or row["last_seen"][:10] != _now_iso()[:10]:
            c.execute(
                "UPDATE web_sessions SET last_seen=?, expires_at=datetime(?, ?) "
                "WHERE token_hash=?",
                (_now_iso(), _now_iso(), f"+{SESSION_TTL_DAYS} days", h),
            )
        return row["user_id"]


def revoke_session(token):
    if not token:
        return
    with db() as c:
        c.execute("UPDATE web_sessions SET revoked=1 WHERE token_hash=?", (_hash(token),))


def revoke_all_sessions(user_id):
    """«Выйти на всех устройствах» — понадобится, если телефон потерян."""
    with db() as c:
        c.execute("UPDATE web_sessions SET revoked=1 WHERE user_id=?", (str(user_id),))
