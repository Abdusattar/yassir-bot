"""Тренажёр нахва (17.09.2026) — вместо письменной сдачи задания «n».

Цель у нахва своя: не запомнить ответы на карточки, а научиться узнавать
правило в любом слове Корана. Отсюда устройство (согласовано с
пользователем 17.09.2026):

* **Учим правило, слово каждый раз новое.** Карточка — слово в аяте из
  пройденного студентом диапазона. Повтор после ошибки — ДРУГОЕ слово того
  же типа: проверяем, что понял правило, а не запомнил ответ.
* **Слабое приходит чаще.** Слабость считается не по словам, а по типам
  случаев («исм с ال», «фиаль после قَدْ», «харф, прилипший к слову»...):
  сначала выбирается ответ (исм / фиаль / харф) — чем чаще путает, тем
  чаще, — потом внутри него тип случая по тому же правилу.
* **Рост без скачка.** Ступень 1 — цельные слова (ال и سَ не в счёт: это и
  есть признаки). Ступень 2 — слитные слова, спрашивается выделенная часть
  (وَ + أَبْصَٰرِ + هِمْ). Вторая открывается сама после 85% верных на
  последних 40 ответах первой; норма дня при этом не растёт.
* **Объяснение после ответа** — словами урока «Виды слова» («есть ال —
  признак исма»), плюс разбор слова по частям.
* **Норма — 10 верных за день** (в том числе с повтора): она засчитывает
  задание «Нахв» группы.

Ответы НЕ генерируются: разметка слов — Quranic Arabic Corpus v0.4
(corpus.quran.com, GNU GPL), сборка — scripts/build_nahw_corpus.py.
Навык открыт, когда в ЭТОЙ базе опубликован его урок. Навыки дальше
(признаки исма, число, معرب/مبني...) добавляются в SKILLS по мере уроков.
"""
import bisect
import gzip
import json
import logging
import os
import random
import sqlite3
import unicodedata

from core.db import db, get_date
from core.sampler import HADITHS_DB

log = logging.getLogger(__name__)

DAILY_TARGET = 10
SESSION_SIZE = 10
# Ступень 2 и «навык освоен»: доля верных с первой попытки на последних N.
MASTERY_WINDOW = 40
MASTERY_SHARE = 0.85
# Слабость типа случаев - по последним ответам на него.
WEAKNESS_WINDOW = 20
# Слово не спрашивается снова, пока не прошло столько дней.
ITEM_REST_DAYS = 7
# Повтор одного и того же ошибочного типа в заходе - не больше.
MAX_RETRIES_PER_CARD = 2
# Даже у того, кто в самом начале Бакары, пул не меньше этих страниц:
# вид слова не зависит от того, выучен ли аят, а на трёх аятах нет
# повелительного глагола.
MIN_POOL_PAGE = 5

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "nahw_corpus.json.gz")

ANSWERS = ("ism", "fil", "harf")
ANSWER_AR = {"ism": "اسم", "fil": "فعل", "harf": "حرف"}
ANSWER_RU = {"ism": "Исм", "fil": "Фиаль", "harf": "Харф"}

# Тип случая -> (ответ, подпись для итога захода). Порядок - как в уроке.
CTYPES = {
    "ism_al":       ("ism",  "исм с артиклем الـ"),
    "ism_tanwin":   ("ism",  "исм с танвином"),
    "ism_jarr":     ("ism",  "исм после харфа джарр"),
    "ism_plain":    ("ism",  "исм без внешнего признака"),
    "fil_qad":      ("fil",  "фиаль после قَدْ"),
    "fil_sa":       ("fil",  "фиаль с سَ / سَوْفَ"),
    "fil_tat":      ("fil",  "фиаль с تْ на конце"),
    "fil_madi":     ("fil",  "фиаль прошедшего времени"),
    "fil_mudari":   ("fil",  "фиаль настоящего-будущего"),
    "fil_amr":      ("fil",  "фиаль-повеление"),
    "harf_jarr":    ("harf", "харф джарр"),
    "harf_other":   ("harf", "другие харфы"),
    # Ступень 2 - часть слитного слова.
    "c_harf_pref":  ("harf", "харф, прилипший к слову"),
    "c_ism":        ("ism",  "исм внутри слитного слова"),
    "c_fil":        ("fil",  "фиаль внутри слитного слова"),
    "c_harf":       ("harf", "харф с прилипшим местоимением"),
}

