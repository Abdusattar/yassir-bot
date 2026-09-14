"""Тренажёр таджвида (14.09.2026) — вместо письменной сдачи задания «j».

Карточка: буква крупно, под ней восемь мест выхода, студент тапает одно.
Правила пользователя:

* **Только пройденное.** Буква попадает в колоду, когда в ЭТОЙ базе
  опубликован урок, где она разобрана. Базы у братьев и сестёр идут
  вразнобой (на 14.09 у сестёр открыто 4 части, у братьев 9), поэтому колода
  считается по `curriculum_parts.published_at`, а не одна на всех.
* **Равномерно.** Следующей идёт буква, которую этому человеку показывали
  реже всех; при равенстве — случайная. Счётчик хранится по каждой букве.
* **Варианты — все 17 мест выхода**, а не только пройденные: студент
  выбирает из всей карты, и неверный вариант — тоже настоящее место из урока,
  выдуманного ответа нет. Два варианта по возможности из той же зоны (горло,
  язык, губы): отличить ق от ك учит больше, чем ق от «Нос».
* **Ошибка повторяется в конце захода**, пока не ответит верно, — чтобы
  запоминал. Счётчик показов растёт только когда буква новая в заходе.
* **Норма — 4 разные буквы верно за день** (в том числе с повтора): она и
  засчитывает задание «Таджвид» группы.

Банк ниже собран ТОЛЬКО из текстов опубликованных уроков (Аль-Мукаддима
аль-Джазарийя). Сверка с Умар устазом — до выкладки.
"""
import logging
import random

from core.db import db, get_date

log = logging.getLogger(__name__)

DAILY_TARGET = 4
SESSION_SIZE = 4
OPTIONS = 8
SAME_ZONE_DISTRACTORS = 2

# 17 частных мест выхода (урок «Сколько всего мест выхода» и итог главы).
MAKHARIJ = (
    {"id": "jawf",          "zone": "jawf",     "ru": "Полость рта и горла"},
    {"id": "halq_aqsa",     "zone": "halq",     "ru": "Начало горла, глубже всего"},
    {"id": "halq_wasat",    "zone": "halq",     "ru": "Середина горла"},
    {"id": "halq_adna",     "zone": "halq",     "ru": "Конец горла, ближе ко рту"},
    {"id": "lisan_qaf",     "zone": "lisan",    "ru": "Корень языка, глубже"},
    {"id": "lisan_kaf",     "zone": "lisan",    "ru": "Корень языка, ближе ко рту"},
    {"id": "lisan_wasat",   "zone": "lisan",    "ru": "Середина языка и твёрдое нёбо"},
    {"id": "lisan_hafa",    "zone": "lisan",    "ru": "Боковой край языка и коренные зубы"},
    {"id": "lisan_lam",     "zone": "lisan",    "ru": "Край языка до кончика и дёсны"},
    {"id": "lisan_nun",     "zone": "lisan",    "ru": "Кончик языка, чуть ниже ляма"},
    {"id": "lisan_ra",      "zone": "lisan",    "ru": "Кончик языка, спинка подтянута"},
    {"id": "lisan_nit",     "zone": "lisan",    "ru": "Кончик языка и корни верхних зубов"},
    {"id": "lisan_safir",   "zone": "lisan",    "ru": "Кончик языка у нижних зубов, свист"},
    {"id": "lisan_lithawi", "zone": "lisan",    "ru": "Кончик языка между зубами"},
    {"id": "shafa_fa",      "zone": "shafatan", "ru": "Нижняя губа и верхние зубы"},
    {"id": "shafatan",      "zone": "shafatan", "ru": "Обе губы"},
    {"id": "khayshum",      "zone": "khayshum", "ru": "Нос — гунна"},
)
_MAKHRAJ = {m["id"]: m for m in MAKHARIJ}

