"""Тренажёр хадисов (23.09.2026) — «Сорок хадисов» ан-Навави слово за словом.

Методика — как в N-1 (решение пользователя): хадисы по порядку, в хадисе
слово за словом, включая частицы и повторы, одно новое слово в день. Пока
хадис не выучен, к следующему не переходят.

* **Слово дня** показывается внутри своей фразы, с переводом. Это не проверка:
  студент смотрит и нажимает «Закрепить».
* **Закрепление** — сам тренажёр: вопросы с четырьмя вариантами, слово →
  перевод и перевод → слово. Сегодняшнее слово — в обе стороны, дальше слова
  прошлых дней, забытое чаще. Ошибка возвращается в конце захода.
* **Норма** — 5 верных; пока выучено меньше трёх слов — 2 на слово (одно
  слово — 2, два — 4). Норма засчитывает задание «Хадис» группы.
* **Ещё слово** — по желанию до трёх новых в день, норма от этого не растёт.
* **Старт** — студент сам ставит, с какого хадиса и слова продолжает: в N-1
  все на разных местах.

Ответы не генерируются: слова и переводы — core/arbain.json.gz
(scripts/build_arbain.py: пословная таблица из PDF пользователя + текст с
огласовками из архива ar-ru.ru).
"""
import gzip
import json
import logging
import os
import random
import re

from core.db import db, get_date

log = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(__file__), "arbain.json.gz")
DAILY_TARGET = 5
NEW_PER_DAY_MAX = 3
MAX_RETRIES_PER_WORD = 2
N_OPTIONS = 4