SKILLS = (
    {"id": "kinds", "lesson": "أنواع الكلمة", "title": "Виды слова"},
)

# Не спрашиваются в «Видах слова»: местоимения, указательные, относительные,
# вопросительные и условные слова, наречия места и времени - это исмы, но
# узнаются по темам, которых в уроке ещё не было. Показываются в разборе.
_SKIP_NOUN = {"PRON", "DEM", "REL", "INTG", "COND", "NV", "T", "LOC"}
# Харфы, которые в уроке не разбирались или спорны без контекста:
# буквы-сокращения в начале сур, «ما» после إنّ, лишний харф.
_SKIP_PARTICLE = {"INL", "PREV", "SUP", "INTG", "COND", "DET"}
_TANWIN = set("ًࣰٌࣱٍࣲ")

# Пользователь не видит ступени как «уровня» - только в итоге захода.
_corpus = None


def _feats(seg):
    return set(seg[2].split("|"))


def _is_sign_prefix(seg):
    """ال и سَ - признаки, а не отдельная часть для вопроса."""
    f = _feats(seg)
    return "DET" in f or ("FUT" in f and "PREF" in f)


def _answer_of(seg):
    return {"N": "ism", "V": "fil", "P": "harf"}[seg[1]]


def _letters(text):
    """Только буквы: порядок шадды и фатхи в байтах у корпуса и у нашего
    текста разный, сравнение с харакатами молча не совпадает (17.09.2026 -
    так имя Аллаха прошло в вопросы при «проверенном» исключении)."""
    return "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if unicodedata.category(ch) == "Lo")


_ALLAH_LEMMAS = {"الله", "اللهم"}


def _is_allah(feats):
    return any(x.startswith("LEM:") and _letters(x[4:]) in _ALLAH_LEMMAS for x in feats)


def _askable(seg):
    f = _feats(seg)
    if seg[1] == "N":
        # Имя Аллаха не делаем учебным примером «угадай вид слова» (17.09.2026).
        return not (f & _SKIP_NOUN) and not _is_allah(f)
    if seg[1] == "P":
        return not (f & _SKIP_PARTICLE)
    return True


def _prev_last_seg(ayah, pos):
    prev = ayah.get(str(pos - 1))
    return prev[-1] if prev else None


def _jarr_before(word, idx, ayah, pos):
    """Харф джарр перед исмом: прилипший (بِ لِ كَ) или отдельным словом."""
    for seg in reversed(word[:idx]):
        if _is_sign_prefix(seg):
            continue
        return seg[1] == "P" and "P" in _feats(seg) and seg
    prev = _prev_last_seg(ayah, pos) if idx == 0 or all(_is_sign_prefix(s) for s in word[:idx]) else None
    if prev and prev[1] == "P" and "P" in _feats(prev) and "PREF" not in _feats(prev):
        return prev
    return None


def _signs(word, idx, ayah, pos):
    """Признаки из урока, которые реально есть у этой части слова."""
    seg, f, out = word[idx], _feats(word[idx]), []
    if seg[1] == "N":
        if any("DET" in _feats(s) for s in word[:idx]):
            out.append("al")
        if set(seg[0]) & _TANWIN:
            out.append("tanwin")
        if _jarr_before(word, idx, ayah, pos):
            out.append("jarr")
    elif seg[1] == "V":
        prev = _prev_last_seg(ayah, pos)
        if prev and "CERT" in _feats(prev):
            out.append("qad")
        if any("FUT" in _feats(s) for s in word[:idx]) or (prev and "FUT" in _feats(prev)):
            out.append("sa")
        if "PERF" in f and "3FS" in f and seg[0].rstrip("ْ۟").endswith("ت"):
            out.append("tat")
    return out