# Урок — по началу названия темы: id частей у баз разные, названия одни.
# Буквы урока «Сколько всего мест выхода» здесь не берутся: полость в нём
# только названа, разобрана она в «Полости».
CARDS = (
    # Горло (الحلق)
    {"id": "hamza", "glyph": "ء", "note": "", "makhraj": "halq_aqsa",  "lesson": "Горло"},
    {"id": "ha",    "glyph": "ه", "note": "", "makhraj": "halq_aqsa",  "lesson": "Горло"},
    {"id": "ain",   "glyph": "ع", "note": "", "makhraj": "halq_wasat", "lesson": "Горло"},
    {"id": "hha",   "glyph": "ح", "note": "", "makhraj": "halq_wasat", "lesson": "Горло"},
    {"id": "ghain", "glyph": "غ", "note": "", "makhraj": "halq_adna",  "lesson": "Горло"},
    {"id": "kha",   "glyph": "خ", "note": "", "makhraj": "halq_adna",  "lesson": "Горло"},
    # Губы (الشفتان)
    {"id": "fa",    "glyph": "ف", "note": "", "makhraj": "shafa_fa", "lesson": "Губы"},
    {"id": "ba",    "glyph": "ب", "note": "", "makhraj": "shafatan", "lesson": "Губы"},
    {"id": "mim",   "glyph": "م", "note": "", "makhraj": "shafatan", "lesson": "Губы"},
    {"id": "waw",   "glyph": "و", "note": "согласная, как в وَلَد", "makhraj": "shafatan", "lesson": "Губы"},
    # Корень языка (أقصى اللسان)
    {"id": "qaf",   "glyph": "ق", "note": "", "makhraj": "lisan_qaf", "lesson": "Корень языка"},
    {"id": "kaf",   "glyph": "ك", "note": "", "makhraj": "lisan_kaf", "lesson": "Корень языка"},
    # Середина языка (وسط اللسان)
    {"id": "jim",   "glyph": "ج", "note": "", "makhraj": "lisan_wasat", "lesson": "Середина языка"},
    {"id": "shin",  "glyph": "ش", "note": "", "makhraj": "lisan_wasat", "lesson": "Середина языка"},
    {"id": "ya",    "glyph": "ي", "note": "согласная, как в يَد", "makhraj": "lisan_wasat", "lesson": "Середина языка"},
    # Ад-Дад
    {"id": "dad",   "glyph": "ض", "note": "", "makhraj": "lisan_hafa", "lesson": "Ад-Дад"},
    # Кончик языка — ل ن ر
    {"id": "lam",   "glyph": "ل", "note": "", "makhraj": "lisan_lam", "lesson": "Кончик языка"},
    {"id": "nun",   "glyph": "ن", "note": "", "makhraj": "lisan_nun", "lesson": "Кончик языка"},
    {"id": "ra",    "glyph": "ر", "note": "", "makhraj": "lisan_ra",  "lesson": "Кончик языка"},
    # Зубно-язычные — ط د ت / ص س ز / ظ ذ ث
    {"id": "tta",   "glyph": "ط", "note": "", "makhraj": "lisan_nit",     "lesson": "Зубно-язычные"},
    {"id": "dal",   "glyph": "د", "note": "", "makhraj": "lisan_nit",     "lesson": "Зубно-язычные"},
    {"id": "ta",    "glyph": "ت", "note": "", "makhraj": "lisan_nit",     "lesson": "Зубно-язычные"},
    {"id": "sad",   "glyph": "ص", "note": "", "makhraj": "lisan_safir",   "lesson": "Зубно-язычные"},
    {"id": "sin",   "glyph": "س", "note": "", "makhraj": "lisan_safir",   "lesson": "Зубно-язычные"},
    {"id": "zay",   "glyph": "ز", "note": "", "makhraj": "lisan_safir",   "lesson": "Зубно-язычные"},
    {"id": "zza",   "glyph": "ظ", "note": "", "makhraj": "lisan_lithawi", "lesson": "Зубно-язычные"},
    {"id": "dhal",  "glyph": "ذ", "note": "", "makhraj": "lisan_lithawi", "lesson": "Зубно-язычные"},
    {"id": "tha",   "glyph": "ث", "note": "", "makhraj": "lisan_lithawi", "lesson": "Зубно-язычные"},
    # Полость (الجوف) — буквы мадда
    {"id": "alif_madd", "glyph": "ا", "note": "мадд, как в قَالَ",   "makhraj": "jawf", "lesson": "Полость"},
    {"id": "waw_madd",  "glyph": "و", "note": "мадд, как в يَقُولُ", "makhraj": "jawf", "lesson": "Полость"},
    {"id": "ya_madd",   "glyph": "ي", "note": "мадд, как в قِيلَ",   "makhraj": "jawf", "lesson": "Полость"},
)
_CARD = {c["id"]: c for c in CARDS}

# Заход живёт в памяти процесса, как активный вопрос у тренажёра слов: после
# рестарта бота человек просто начнёт новый заход, счёт дня лежит в базе.
_sessions = {}


def open_cards():
    """Карточки уроков, уже опубликованных в этой базе."""
    try:
        with db() as c:
            topics = [r["topic"] or "" for r in c.execute(
                "SELECT topic FROM curriculum_parts"
                " WHERE subject='j' AND published_at IS NOT NULL").fetchall()]
    except Exception as e:
        log.error("tajweed open_cards error: %s: %s", type(e).__name__, e)
        return []
    return [card for card in CARDS
            if any(t.startswith(card["lesson"]) for t in topics)]


