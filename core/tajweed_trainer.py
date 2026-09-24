"""Тренажёр таджвида (14.09.2026) — вместо письменной сдачи задания «j».

Карточка: буква крупно, под ней четыре места выхода, студент тапает одно
(с 22.09.2026; было восемь).
Правила пользователя:

* **Только пройденное.** Буква попадает в колоду, когда в ЭТОЙ базе
  опубликован урок, где она разобрана. Базы у братьев и сестёр идут
  вразнобой (на 14.09 у сестёр открыто 4 части, у братьев 9), поэтому колода
  считается по `curriculum_parts.published_at`, а не одна на всех.
* **Выученное реже, новое и слабое чаще** (24.09.2026, вместо «равномерно»:
  пользователь — «грамотно ответил, зачем их прогонять»). Интервальное
  повторение: верно с первой попытки — следующий показ через 1, 3, 7, 14,
  30 дней (шаг не чаще раза в день), ошибка — буква снова каждый день.
  Порядок: ошибочные → новые → подошёл срок → ближайшие по сроку.
* **Сифаты** (24.09.2026) — вторая колода: буква → свойство из пары
  (هَمْس или جَهْر и т.д.), пара открывается своим уроком.
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
import datetime
import logging
import random

from core.db import db, get_date

log = logging.getLogger(__name__)

DAILY_TARGET = 4
# Сколько букв подбираем за раз. Это НЕ «заход» с остановкой в конце
# (20.09.2026, решение пользователя): карточки идут лентой, и когда порция
# кончается, подбирается следующая - тем же правилом равномерности. Человек
# сам решает, когда хватит, а норму дня он и так видит в шапке.
BATCH_SIZE = 4
# Через сколько карточек вернуть букву, в которой ошибся. Раньше ошибка
# уходила «в конец захода», а конца больше нет; три карточки - достаточно,
# чтобы не угадать по памяти, и мало, чтобы не забыть разбор.
RETRY_AFTER = 3
# Четыре, а не восемь (22.09.2026, решение пользователя по просьбе братьев):
# цель - заниматься каждый день, а не продираться через восемь кнопок.
# Отбрасываются лёгкие варианты: двое соседей по зоне остаются, так что
# трудное (ق или ك) никуда не девается. Угадать - 25%, но ошибка
# возвращается через RETRY_AFTER карточек, пока не ответит верно.
OPTIONS = 4
SAME_ZONE_DISTRACTORS = 2

# 17 частных мест выхода (урок «Сколько всего мест выхода» и итог главы).
# Порядок - анатомический, от горла к губам: в нём же стоят варианты на
# экране (14.09.2026), чтобы порядок сам был картой рта.
#
# Надписи - эталон лекций, ужатый без потери смысла (сверено пользователем
# 14.09.2026 с тем, как пишут студенты): «дальше всего от рта» = «ближе к
# груди», «сразу под местом ляма» = «под лямом». До трёх строк на кнопке.
MAKHARIJ = (
    {"id": "halq_aqsa",     "zone": "halq",     "ru": "Начало горла, ближе к груди"},
    {"id": "halq_wasat",    "zone": "halq",     "ru": "Середина горла"},
    {"id": "halq_adna",     "zone": "halq",     "ru": "Конец горла, ближе ко рту"},
    {"id": "lisan_qaf",     "zone": "lisan",    "ru": "Корень языка у глотки + мягкое нёбо"},
    {"id": "lisan_kaf",     "zone": "lisan",    "ru": "Корень языка ближе ко рту + мягкое нёбо"},
    {"id": "lisan_wasat",   "zone": "lisan",    "ru": "Середина языка + твёрдое нёбо"},
    {"id": "lisan_hafa",    "zone": "lisan",    "ru": "Бок языка (левый или правый) + верхние коренные зубы"},
    {"id": "lisan_lam",     "zone": "lisan",    "ru": "Край языка до кончика + дёсны верхних передних зубов"},
    {"id": "lisan_nun",     "zone": "lisan",    "ru": "Кончик языка + дёсны над верхними зубами, под лямом"},
    {"id": "lisan_ra",      "zone": "lisan",    "ru": "Почти как нун, но спинка языка подтянута внутрь"},
    {"id": "lisan_nit",     "zone": "lisan",    "ru": "Кончик языка + основание верхних передних зубов изнутри"},
    {"id": "lisan_safir",   "zone": "lisan",    "ru": "Кончик языка над краем нижних передних зубов, со свистом"},
    {"id": "lisan_lithawi", "zone": "lisan",    "ru": "Кончик языка между зубами + край верхних передних зубов"},
    {"id": "shafa_fa",      "zone": "shafatan", "ru": "Нижняя губа + кончики верхних передних зубов"},
    {"id": "shafatan",      "zone": "shafatan", "ru": "Обе губы"},
    {"id": "jawf",          "zone": "jawf",     "ru": "Пустота рта и горла"},
    {"id": "khayshum",      "zone": "khayshum", "ru": "Нос (хайшум)"},
)
_MAKHRAJ = {m["id"]: m for m in MAKHARIJ}
_ORDER = {m["id"]: i for i, m in enumerate(MAKHARIJ)}

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
for _c in CARDS:
    _c["kind"], _c["answer"] = "makhraj", _c["makhraj"]

# ── Сифаты (24.09.2026): пять пар «Джазарийи», по уроку на пару ────────────
# Списки букв - из байтов (sources/matn/jazariyya.txt): فَحَثَّهُ شَخْصٌ سَكَتْ,
# أَجِدْ قَطٍ بَكَتْ, لِنْ عُمَرْ, خُصَّ ضَغْطٍ قِظْ, ص ض ط ظ, فِرَّ مِنْ لُبِّ.
# Буквы, не названные в байте, получают противоположное свойство («وَالضِّدَّ قُلْ»).
# Варианты - только свойства самой пары, в порядке урока.
SIFAT = (
    {"id": "hams", "lesson": "Первая пара", "question": "Шёпот или звонкость?",
     "options": (("hams", "Шёпот — الهمس"), ("jahr", "Звонкость — الجهر")),
     "letters": {"hams": "فحثهشخصسكت"}, "rest": "jahr"},
    {"id": "shidda", "lesson": "Вторая пара", "question": "Звук обрывается или течёт?",
     "options": (("shidda", "Взрыв — الشدة"), ("tawassut", "Середина — التوسط"),
                 ("rakhawa", "Мягкость — الرخاوة")),
     "letters": {"shidda": "ءجدقطبكت", "tawassut": "لنعمر"}, "rest": "rakhawa"},
    {"id": "istila", "lesson": "Третья пара", "question": "Корень языка поднят или опущен?",
     "options": (("istila", "Подъём — الاستعلاء"), ("istifal", "Опускание — الاستفال")),
     "letters": {"istila": "خصضغطقظ"}, "rest": "istifal"},
    {"id": "itbaq", "lesson": "Четвёртая пара", "question": "Язык прижат к нёбу или нет?",
     "options": (("itbaq", "Прижатие — الإطباق"), ("infitah", "Открытие — الانفتاح")),
     "letters": {"itbaq": "صضطظ"}, "rest": "infitah"},
    {"id": "idhlaq", "lesson": "Пятая пара", "question": "Лёгкая или удержанная?",
     "options": (("idhlaq", "Лёгкость — الإذلاق"), ("ismat", "Удержание — الإصمات")),
     "letters": {"idhlaq": "فرمنلب"}, "rest": "ismat"},
)
_SIFA = {p["id"]: p for p in SIFAT}
_SIFA_LABEL = {oid: label for p in SIFAT for oid, label in p["options"]}
# 28 согласных букв; و и ي - согласные, как в карточках мест выхода.
SIFA_LETTERS = "ءبتثجحخدذرزسشصضطظعغفقكلمنهوي"
_NOTE = {"و": "согласная, как в وَلَد", "ي": "согласная, как в يَد"}


def _sifa_answer(pair, letter):
    for ans, letters in pair["letters"].items():
        if letter in letters:
            return ans
    return pair["rest"]


CARDS = CARDS + tuple(
    {"id": "sf_%s_%d" % (p["id"], i), "glyph": ch, "note": _NOTE.get(ch, ""),
     "kind": p["id"], "answer": _sifa_answer(p, ch), "lesson": p["lesson"]}
    for p in SIFAT for i, ch in enumerate(SIFA_LETTERS))
_CARD = {c["id"]: c for c in CARDS}

# Пауза до следующего показа после n-го верного дня подряд (1-й, 2-й, ...).
INTERVALS = (1, 3, 7, 14, 30)

# Заход живёт в памяти процесса, как активный вопрос у тренажёра слов: после
# рестарта бота человек просто начнёт новый заход, счёт дня лежит в базе.
_sessions = {}


def open_cards(user_id=None):
    """Карточки уроков, открытых группе этого человека (17.09.2026,
    core/curriculum.py); устазу и без user_id - всё опубликованное в базе."""
    try:
        from core.curriculum import topics as _topics, user_group_id
        topics = _topics("j", user_group_id(user_id) if user_id else None)
    except Exception as e:
        log.error("tajweed open_cards error: %s: %s", type(e).__name__, e)
        return []
    return [card for card in CARDS
            if any(t.startswith(card["lesson"]) for t in topics)]


def _stats(user_id):
    with db() as c:
        rows = c.execute("SELECT card, shown, streak, due FROM tajweed_card_stats WHERE user_id=?",
                         (str(user_id),)).fetchall()
    return {r["card"]: r for r in rows}


def _tier(row, today):
    """0 - ошибся в прошлый раз, 1 - новая, 2 - подошёл срок, 3 - рано.
    Ошибка ставит due, а у строк до 24.09 его нет: они не «ошибочные», а
    просто пора повторить."""
    if row is None or not row["shown"]:
        return 1
    if row["due"] and row["due"] > today:
        return 3
    if row["streak"] == 0 and row["due"]:
        return 0
    return 2


def _pick_batch(user_id, cards, skip=()):
    """Сначала ошибочные, потом новые, потом те, кому подошёл срок; при
    равенстве - случайно. Если всё выученное отдыхает, лента не встаёт:
    берутся ближайшие по сроку.

    skip - буквы, которые прямо сейчас в работе: без этого следующая порция
    могла бы начаться с той же буквы, на которой человек только что стоял."""
    stats, today = _stats(user_id), get_date()
    pool = [c for c in cards if c["id"] not in skip] or list(cards)

    def key(c):
        row = stats.get(c["id"])
        tier = _tier(row, today)
        return (tier, row["due"] if tier == 3 else "", random.random())
    return [c["id"] for c in sorted(pool, key=key)[:BATCH_SIZE]]


def _options(card):
    if card["kind"] != "makhraj":
        return [oid for oid, _ in _SIFA[card["kind"]]["options"]]
    return _makhraj_options(card)


def _label(card, oid):
    return _MAKHRAJ[oid]["ru"] if card["kind"] == "makhraj" else _SIFA_LABEL[oid]


def _makhraj_options(card):
    """OPTIONS мест выхода: верное, два из той же зоны, остальные из всей карты.
    На экране - в анатомическом порядке, не вразброс."""
    right = _MAKHRAJ[card["makhraj"]]
    same = [m["id"] for m in MAKHARIJ if m["zone"] == right["zone"] and m["id"] != right["id"]]
    random.shuffle(same)
    picked = same[:SAME_ZONE_DISTRACTORS]
    rest = [m["id"] for m in MAKHARIJ if m["id"] != right["id"] and m["id"] not in picked]
    random.shuffle(rest)
    picked += rest[:OPTIONS - 1 - len(picked)]
    picked.append(right["id"])
    return sorted(picked, key=_ORDER.get)


def daily_count(user_id):
    with db() as c:
        row = c.execute("SELECT count(*) n FROM tajweed_daily WHERE user_id=? AND date=?",
                        (str(user_id), get_date())).fetchone()
    return row["n"]


def _after(today, days):
    return (datetime.date.fromisoformat(today) + datetime.timedelta(days=days)).isoformat()


def _record(user_id, card_id, correct, first_try):
    today = get_date()
    with db() as c:
        if first_try:
            c.execute(
                "INSERT INTO tajweed_card_stats(user_id, card, shown, correct, last_at)"
                " VALUES(?,?,1,?,datetime('now'))"
                " ON CONFLICT(user_id, card) DO UPDATE SET shown=shown+1,"
                " correct=correct+excluded.correct, last_at=excluded.last_at",
                (str(user_id), card_id, 1 if correct else 0))
            row = c.execute("SELECT streak, ok_date FROM tajweed_card_stats WHERE user_id=? AND card=?",
                            (str(user_id), card_id)).fetchone()
            if not correct:
                c.execute("UPDATE tajweed_card_stats SET streak=0, due=? WHERE user_id=? AND card=?",
                          (today, str(user_id), card_id))
            elif row["ok_date"] != today:
                # Шаг серии - раз в день: десять верных за вечер - это один день.
                streak = row["streak"] + 1
                c.execute("UPDATE tajweed_card_stats SET streak=?, ok_date=?, due=?"
                          " WHERE user_id=? AND card=?",
                          (streak, today, _after(today, INTERVALS[min(streak, len(INTERVALS)) - 1]),
                           str(user_id), card_id))
        if correct:
            c.execute("INSERT OR IGNORE INTO tajweed_daily(user_id, date, card) VALUES(?,?,?)",
                      (str(user_id), get_date(), card_id))


def _refill(session, user_id):
    """Долить букв, когда порция кончилась. Лента не должна упираться в
    стену: кто решил закрепить сверх нормы, просто продолжает."""
    cards = open_cards(user_id)
    if not cards:
        return
    busy = set(session["queue"])
    if session["current"]:
        busy.add(session["current"]["card"])
    session["queue"] += _pick_batch(user_id, cards, skip=busy)


def _next(session, user_id):
    """Следующая буква ленты. Очередь никогда не пустеет: кончилась порция -
    подбираем новую (20.09.2026). Ошибка лежит в самой очереди на три шага
    вперёд, отдельной пачки «повторов в конце» больше нет."""
    if not session["queue"]:
        _refill(session, user_id)
    if not session["queue"]:
        session["current"] = None          # колода пуста - уроков ещё нет
        return
    card_id = session["queue"].pop(0)
    session["retry_now"] = card_id in session["missed"]
    session["current"] = {"card": card_id, "options": _options(_CARD[card_id])}


def start(user_id):
    cards = open_cards(user_id)
    if not cards:
        _sessions.pop(str(user_id), None)
        return None
    session = {"queue": _pick_batch(user_id, cards), "current": None,
               "retry_now": False, "missed": set(), "asked": 0}
    _next(session, user_id)
    _sessions[str(user_id)] = session
    return session


def state(user_id, feedback=None):
    """Что показать сейчас: карточку или «уроков ещё нет».

    Экрана «Заход окончен» больше нет (20.09.2026, решение пользователя):
    каждые четыре буквы он вставал стеной и спрашивал разрешения продолжить,
    хотя человек и так знает, что норму дня надо закрыть, а сверх неё
    занимается по своей воле. Ход дня виден в шапке счётчиком."""
    session = _sessions.get(str(user_id)) or start(user_id)
    done = daily_count(user_id)
    out = {"daily_count": done, "daily_target": DAILY_TARGET, "feedback": feedback}
    if session is None:
        out["empty"] = True
        return out
    cur = session["current"]
    if cur is None:
        out["empty"] = True                # колоду отобрали (урок сняли)
        return out
    card = _CARD[cur["card"]]
    out["card"] = {
        "id": card["id"], "glyph": card["glyph"], "note": card["note"],
        "retry": session["retry_now"],
        # Точки показывают ход ДНЯ, а не порции: порция - внутреннее дело
        # подбора, человеку про неё знать незачем. Норма закрыта - точки
        # полны, и это единственное, что меняется на экране.
        "pos": min(done + 1, DAILY_TARGET), "size": DAILY_TARGET,
        "day_done": done >= DAILY_TARGET,
    }
    out["card"]["question"] = (_SIFA[card["kind"]]["question"]
                               if card["kind"] != "makhraj" else None)
    out["options"] = [_label(card, m) for m in cur["options"]]
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
    correct = cur["options"][slot] == card["answer"]
    first_try = not session["retry_now"]
    before = daily_count(user_id)
    _record(user_id, card_id, correct, first_try)
    session["asked"] += 1
    if not correct:
        # Ошибка возвращается через три карточки, а не «в конец захода»:
        # конца больше нет, а подряд повторять - значит проверять память на
        # пять секунд, а не знание места выхода.
        session["missed"].add(card_id)
        # Доливаем ДО вставки: на последней карточке порции очередь пуста, и
        # буква встала бы в позицию 0, то есть следующим же вопросом.
        while len(session["queue"]) < RETRY_AFTER:
            before_len = len(session["queue"])
            _refill(session, user_id)
            if len(session["queue"]) == before_len:
                break                      # колода меньше, чем отступ
        session["queue"].insert(min(RETRY_AFTER, len(session["queue"])), card_id)
    else:
        session["missed"].discard(card_id)
    reached = before < DAILY_TARGET <= daily_count(user_id)
    feedback = {"correct": correct, "glyph": card["glyph"], "note": card["note"],
                "answer": _label(card, card["answer"])}
    _next(session, user_id)
    return state(user_id, feedback), reached


def new_session(user_id):
    """Начать ленту заново. Кнопки «Ещё заход» больше нет (20.09.2026), но
    метод остаётся: его зовут страницы, оставшиеся в кэше телефона, и он же
    пригодится, если колода сменилась (устаз опубликовал новый урок)."""
    _sessions.pop(str(user_id), None)
    return state(user_id)