def _classify(word, idx, ayah, pos):
    """(ctype, stage) или None, если эту часть не спрашиваем."""
    seg = word[idx]
    if _is_sign_prefix(seg) or not _askable(seg) or "SUFF" in _feats(seg):
        return None
    rest = [s for i, s in enumerate(word) if i != idx and s[0] and not _is_sign_prefix(s)]
    if rest:
        f = _feats(seg)
        if "PREF" in f:
            return ("c_harf_pref", 2) if seg[1] == "P" else None
        return {"N": "c_ism", "V": "c_fil", "P": "c_harf"}[seg[1]], 2
    f, signs = _feats(seg), _signs(word, idx, ayah, pos)
    if seg[1] == "N":
        for s in ("al", "tanwin", "jarr"):
            if s in signs:
                return "ism_" + s, 1
        return "ism_plain", 1
    if seg[1] == "V":
        for s in ("qad", "sa", "tat"):
            if s in signs:
                return "fil_" + s, 1
        if "IMPV" in f:
            return "fil_amr", 1
        return ("fil_mudari" if "IMPF" in f else "fil_madi"), 1
    return ("harf_jarr" if "P" in f else "harf_other"), 1


class _Corpus:
    """Разметка + индекс «тип случая -> слова по порядку мусхафа». Порядковый
    номер аята нужен, чтобы пул «до закладки» отрезался бисекцией, а не
    перебором 77 тысяч слов на каждый тап."""

    def __init__(self, path=CORPUS_PATH):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        self.terms = data["terms"]
        self.ayat = data["ayat"]
        keys = sorted(self.ayat, key=lambda k: tuple(int(x) for x in k.split(":")))
        self.ord = {k: i for i, k in enumerate(keys)}
        self.index = {}          # ctype -> ([ord...], [item...])
        if data.get("index"):
            # Собран scripts/build_nahw_corpus.py: разбор 77 тысяч слов на
            # ходу занимает секунды, а первый вход после рестарта бота ждать
            # не должен.
            for ctype, (ords, items) in data["index"].items():
                self.index[ctype] = (ords, items)
            return
        for key in keys:
            ayah = self.ayat[key]
            for pos in sorted(ayah, key=int):
                word = ayah[pos]
                for idx in range(len(word)):
                    got = _classify(word, idx, ayah, int(pos))
                    if not got:
                        continue
                    ords, items = self.index.setdefault(got[0], ([], []))
                    ords.append(self.ord[key])
                    items.append("%s:%s:%d" % (key, pos, idx))

    def word(self, item):
        s, a, pos, idx = item.split(":")
        ayah = self.ayat["%s:%s" % (s, a)]
        return ayah, ayah[pos], int(pos), int(idx)


def corpus():
    global _corpus
    if _corpus is None:
        _corpus = _Corpus()
    return _corpus


# ── Пул, открытость, статистика ────────────────────────────────────────────

def open_skills():
    """Навыки, чей урок уже опубликован в этой базе."""
    try:
        with db() as c:
            topics = [r["topic"] or "" for r in c.execute(
                "SELECT topic FROM curriculum_parts"
                " WHERE subject='n' AND published_at IS NOT NULL").fetchall()]
    except Exception as e:
        log.error("nahw open_skills error: %s: %s", type(e).__name__, e)
        return []
    return [s for s in SKILLS if any(t.startswith(s["lesson"]) for t in topics)]


def _pool_limit(user_id):
    """Порядковый номер последнего аята пула: страница заучивания, иначе
    закладка «Слов», но не меньше MIN_POOL_PAGE."""
    from core.quran_pages import last_ayah_on_page, LAST_PAGE
    page = None
    try:
        from core.mushaf_words import get_hifz_pointer
        ptr = get_hifz_pointer(str(user_id))
        page = ptr and ptr["page"]
        if not page:
            from core.mufradat import get_current_page
            page = get_current_page(str(user_id))
    except Exception as e:
        log.error("nahw pool page error: %s: %s", type(e).__name__, e)
    page = min(max(page or MIN_POOL_PAGE, MIN_POOL_PAGE), LAST_PAGE)
    s, a = last_ayah_on_page(page)
    return corpus().ord["%d:%d" % (s, a)]


def _first_try_history(user_id, skill, stage=None, ctype=None, limit=MASTERY_WINDOW):
    sql = "SELECT correct FROM nahw_answers WHERE user_id=? AND skill=? AND retry=0"
    args = [str(user_id), skill]
    if stage is not None:
        sql += " AND stage=?"
        args.append(stage)
    if ctype is not None:
        sql += " AND ctype=?"
        args.append(ctype)
    with db() as c:
        rows = c.execute(sql + " ORDER BY id DESC LIMIT ?", args + [limit]).fetchall()
    return [r["correct"] for r in rows]