def _shown_counts(user_id):
    with db() as c:
        rows = c.execute("SELECT card, shown FROM tajweed_card_stats WHERE user_id=?",
                         (str(user_id),)).fetchall()
    return {r["card"]: r["shown"] for r in rows}


def _pick_session(user_id, cards):
    """Самые редко показанные, при равенстве — случайные."""
    shown = _shown_counts(user_id)
    order = sorted(cards, key=lambda c: (shown.get(c["id"], 0), random.random()))
    return [c["id"] for c in order[:SESSION_SIZE]]


def _options(card):
    """Восемь мест выхода: верное, два из той же зоны, остальные из всей карты."""
    right = _MAKHRAJ[card["makhraj"]]
    same = [m["id"] for m in MAKHARIJ if m["zone"] == right["zone"] and m["id"] != right["id"]]
    random.shuffle(same)
    picked = same[:SAME_ZONE_DISTRACTORS]
    rest = [m["id"] for m in MAKHARIJ if m["id"] != right["id"] and m["id"] not in picked]
    random.shuffle(rest)
    picked += rest[:OPTIONS - 1 - len(picked)]
    picked.append(right["id"])
    random.shuffle(picked)
    return picked


def daily_count(user_id):
    with db() as c:
        row = c.execute("SELECT count(*) n FROM tajweed_daily WHERE user_id=? AND date=?",
                        (str(user_id), get_date())).fetchone()
    return row["n"]


def _record(user_id, card_id, correct, first_try):
    with db() as c:
        if first_try:
            c.execute(
                "INSERT INTO tajweed_card_stats(user_id, card, shown, correct, last_at)"
                " VALUES(?,?,1,?,datetime('now'))"
                " ON CONFLICT(user_id, card) DO UPDATE SET shown=shown+1,"
                " correct=correct+excluded.correct, last_at=excluded.last_at",
                (str(user_id), card_id, 1 if correct else 0))
        if correct:
            c.execute("INSERT OR IGNORE INTO tajweed_daily(user_id, date, card) VALUES(?,?,?)",
                      (str(user_id), get_date(), card_id))


def _next(session):
    """Сначала новые буквы захода, потом ошибки — в том порядке, в каком ошибся."""
    if session["queue"]:
        card_id, session["retry_now"] = session["queue"].pop(0), False
    elif session["retry"]:
        card_id, session["retry_now"] = session["retry"].pop(0), True
    else:
        session["current"] = None
        return
    session["current"] = {"card": card_id, "options": _options(_CARD[card_id])}


def start(user_id):
    cards = open_cards()
    if not cards:
        _sessions.pop(str(user_id), None)
        return None
    queue = _pick_session(user_id, cards)
    session = {"queue": queue, "retry": [], "current": None, "retry_now": False,
               "size": len(queue), "first_right": 0}
    _next(session)
    _sessions[str(user_id)] = session
    return session


def state(user_id, feedback=None):
    """Что показать сейчас: карточку, итог захода или «уроков ещё нет»."""
    session = _sessions.get(str(user_id)) or start(user_id)
    out = {"daily_count": daily_count(user_id), "daily_target": DAILY_TARGET,
           "feedback": feedback}
    if session is None:
        out["empty"] = True
        return out
    cur = session["current"]
    if cur is None:
        out["finished"] = {"size": session["size"], "first_right": session["first_right"]}
        return out
    card = _CARD[cur["card"]]
    out["card"] = {
        "id": card["id"], "glyph": card["glyph"], "note": card["note"],
        "retry": session["retry_now"],
        "pos": session["size"] - len(session["queue"]), "size": session["size"],
    }
    out["options"] = [_MAKHRAJ[m]["ru"] for m in cur["options"]]
    return out


def answer(user_id, card_id, slot):
    """(ответ для клиента, достигнута ли норма дня именно этим ответом)."""
    session = _sessions.get(str(user_id))
    cur = session["current"] if session else None
    if not cur or cur["card"] != card_id:
        return state(user_id), False          # устаревший или двойной тап
    if not isinstance(slot, int) or not 0 <= slot < len(cur["options"]):
        raise ValueError("bad_slot")
    card = _CARD[card_id]
    correct = cur["options"][slot] == card["makhraj"]
    first_try = not session["retry_now"]
    before = daily_count(user_id)
    _record(user_id, card_id, correct, first_try)
    if first_try and correct:
        session["first_right"] += 1
    if not correct:
        session["retry"].append(card_id)
    reached = before < DAILY_TARGET <= daily_count(user_id)
    feedback = {"correct": correct, "glyph": card["glyph"], "note": card["note"],
                "answer": _MAKHRAJ[card["makhraj"]]["ru"]}
    _next(session)
    return state(user_id, feedback), reached


def new_session(user_id):
    _sessions.pop(str(user_id), None)
    return state(user_id)