_HARAKAT = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_NOT_LETTER = re.compile(r"[^ء-ي ]")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS hadith_progress(
    user_id TEXT PRIMARY KEY,
    hadith INTEGER NOT NULL,
    pos INTEGER NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS hadith_new_words(
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    hadith INTEGER NOT NULL,
    pos INTEGER NOT NULL,
    PRIMARY KEY(user_id, hadith, pos)
);
CREATE TABLE IF NOT EXISTS hadith_answers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    word TEXT NOT NULL,
    dir TEXT NOT NULL,
    correct INTEGER NOT NULL,
    retry INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_hadith_answers_user ON hadith_answers(user_id, word, id);
CREATE TABLE IF NOT EXISTS hadith_sessions(
    user_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    data TEXT NOT NULL
);
"""


def init():
    with db() as c:
        c.executescript(_SCHEMA)


_data = None


def data():
    global _data
    if _data is None:
        with gzip.open(DATA_PATH, "rt", encoding="utf-8") as f:
            _data = {h["n"]: h for h in json.load(f)}
    return _data


def letters(s):
    s = _HARAKAT.sub("", s or "")
    s = _NOT_LETTER.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return " ".join(s.split())


def _norm_ru(s):
    return re.sub(r"\(.*?\)|[^\w ]", "", (s or "").lower()).strip()


def _word(n, i):
    return data()[n]["words"][i]


def _key(n, i):
    return "%d:%d" % (n, i)


def _identity(n, i):
    """Одно и то же слово с тем же переводом в разных местах («إلى — к»)
    - одно слово: спрашивается и выбирается один раз."""
    w = _word(n, i)
    return letters(w["ar"]) + "|" + _norm_ru(w["ru"])


# ── Прогресс ──────────────────────────────────────────────────────────────────

def progress(user_id):
    """(хадис, сколько слов в нём уже выучено) или None - старт не выбран."""
    with db() as c:
        row = c.execute("SELECT hadith, pos FROM hadith_progress WHERE user_id=?", (str(user_id),)).fetchone()
    return (row["hadith"], row["pos"]) if row else None


def set_start(user_id, hadith, pos=0):
    """Студент сам ставит, откуда продолжает. Слова до этого места считаются
    выученными - закрепление по ним идёт сразу."""
    d = data()
    if hadith not in d:
        raise ValueError("bad_hadith")
    pos = max(0, min(int(pos), len(d[hadith]["words"])))
    with db() as c:
        c.execute("INSERT INTO hadith_progress(user_id, hadith, pos) VALUES(?,?,?)"
                  " ON CONFLICT(user_id) DO UPDATE SET hadith=excluded.hadith, pos=excluded.pos,"
                  " updated_at=datetime('now')", (str(user_id), hadith, pos))
        c.execute("DELETE FROM hadith_sessions WHERE user_id=?", (str(user_id),))


def _advance(user_id, n, pos):
    d = data()
    pos += 1
    if pos >= len(d[n]["words"]) and n + 1 in d:
        n, pos = n + 1, 0
    with db() as c:
        c.execute("UPDATE hadith_progress SET hadith=?, pos=?, updated_at=datetime('now') WHERE user_id=?",
                  (n, pos, str(user_id)))


def next_word(user_id):
    """(хадис, № слова) - следующее новое слово, None - всё выучено."""
    p = progress(user_id)
    if not p:
        return None
    n, pos = p
    if pos < len(data()[n]["words"]):
        return n, pos
    return None


def learned(user_id):
    """Выученные слова: [(хадис, №)] - всё до текущего места."""
    p = progress(user_id)
    if not p:
        return []
    n, pos = p
    out = []
    for h in sorted(data()):
        if h < n:
            out += [(h, i) for i in range(len(data()[h]["words"]))]
        elif h == n:
            out += [(h, i) for i in range(pos)]
    return out


def new_today(user_id):
    with db() as c:
        return c.execute("SELECT count(*) n FROM hadith_new_words WHERE user_id=? AND date=?",
                         (str(user_id), get_date())).fetchone()["n"]


def daily_count(user_id):
    with db() as c:
        return c.execute("SELECT count(*) n FROM hadith_answers WHERE user_id=? AND date=? AND correct=1",
                         (str(user_id), get_date())).fetchone()["n"]


def daily_target(user_id):
    """5 верных; пока слов мало - по два на слово (1 слово - 2, 2 - 4)."""
    k = len({_identity(n, i) for n, i in learned(user_id)})
    return max(2, min(DAILY_TARGET, 2 * k)) if k else DAILY_TARGET


# ── Выбор слов ────────────────────────────────────────────────────────────────

def _streaks(user_id):
    """{слово: серия верных подряд с конца} - по всей истории."""
    with db() as c:
        rows = c.execute("SELECT word, correct FROM hadith_answers WHERE user_id=? ORDER BY id",
                         (str(user_id),)).fetchall()
    out = {}
    for r in rows:
        out[r["word"]] = out.get(r["word"], 0) + 1 if r["correct"] else 0
    return out


def _pick_old(user_id, exclude, count, rnd):
    """Слова прошлых дней: забытое чаще (вес 1/(1+серия)), без повторов.
    Главное - текущий хадис: из прежних хадисов не больше одного слова за
    заход. Иначе у того, кто начал с 8-го, сотни слов 1-7-го перевешивали
    девять слов его хадиса (снимок стенда 23.09)."""
    streak = _streaks(user_id)
    p = progress(user_id)
    cur_h = p[0] if p else None
    seen, here, before = set(exclude), [], []
    for n, i in learned(user_id):
        ident = _identity(n, i)
        if ident in seen:
            continue
        seen.add(ident)
        (here if n == cur_h else before).append((n, i))

    def draw(pool, k):
        out = []
        while pool and len(out) < k:
            weights = [1.0 / (1 + streak.get(_key(n, i), 0)) for n, i in pool]
            j = rnd.choices(range(len(pool)), weights=weights)[0]
            out.append(pool.pop(j))
        return out

    # Только что перешёл на новый хадис - в нём ещё пусто, тогда из прежних.
    take_before = 1 if here else count
    picked = draw(here, count - min(take_before, len(before)))
    picked += draw(before, count - len(picked))
    rnd.shuffle(picked)
    return picked


def _options(n, i, direction, rnd):
    """Четыре варианта: верный + три других слова, лучше из того же хадиса."""
    right = _word(n, i)
    key = (lambda w: _norm_ru(w["ru"])) if direction == "ar2ru" else (lambda w: letters(w["ar"]))
    taken, pool = {key(right)}, []
    for h in [n] + [x for x in sorted(data()) if x != n]:
        ws = data()[h]["words"]
        cand = list(range(len(ws)))
        rnd.shuffle(cand)
        for j in cand:
            k = key(ws[j])
            if k and k not in taken:
                taken.add(k)
                pool.append(ws[j])
            if len(pool) >= N_OPTIONS - 1:
                break
        if len(pool) >= N_OPTIONS - 1:
            break
    opts = [right] + pool
    rnd.shuffle(opts)
    return [{"key": key(w), "text": w["ru"] if direction == "ar2ru" else w["ar"]} for w in opts], key(right)


def context(n, i):
    """Фраза, в которой стоит слово, и где в ней слово - для показа."""
    h = data()[n]
    ph = _word(n, i).get("ph")
    j = i
    while ph is None and j > 0:                        # слово из другого издания
        j -= 1
        ph = h["words"][j].get("ph")
    if ph is None:
        return {"tokens": [{"t": _word(n, i)["ar"], "hl": True}], "ru": ""}
    phrase = h["phrases"][ph]
    target = letters(_word(n, i)["ar"])
    # Повторы в одной фразе: отмечаем то вхождение, которое по счёту совпадает.
    nth = sum(1 for k in range(i) if h["words"][k].get("ph") == ph and letters(h["words"][k]["ar"]) == target)
    tokens, hit = [], 0
    marked = False
    for t in phrase["ar"].split():
        is_it = not marked and letters(t.strip("،,.:«»\"()[]؛؟")) == target
        if is_it:
            if hit == nth:
                marked = True
            else:
                is_it = False
            hit += 1
        tokens.append({"t": t, "hl": is_it})
    if not marked:
        tokens = [{"t": t, "hl": False} for t in phrase["ar"].split()]
    return {"tokens": tokens, "ru": phrase["ru"]}


# ── Заход ─────────────────────────────────────────────────────────────────────

def _load_session(user_id):
    with db() as c:
        row = c.execute("SELECT date, data FROM hadith_sessions WHERE user_id=?", (str(user_id),)).fetchone()
    if not row or row["date"] != get_date():
        return None
    return json.loads(row["data"])


def _save_session(user_id, session):
    with db() as c:
        c.execute("INSERT INTO hadith_sessions(user_id, date, data) VALUES(?,?,?)"
                  " ON CONFLICT(user_id) DO UPDATE SET date=excluded.date, data=excluded.data",
                  (str(user_id), get_date(), json.dumps(session, ensure_ascii=False)))


def _build_queue(user_id, new_word, size, rnd):
    """Сегодняшнее слово в обе стороны, дальше слова прошлых дней."""
    queue = []
    exclude = set()
    if new_word:
        n, i = new_word
        queue += [[n, i, "ar2ru", 0], [n, i, "ru2ar", 0]]
        exclude.add(_identity(n, i))
    for n, i in _pick_old(user_id, exclude, max(0, size - len(queue)), rnd):
        queue.append([n, i, rnd.choice(["ar2ru", "ru2ar"]), 0])
    # Слов мало (второй день): одно старое слово тоже в обе стороны.
    if len(queue) < size:
        olds = [q for q in queue if new_word is None or (q[0], q[1]) != tuple(new_word)]
        for q in olds:
            if len(queue) >= size:
                break
            queue.append([q[0], q[1], "ru2ar" if q[2] == "ar2ru" else "ar2ru", 0])
    return queue[:size]


def _start_quiz(user_id, new_word=None, size=None):
    rnd = random.Random()
    size = size or daily_target(user_id)
    session = {"stage": "quiz", "queue": _build_queue(user_id, new_word, size, rnd),
               "asked": 0, "correct": 0, "size": size, "results": [], "current": None,
               "new": list(new_word) if new_word else None}
    _next_card(session, rnd)
    _save_session(user_id, session)
    return session


def _next_card(session, rnd=None):
    rnd = rnd or random.Random()
    if not session["queue"]:
        session["current"] = None
        return
    n, i, direction, retry = session["queue"].pop(0)
    opts, right = _options(n, i, direction, rnd)
    session["current"] = {"n": n, "i": i, "dir": direction, "retry": retry, "options": opts, "right": right,
                          "id": "%d:%d:%s:%d" % (n, i, direction, session["asked"])}
    session["asked"] += 1


def _word_view(n, i):
    w = _word(n, i)
    h = data()[n]
    return {"hadith": n, "pos": i + 1, "total": len(h["words"]), "ar": w["ar"], "ru": w["ru"],
            "context": context(n, i)}


def state(user_id, feedback=None):
    out = {"daily_count": daily_count(user_id), "daily_target": daily_target(user_id),
           "new_today": new_today(user_id), "new_max": NEW_PER_DAY_MAX, "feedback": feedback}
    p = progress(user_id)
    if not p:
        out["pick"] = [{"n": n, "words": len(h["words"]), "first": h["words"][0]["ar"] if h["words"] else ""}
                       for n, h in sorted(data().items())]
        return out
    out["where"] = {"hadith": p[0], "pos": p[1], "total": len(data()[p[0]]["words"])}
    session = _load_session(user_id)
    # Новый день: сначала слово дня, если есть что учить.
    if session is None:
        nw = next_word(user_id)
        if nw and new_today(user_id) == 0:
            out["new_word"] = _word_view(*nw)
            return out
        if not learned(user_id):
            out["empty"] = True
            return out
        session = _start_quiz(user_id)
    cur = session.get("current")
    if cur is None:
        nw = next_word(user_id)
        out["finished"] = {"correct": session["correct"], "size": session["size"],
                           "results": session["results"],
                           "more": bool(nw) and new_today(user_id) < NEW_PER_DAY_MAX}
        return out
    w = _word(cur["n"], cur["i"])
    card = {"id": cur["id"], "dir": cur["dir"], "retry": bool(cur["retry"]),
            "pos": min(session["asked"], session["size"]), "size": session["size"],
            "options": cur["options"]}
    if cur["dir"] == "ar2ru":
        card["context"] = context(cur["n"], cur["i"])
        card["ar"] = w["ar"]
    else:
        card["ru"] = w["ru"]
    out["card"] = card
    return out


def learn(user_id):
    """«Закрепить»: слово дня выучено - начинаем закрепление."""
    nw = next_word(user_id)
    if not nw or new_today(user_id) >= NEW_PER_DAY_MAX:
        return state(user_id)
    n, i = nw
    first_today = new_today(user_id) == 0
    with db() as c:
        c.execute("INSERT OR IGNORE INTO hadith_new_words(user_id, date, hadith, pos) VALUES(?,?,?,?)",
                  (str(user_id), get_date(), n, i))
    _advance(user_id, n, i)
    # Первое слово дня - полное закрепление (норма), следующие - короткое.
    _start_quiz(user_id, new_word=(n, i), size=None if first_today else 3)
    return state(user_id)


def more(user_id):
    """«Ещё одно слово» - показать следующее новое слово."""
    nw = next_word(user_id)
    if not nw or new_today(user_id) >= NEW_PER_DAY_MAX:
        return state(user_id)
    with db() as c:
        c.execute("DELETE FROM hadith_sessions WHERE user_id=?", (str(user_id),))
    out = {"daily_count": daily_count(user_id), "daily_target": daily_target(user_id),
           "new_today": new_today(user_id), "new_max": NEW_PER_DAY_MAX,
           "where": {"hadith": nw[0], "pos": nw[1], "total": len(data()[nw[0]]["words"])},
           "new_word": _word_view(*nw)}
    return out


def answer(user_id, card_id, choice):
    """(ответ для клиента, достигнута ли норма дня именно этим ответом)."""
    session = _load_session(user_id)
    cur = session.get("current") if session else None
    if not cur or cur["id"] != card_id:
        return state(user_id), False                    # двойной тап / устаревшая карточка
    correct = choice == cur["right"]
    before = daily_count(user_id)
    with db() as c:
        c.execute("INSERT INTO hadith_answers(user_id, date, word, dir, correct, retry) VALUES(?,?,?,?,?,?)",
                  (str(user_id), get_date(), _key(cur["n"], cur["i"]), cur["dir"], int(correct), cur["retry"]))
    if correct:
        session["correct"] += 1
    elif cur["retry"] < MAX_RETRIES_PER_WORD:
        other = "ru2ar" if cur["dir"] == "ar2ru" else "ar2ru"
        session["queue"].append([cur["n"], cur["i"], other, cur["retry"] + 1])
    w = _word(cur["n"], cur["i"])
    # В итоге - строка на слово, а не на вопрос: сегодняшнее спрашивается в
    # обе стороны, и дважды в списке оно только путало. Ошибся хоть раз - «повторить».
    mine = next((r for r in session["results"] if r["key"] == _key(cur["n"], cur["i"])), None)
    if mine is None:
        session["results"].append({"key": _key(cur["n"], cur["i"]), "ar": w["ar"], "ru": w["ru"], "ok": correct,
                                   "new": session.get("new") == [cur["n"], cur["i"]]})
    elif not correct:
        mine["ok"] = False
    reached = before < daily_target(user_id) <= before + int(correct)
    feedback = {"correct": correct, "answer": cur["right"], "ar": w["ar"], "ru": w["ru"]}
    _next_card(session)
    _save_session(user_id, session)
    return state(user_id, feedback), reached


def restart(user_id):
    """«Ещё заход» после нормы - закрепление без новых слов."""
    with db() as c:
        c.execute("DELETE FROM hadith_sessions WHERE user_id=?", (str(user_id),))
    if learned(user_id):
        _start_quiz(user_id)
    return state(user_id)