def _mastered(history):
    return len(history) >= MASTERY_WINDOW and sum(history) >= MASTERY_SHARE * MASTERY_WINDOW


def stage_of(user_id, skill="kinds"):
    return 2 if _mastered(_first_try_history(user_id, skill, stage=1)) else 1


def skill_mastered(user_id, skill="kinds"):
    """Для открытия следующего навыка: ступень 2 держится на 85%."""
    return stage_of(user_id, skill) == 2 and _mastered(_first_try_history(user_id, skill, stage=2))


def daily_count(user_id):
    with db() as c:
        row = c.execute("SELECT count(*) n FROM nahw_answers WHERE user_id=? AND date=? AND correct=1",
                        (str(user_id), get_date())).fetchone()
    return row["n"]


def _weakness(user_id, skill, ctype):
    h = _first_try_history(user_id, skill, ctype=ctype, limit=WEAKNESS_WINDOW)
    return (len(h) - sum(h) + 1) / (len(h) + 2)


def _recent_items(user_id):
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT item FROM nahw_answers WHERE user_id=?"
            " AND created_at >= datetime('now', ?)",
            (str(user_id), "-%d days" % ITEM_REST_DAYS)).fetchall()
    return {r["item"] for r in rows}


def _pick_item(ctype, limit, avoid):
    ords, items = corpus().index.get(ctype, ([], []))
    n = bisect.bisect_right(ords, limit)
    if not n:
        return None
    for _ in range(30):
        item = items[random.randrange(n)]
        if item not in avoid:
            return item
    return items[random.randrange(n)]


def _choose_ctype(user_id, skill, stage, limit):
    """Сначала ответ (исм/фиаль/харф), потом тип случая внутри него - оба
    выбора взвешены слабостью. Без первого шага исмов с фиалями было бы
    вдвое больше харфов просто потому, что у них больше типов."""
    open_types = [t for t, (ans, _) in CTYPES.items()
                  if (stage == 2 or not t.startswith("c_"))
                  and bisect.bisect_right(corpus().index.get(t, ([], []))[0], limit)]
    if not open_types:
        return None
    weak = {t: _weakness(user_id, skill, t) for t in open_types}
    # Новая ступень, пока к ней не привык, - вдвое чаще.
    if stage == 2 and len(_first_try_history(user_id, skill, stage=2)) < MASTERY_WINDOW:
        for t in weak:
            if t.startswith("c_"):
                weak[t] *= 2
    by_answer = {}
    for t in open_types:
        by_answer.setdefault(CTYPES[t][0], []).append(t)
    answers = list(by_answer)
    ans = random.choices(answers, [0.3 + max(weak[t] for t in by_answer[a]) for a in answers])[0]
    types = by_answer[ans]
    return random.choices(types, [0.15 + weak[t] for t in types])[0]


# ── Показ карточки ─────────────────────────────────────────────────────────

def _skel_len(text):
    text = unicodedata.normalize("NFD", text)
    return sum(1 for ch in text if unicodedata.category(ch) == "Lo"
               and ch not in "ءۦۥـ")


def split_by_segments(text, segs):
    """Наше написание слова, разрезанное на части корпуса: по числу букв
    (харакаты и знаки остаются при своей букве). У выпавшей части (ي в
    رَبِّ «мой Господь») букв нет - ей достаётся пустая строка. Не сошлось -
    None, тогда слово показывается целиком."""
    full = [i for i, sg in enumerate(segs) if _skel_len(sg[0])]
    if not full:
        return None
    lens = [_skel_len(segs[i][0]) for i in full]
    parts, k, count = [""] * len(full), 0, 0
    for ch in text:
        if unicodedata.category(ch) == "Lo":
            # Буква после заполненной части открывает следующую.
            while k < len(full) - 1 and count >= lens[k]:
                k, count = k + 1, 0
        parts[k] += ch
        if unicodedata.category(ch) == "Lo" and ch not in "ءۦۥـ":
            count += 1
    if k != len(full) - 1 or count != lens[k]:
        return None
    out = [""] * len(segs)
    for i, part in zip(full, parts):
        out[i] = part
    return out


def _ayah_words(surah, ayah):
    with sqlite3.connect(HADITHS_DB) as conn:
        rows = conn.execute(
            "SELECT position, arabic_text, translation FROM mufradat_words"
            " WHERE surah_number=? AND ayah_number=? AND language='ru' ORDER BY position",
            (surah, ayah)).fetchall()
    return rows


def _seg_label(seg):
    """Арабское название части для разбора: «حرف جر», «فعل مضارع», «ضمير»."""
    t, f = corpus().terms, _feats(seg)
    if "DET" in f:
        return "ال"
    if seg[1] == "P":
        for x in seg[2].split("|"):
            if x in t["particles"]:
                return t["particles"][x]
        return "حرف"
    if seg[1] == "V":
        tense = next((t["verb_tenses"][x] for x in f if x in t["verb_tenses"]), "")
        return ("فعل " + tense).strip()
    for x in ("PRON", "DEM", "REL", "PN", "T", "LOC", "INTG", "COND", "NV"):
        if x in f:
            return t["types"][x]
    return "اسم"


_SIGN_RU = {
    "al": "есть артикль الـ",
    "tanwin": "есть танвин",
    "jarr": "перед ним харф джарр",
    "qad": "перед ним قَدْ",
    "sa": "есть سَ / سَوْفَ",
    "tat": "на конце تْ",
}


def _cap(text):
    return text[:1].upper() + text[1:]


def explain(item):
    """Одна-две строки словами урока «Виды слова»."""
    ayah, word, pos, idx = corpus().word(item)
    seg, f = word[idx], _feats(word[idx])
    signs = _signs(word, idx, ayah, pos)
    if seg[1] == "N":
        if signs:
            return _cap(", ".join(_SIGN_RU[s] for s in signs)) + " — признак исма."
        return "Называет, но не указывает на время — это исм."
    if seg[1] == "V":
        when = ("повеление" if "IMPV" in f else
                "действие в настоящем или будущем" if "IMPF" in f else "действие в прошлом")
        return _cap(when) + (", " + ", ".join(_SIGN_RU[s] for s in signs) if signs else "") + " — это фиаль."
    return "Смысл даёт только вместе с другими словами — это харф (" + _seg_label(seg) + ")."


def card_view(item, retry=False):
    s, a, pos, idx = item.split(":")
    ayah, word, pos_i, idx_i = corpus().word(item)
    rows = _ayah_words(int(s), int(a))
    compound = any(x[0] and not _is_sign_prefix(x) for i, x in enumerate(word) if i != idx_i)
    words, target_text, meaning = [], "", ""
    for p, text, tr in rows:
        entry = {"t": text}
        if p == pos_i:
            parts = split_by_segments(text, word) if compound else None
            if parts:
                # Слитное слово - выделяется только спрашиваемая часть.
                entry = {"parts": [{"t": pt, "hl": i == idx_i} for i, pt in enumerate(parts)]}
            else:
                entry["hl"] = True
            target_text = text
            meaning = tr if tr and tr.strip() != "*" else ""
        words.append(entry)
    return {"id": item, "ref": "%s:%s" % (s, a), "words": words, "compound": compound,
            "word": target_text, "meaning": meaning, "retry": retry}


def breakdown(item):
    ayah, word, pos, idx = corpus().word(item)
    rows = dict((p, t) for p, t, _ in _ayah_words(*(int(x) for x in item.split(":")[:2])))
    parts = split_by_segments(rows.get(pos, ""), word) or [s[0] for s in word]
    return [{"t": pt, "label": _seg_label(seg), "asked": i == idx} for i, (pt, seg) in enumerate(zip(parts, word))]


# ── Заход ──────────────────────────────────────────────────────────────────

def _load_session(user_id):
    with db() as c:
        row = c.execute("SELECT date, data FROM nahw_sessions WHERE user_id=?", (str(user_id),)).fetchone()
    if not row or row["date"] != get_date():
        return None
    return json.loads(row["data"])


def _save_session(user_id, session):
    with db() as c:
        c.execute("INSERT INTO nahw_sessions(user_id, date, data) VALUES(?,?,?)"
                  " ON CONFLICT(user_id) DO UPDATE SET date=excluded.date, data=excluded.data",
                  (str(user_id), get_date(), json.dumps(session, ensure_ascii=False)))


def _next_card(user_id, session):
    limit, avoid = _pool_limit(user_id), _recent_items(user_id) | set(session["used"])
    if session["asked"] < session["size"]:
        ctype = _choose_ctype(user_id, session["skill"], session["stage"], limit)
        retry, left = False, 0
    elif session["retry"]:
        ctype, left = session["retry"].pop(0)
        retry = True
    else:
        session["current"] = None
        return
    item = ctype and _pick_item(ctype, limit, avoid)
    if not item:
        session["current"] = None
        return
    if not retry:
        session["asked"] += 1
    session["used"].append(item)
    session["current"] = {"item": item, "ctype": ctype, "retry": retry, "left": left,
                          "stage": 2 if ctype.startswith("c_") else 1}


def start(user_id):
    skills = open_skills()
    if not skills:
        return None
    skill = skills[-1]["id"]
    session = {"skill": skill, "stage": stage_of(user_id, skill), "size": SESSION_SIZE,
               "asked": 0, "retry": [], "used": [], "results": [], "current": None}
    _next_card(user_id, session)
    _save_session(user_id, session)
    return session


def _summary(session):
    """Что получается и что стоит повторить - по типам случаев, не счётом."""
    by = {}
    for ctype, ok in session["results"]:
        by.setdefault(ctype, []).append(ok)
    good = [CTYPES[t][1] for t, oks in by.items() if all(oks)]
    weak = [CTYPES[t][1] for t, oks in by.items() if not all(oks)]
    return {"good": good, "weak": weak}


def state(user_id, feedback=None):
    session = _load_session(user_id) or start(user_id)
    out = {"daily_count": daily_count(user_id), "daily_target": DAILY_TARGET,
           "feedback": feedback, "source": "Quranic Arabic Corpus · corpus.quran.com"}
    if session is None:
        out["empty"] = True
        return out
    out["stage"] = session["stage"]
    cur = session["current"]
    if cur is None:
        out["finished"] = dict(_summary(session), size=session["size"],
                               stage_up=session.get("stage_up", False))
        return out
    out["card"] = dict(card_view(cur["item"], cur["retry"]),
                       pos=min(session["asked"], session["size"]), size=session["size"])
    out["options"] = [{"key": k, "ar": ANSWER_AR[k], "ru": ANSWER_RU[k]} for k in ANSWERS]
    return out


def answer(user_id, card_id, choice):
    """(ответ для клиента, достигнута ли норма дня именно этим ответом)."""
    session = _load_session(user_id)
    cur = session["current"] if session else None
    if not cur or cur["item"] != card_id:
        return state(user_id), False          # устаревший или двойной тап
    if choice not in ANSWERS:
        raise ValueError("bad_choice")
    right = CTYPES[cur["ctype"]][0]
    correct = choice == right
    before = daily_count(user_id)
    with db() as c:
        c.execute("INSERT INTO nahw_answers(user_id, date, skill, ctype, stage, item, correct, retry)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (str(user_id), get_date(), session["skill"], cur["ctype"], cur["stage"],
                   cur["item"], int(correct), int(cur["retry"])))
    if not cur["retry"]:
        session["results"].append((cur["ctype"], correct))
    if not correct and cur["left"] < MAX_RETRIES_PER_CARD:
        session["retry"].append((cur["ctype"], cur["left"] + 1))
    reached = before < DAILY_TARGET <= before + int(correct)
    feedback = {"correct": correct, "answer": right, "answer_ar": ANSWER_AR[right],
                "answer_ru": ANSWER_RU[right], "explain": explain(cur["item"]),
                "breakdown": breakdown(cur["item"]), "word": card_view(cur["item"])["word"],
                "meaning": card_view(cur["item"])["meaning"]}
    was_stage = session["stage"]
    _next_card(user_id, session)
    if session["current"] is None and was_stage == 1 and stage_of(user_id, session["skill"]) == 2:
        session["stage_up"] = True
    _save_session(user_id, session)
    return state(user_id, feedback), reached


def new_session(user_id):
    with db() as c:
        c.execute("DELETE FROM nahw_sessions WHERE user_id=?", (str(user_id),))
    return state(user_id)
