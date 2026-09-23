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


def _classify_kinds(word, idx, ayah, pos):
    """Тип случая или None, если эту часть не спрашиваем."""
    seg = word[idx]
    if _is_sign_prefix(seg) or not _askable(seg) or "SUFF" in _feats(seg):
        return None
    rest = [s for i, s in enumerate(word) if i != idx and s[0] and not _is_sign_prefix(s)]
    if rest:
        f = _feats(seg)
        if "PREF" in f:
            return "c_harf_pref" if seg[1] == "P" else None
        return {"N": "c_ism", "V": "c_fil", "P": "c_harf"}[seg[1]]
    f, signs = _feats(seg), _signs(word, idx, ayah, pos)
    if seg[1] == "N":
        for s in ("al", "tanwin", "jarr"):
            if s in signs:
                return "ism_" + s
        return "ism_plain"
    if seg[1] == "V":
        for s in ("qad", "sa", "tat"):
            if s in signs:
                return "fil_" + s
        if "IMPV" in f:
            return "fil_amr"
        return "fil_mudari" if "IMPF" in f else "fil_madi"
    return "harf_jarr" if "P" in f else "harf_other"


# ── Навыки дальше «Видов слова» (17.09.2026) ───────────────────────────────
# Общее правило: спрашиваем только однозначные случаи. Спорное (قَبْلُ/بَعْدُ
# на дамме, إضافة без ال, составные числительные, مضارع с نون التوكيد) в
# вопросы не идёт вовсе - пропустить слово лучше, чем научить ошибке.

def _plain_noun(seg):
    """Обычный исм: не местоимение, не указательное, не наречие и т.п."""
    f = _feats(seg)
    return seg[1] == "N" and bool(seg[0]) and not (f & _SKIP_NOUN) and not _is_allah(f)


def _lemma(seg):
    return next((_letters(x[4:]) for x in seg[2].split("|") if x.startswith("LEM:")), "")


def _classify_signs(word, idx, ayah, pos):
    """Признак исма - только когда он у слова ровно один."""
    seg = word[idx]
    if not _plain_noun(seg) or "SUFF" in _feats(seg):
        return None
    signs = _signs(word, idx, ayah, pos)
    return "sg_" + signs[0] if len(signs) == 1 else None


_NUMBER = {"MS": "s", "FS": "s", "S": "s", "MD": "d", "FD": "d", "D": "d",
           "MP": "p", "FP": "p", "P": "p"}


_COLLECTIVE = {"ناس", "قوم", "نساء", "رهط", "نفر", "اهل", "أهل", "ذريه", "ذرية"}


def _classify_number(word, idx, ayah, pos):
    """Только слова с явной пометкой числа: у «M»/«F» без числа корпус
    единственное не утверждает."""
    seg = word[idx]
    if not _plain_noun(seg) or "PN" in _feats(seg):
        return None
    if _lemma(seg) in _COLLECTIVE:
        return None                   # اسم جمع (ناس، قوم) - не جمع в строгом смысле
    got = [_NUMBER[x] for x in _feats(seg) if x in _NUMBER]
    return "nm_" + got[0] if len(got) == 1 else None


def _classify_tense(word, idx, ayah, pos):
    seg, f = word[idx], _feats(word[idx])
    if seg[1] != "V":
        return None
    return "tn_amr" if "IMPV" in f else "tn_mudari" if "IMPF" in f else "tn_madi"


def _has_emph_nun(word):
    return any("EMPH" in _feats(s) and "SUFF" in _feats(s) for s in word)


_VAGUE_LEMMAS = {"قبل", "بعد", "غير", "مثل", "سوي", "سوى", "شبه", "كل", "بعض", "اي", "أي"}


def _classify_bina(word, idx, ayah, pos):
    seg, f = word[idx], _feats(word[idx])
    if not seg[0]:
        return None
    if seg[1] == "V":
        if _has_emph_nun(word):
            return None               # مبني только при прямом примыкании нуна
        if "PERF" in f:
            return "bn_madi"
        if "IMPV" in f:
            return "bn_amr"
        return "bn_mudari_nun" if f & {"3FP", "2FP"} else "bn_mudari"
    if seg[1] == "P":
        # Буквы внутри ذَٰلِكَ и هَٰذَا (لام البعد، كاف الخطاب، هاء التنبيه) отдельно
        # не спрашиваем - слово показывается целым.
        return None if f & {"DET", "INL", "ADDR", "DIST", "ATT"} else "bn_harf"
    if _is_allah(f):
        return None
    if "PRON" in f:
        return "bn_pron"
    if f & {"DEM", "REL"}:
        return None if f & {"MD", "FD", "D"} else "bn_dem"      # هذان، اللذان - معرب
    if not _plain_noun(seg) or not f & {"NOM", "ACC", "GEN"}:
        return None
    lemma = _lemma(seg)
    if lemma in _VAGUE_LEMMAS or "عشر" in lemma:
        return None
    return "bn_noun"


def _classify_defin(word, idx, ayah, pos):
    seg, f = word[idx], _feats(word[idx])
    if seg[1] != "N" or not seg[0] or _is_allah(f) or "SUFF" in f:
        return None
    if "PRON" in f:
        return "df_pron"
    if f & {"DEM", "REL"}:
        return "df_dem"
    if not _plain_noun(seg):
        return None
    if "PN" in f:
        return "df_pn"
    if any("DET" in _feats(x) for x in word[:idx]):
        return "df_al"
    if _lemma(seg) in _VAGUE_LEMMAS:
        return None                   # غير، مثل и с местоимением остаются نكرة
    if any("PRON" in _feats(x) and "SUFF" in _feats(x) for x in word[idx + 1:]):
        return "df_mudaf"
    return "df_indef" if "INDEF" in f else None


_CASE = {"NOM": "ir_nom", "ACC": "ir_acc", "GEN": "ir_gen"}
_MOOD = {"MOOD:IND": "ir_vind", "MOOD:SUBJ": "ir_vsubj", "MOOD:JUS": "ir_vjus"}


def _classify_irab(word, idx, ayah, pos):
    seg, f = word[idx], _feats(word[idx])
    if seg[1] == "V":
        if "IMPF" not in f or _has_emph_nun(word) or f & {"3FP", "2FP"}:
            return None
        return next((_MOOD[x] for x in f if x in _MOOD), None)
    if _classify_bina(word, idx, ayah, pos) != "bn_noun":
        return None
    return next((_CASE[x] for x in f if x in _CASE), None)


def _opt(key, ar, ru):
    return {"key": key, "ar": ar, "ru": ru}


# Порядок - план Умар устаза (knowledge/нахв): так навыки и открываются.
# lesson - начало темы урока в curriculum_parts; None - письменного урока ещё
# нет, навык открывается только группе, прошедшей тему на лекциях
# (scripts/nahw_start_level.py). Урок написан - вписать сюда его тему.
# ctypes: тип случая -> (ответ, подпись для итога захода).
SKILLS = (
    {"id": "kinds", "lesson": "أنواع الكلمة", "title": "Виды слова", "staged": True,
     "question": "Что это за слово?", "question_part": "Что за выделенная часть слова?",
     "classify": _classify_kinds,
     "options": (_opt("ism", "اسم", "Исм"), _opt("fil", "فعل", "Фиаль"), _opt("harf", "حرف", "Харф")),
     "ctypes": {
         "ism_al": ("ism", "исм с артиклем الـ"), "ism_tanwin": ("ism", "исм с танвином"),
         "ism_jarr": ("ism", "исм после харфа джарр"), "ism_plain": ("ism", "исм без внешнего признака"),
         "fil_qad": ("fil", "фиаль после قَدْ"), "fil_sa": ("fil", "фиаль с سَ / سَوْفَ"),
         "fil_tat": ("fil", "фиаль с تْ на конце"), "fil_madi": ("fil", "фиаль прошедшего времени"),
         "fil_mudari": ("fil", "фиаль настоящего-будущего"), "fil_amr": ("fil", "фиаль-повеление"),
         "harf_jarr": ("harf", "харф джарр"), "harf_other": ("harf", "другие харфы"),
         # Ступень 2 - часть слитного слова.
         "c_harf_pref": ("harf", "харф, прилипший к слову"), "c_ism": ("ism", "исм внутри слитного слова"),
         "c_fil": ("fil", "фиаль внутри слитного слова"), "c_harf": ("harf", "харф с прилипшим местоимением"),
     }},
    {"id": "signs", "lesson": "اسم وعلامته", "title": "Признаки исма",
     "question": "По какому признаку видно, что это исм?", "classify": _classify_signs,
     "options": (_opt("al", "الـ", "Артикль"), _opt("tanwin", "تنوين", "Танвин"), _opt("jarr", "حرف جر", "Харф джарр")),
     "ctypes": {"sg_al": ("al", "признак الـ"), "sg_tanwin": ("tanwin", "признак танвин"),
                "sg_jarr": ("jarr", "признак харф джарр")}},
    {"id": "number", "lesson": "الجمع وأنواعه", "title": "Число",
     "question": "В каком числе стоит слово?", "classify": _classify_number,
     "options": (_opt("s", "مفرد", "Единственное"), _opt("d", "مثنى", "Двойственное"),
                 _opt("p", "جمع", "Множественное")),
     "ctypes": {"nm_s": ("s", "единственное число"), "nm_d": ("d", "двойственное число"),
                "nm_p": ("p", "множественное число")}},
    {"id": "tense", "lesson": None, "title": "Время глагола",
     "question": "Какой это глагол?", "classify": _classify_tense,
     "options": (_opt("madi", "ماض", "Прошедшее"), _opt("mudari", "مضارع", "Наст.-будущее"),
                 _opt("amr", "أمر", "Повеление")),
     "ctypes": {"tn_madi": ("madi", "глагол ماض"), "tn_mudari": ("mudari", "глагол مضارع"),
                "tn_amr": ("amr", "глагол أمر")}},
    {"id": "bina", "lesson": None, "title": "معرب и مبني",
     "question": "معرب или مبني?", "classify": _classify_bina,
     "options": (_opt("murab", "معرب", "Конец меняется"), _opt("mabni", "مبني", "Конец не меняется")),
     "ctypes": {"bn_noun": ("murab", "исм — معرب"), "bn_mudari": ("murab", "مضارع — معرب"),
                "bn_madi": ("mabni", "ماض — مبني"), "bn_amr": ("mabni", "أمر — مبني"),
                "bn_mudari_nun": ("mabni", "مضارع с نون النسوة"), "bn_harf": ("mabni", "харфы — مبني"),
                "bn_pron": ("mabni", "местоимения — مبني"), "bn_dem": ("mabni", "указательные и относительные")}},
    {"id": "defin", "lesson": None, "title": "معرفة и نكرة",
     "question": "معرفة или نكرة?", "classify": _classify_defin,
     "options": (_opt("marifa", "معرفة", "Определённое"), _opt("nakira", "نكرة", "Неопределённое")),
     "ctypes": {"df_al": ("marifa", "معرفة с الـ"), "df_pn": ("marifa", "имя собственное"),
                "df_pron": ("marifa", "местоимение"), "df_dem": ("marifa", "указательные и относительные"),
                "df_mudaf": ("marifa", "исм с прилипшим местоимением"), "df_indef": ("nakira", "نكرة с танвином")}},
    {"id": "irab", "lesson": None, "title": "Иъраб",
     "question": "Какой иъраб у слова?", "classify": _classify_irab,
     "options": (_opt("raf", "مرفوع", "Раф‘"), _opt("nasb", "منصوب", "Насб"),
                 _opt("jarr", "مجرور", "Джарр"), _opt("jazm", "مجزوم", "Джазм")),
     "ctypes": {"ir_nom": ("raf", "исм مرفوع"), "ir_acc": ("nasb", "исм منصوب"), "ir_gen": ("jarr", "исм مجرور"),
                "ir_vind": ("raf", "مضارع مرفوع"), "ir_vsubj": ("nasb", "مضارع منصوب"),
                "ir_vjus": ("jazm", "مضارع مجزوم")}},
)
_SKILL = {s["id"]: s for s in SKILLS}


def _stage(ctype):
    return 2 if ctype.startswith("c_") else 1


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
        self.index = {}          # skill -> ctype -> ([ord...], [item...])
        if data.get("index"):
            # Собран scripts/build_nahw_corpus.py: разбор всех слов на ходу
            # занимает секунды, а первый вход после рестарта ждать не должен.
            self.index = {sk: {t: (o, i) for t, (o, i) in types.items()}
                          for sk, types in data["index"].items()}
            return
        for key in keys:
            ayah = self.ayat[key]
            for pos in sorted(ayah, key=int):
                word = ayah[pos]
                for idx in range(len(word)):
                    for skill in SKILLS:
                        ctype = skill["classify"](word, idx, ayah, int(pos))
                        if not ctype:
                            continue
                        ords, items = self.index.setdefault(skill["id"], {}).setdefault(ctype, ([], []))
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

def _published_topics(user_id=None):
    """Темы лекций, открытых группе этого человека (17.09.2026,
    core/curriculum.py); устазу и без user_id - всё опубликованное в базе."""
    try:
        from core.curriculum import topics, user_group_id
        return topics("n", user_group_id(user_id) if user_id else None)
    except Exception as e:
        log.error("nahw topics error: %s: %s", type(e).__name__, e)
        return []


def group_passed(group_id):
    """Сколько первых навыков группа прошла на лекциях (scripts/nahw_start_level.py)."""
    with db() as c:
        row = c.execute("SELECT passed FROM nahw_group_start WHERE group_id=?", (group_id,)).fetchone()
    return row["passed"] if row else 0


def set_group_passed(group_id, passed):
    with db() as c:
        c.execute("INSERT INTO nahw_group_start(group_id, passed) VALUES(?,?)"
                  " ON CONFLICT(group_id) DO UPDATE SET passed=excluded.passed", (group_id, passed))


def open_skills(user_id=None, passed=0):
    """Навыки по порядку, пока цепочка не прервётся. Первые `passed` открыты
    лекциями. Дальше шаг за шагом: урок навыка опубликован в этой базе И
    предыдущий навык освоен (первому навыку хватает урока)."""
    topics, out = _published_topics(user_id), []
    for i, skill in enumerate(SKILLS):
        if i >= passed:
            if not skill["lesson"] or not any(t.startswith(skill["lesson"]) for t in topics):
                break
            if i > 0 and i - 1 >= passed and not (user_id and skill_mastered(user_id, SKILLS[i - 1]["id"])):
                break
        out.append(skill)
    return out


def _pool_limit(user_id):
    """Порядковый номер последнего аята пула: страница заучивания, иначе
    закладка «Слов», но не меньше MIN_POOL_PAGE."""
    from core.quran_pages import last_ayah_on_page, LAST_PAGE
    page = None
    try:
        from core.mushaf_words import get_hifz_pointer
        ptr = get_hifz_pointer(str(user_id))
        page = ptr and (ptr.get("madani_page") or ptr["page"])
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
    if not _SKILL[skill].get("staged"):
        return 1
    return 2 if _mastered(_first_try_history(user_id, skill, stage=1)) else 1


def skill_mastered(user_id, skill="kinds"):
    """Для открытия следующего навыка: 85% на последних 40 (у «Видов слова» -
    на второй ступени)."""
    if _SKILL[skill].get("staged"):
        return stage_of(user_id, skill) == 2 and _mastered(_first_try_history(user_id, skill, stage=2))
    return _mastered(_first_try_history(user_id, skill))


def daily_count(user_id):
    with db() as c:
        row = c.execute("SELECT count(*) n FROM nahw_answers WHERE user_id=? AND date=? AND correct=1",
                        (str(user_id), get_date())).fetchone()
    return row["n"]


def _weakness(user_id, skill, ctype=None):
    h = _first_try_history(user_id, skill, ctype=ctype, limit=WEAKNESS_WINDOW)
    return (len(h) - sum(h) + 1) / (len(h) + 2)


def _recent_items(user_id):
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT item FROM nahw_answers WHERE user_id=?"
            " AND created_at >= datetime('now', ?)",
            (str(user_id), "-%d days" % ITEM_REST_DAYS)).fetchall()
    return {r["item"] for r in rows}


def _pick_item(skill, ctype, limit, avoid):
    ords, items = corpus().index.get(skill, {}).get(ctype, ([], []))
    n = bisect.bisect_right(ords, limit)
    if not n:
        return None
    for _ in range(30):
        item = items[random.randrange(n)]
        if item not in avoid:
            return item
    return items[random.randrange(n)]


def _choose_skill(user_id, skills, passed):
    """Новый навык (открытый успехами, ещё не освоенный) - втрое чаще:
    примерно 6 карточек из 10. Остальные - на повторение, слабое чаще."""
    if len(skills) == 1:
        return skills[0]["id"]
    ids = [s["id"] for s in skills]
    return random.choices(ids, _skill_weights(user_id, ids, passed))[0]


def _skill_weights(user_id, ids, passed):
    weights = [0.3 + _weakness(user_id, sid) for sid in ids]
    last = len(ids) - 1
    if last >= passed and not skill_mastered(user_id, ids[last]):
        # Не меньше 60% захода, но и не урезать, если слабость уже дала больше.
        weights[last] = max(weights[last], 1.5 * sum(weights[:last]))
    return weights


def _choose_ctype(user_id, skill, stage, limit):
    """Сначала ответ, потом тип случая внутри него - оба выбора взвешены
    слабостью. Без первого шага чаще выпадал бы ответ, у которого просто
    больше типов случаев."""
    ctypes, index = _SKILL[skill]["ctypes"], corpus().index.get(skill, {})
    open_types = [t for t in ctypes
                  if _stage(t) <= stage and bisect.bisect_right(index.get(t, ([], []))[0], limit)]
    if not open_types:
        return None
    weak = {t: _weakness(user_id, skill, t) for t in open_types}
    # Новая ступень, пока к ней не привык, - вдвое чаще.
    if stage == 2 and len(_first_try_history(user_id, skill, stage=2)) < MASTERY_WINDOW:
        for t in weak:
            if _stage(t) == 2:
                weak[t] *= 2
    by_answer = {}
    for t in open_types:
        by_answer.setdefault(ctypes[t][0], []).append(t)
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


_EXPLAIN = {
    "sg_al": "В начале слова الـ — это признак исма.",
    "sg_tanwin": "На конце танвин — это признак исма.",
    "sg_jarr": "Перед словом харф джарр — это признак исма.",
    "nm_s": "Слово указывает на одного или одно — مفرد.",
    "nm_d": "Слово указывает на двоих — مثنى: на конце ـَانِ или ـَيْنِ (нун уходит при إضافة).",
    "nm_p": "Слово указывает на троих и больше — جمع.",
    "tn_madi": "Действие уже произошло — ماض.",
    "tn_mudari": "Начинается с одной из букв أ ن ي ت, действие идёт или будет — مضارع.",
    "tn_amr": "Повеление — أمر.",
    "bn_noun": "Конец этого исма меняется по месту в предложении — معرب.",
    "bn_mudari": "مضارع без نون النسوة и نون التوكيد — معرب.",
    "bn_madi": "الماضي всегда مبني.",
    "bn_amr": "الأمر всегда مبني.",
    "bn_mudari_nun": "К مضارع примкнула نون النسوة — он становится مبني.",
    "bn_harf": "Все харфы — مبني.",
    "bn_pron": "Все местоимения — مبني.",
    "bn_dem": "Указательные и относительные имена (кроме двойственных) — مبني.",
    "df_al": "С الـ слово становится معرفة.",
    "df_pn": "Имя собственное — معرفة.",
    "df_pron": "Местоимение — معرفة.",
    "df_dem": "Указательные и относительные имена — معرفة.",
    "df_mudaf": "К слову присоединено местоимение (إضافة) — оно معرفة.",
    "df_indef": "Танвин, нет ни الـ, ни إضافة — نكرة.",
    "ir_nom": "По месту в предложении это слово — مرفوع.",
    "ir_acc": "По месту в предложении это слово — منصوب.",
    "ir_gen": "После харфа джарр или как مضاف إليه — مجرور.",
    "ir_vind": "Перед مضارع нет ни ناصب, ни جازم — مرفوع.",
    "ir_vsubj": "Перед مضارع стоит ناصب (أَنْ، لَنْ، كَيْ، حَتَّى، لِـ) — منصوب.",
    "ir_vjus": "مضارع под جازم (لَمْ، لَا الناهية، условие и его ответ) — مجزوم.",
}


def explain(item, ctype=None):
    """Одна-две строки словами уроков."""
    if ctype in _EXPLAIN:
        return _EXPLAIN[ctype]
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


_GLUE = {"DET", "ADDR", "DIST", "ATT"}
# Спрашиваем про слово целиком, хотя корпус режет его на части: у
# يُؤْمِنَّ нун корня слит с نون النسوة, половина слова выглядела бы ошибкой.
_WHOLE_WORD = {"bn_mudari_nun"}


def _highlighted(word, idx, ctype=None):
    """Спрашиваемая часть вместе с приросшими к ней буквами (ال، سَ، ذَٰ+لِ+كَ)."""
    if ctype in _WHOLE_WORD:
        return set(range(len(word)))
    glue = lambda seg: bool(_feats(seg) & _GLUE) or _is_sign_prefix(seg) or not seg[0]
    out, i = {idx}, idx - 1
    while i >= 0 and glue(word[i]):
        out.add(i)
        i -= 1
    i = idx + 1
    while i < len(word) and glue(word[i]):
        out.add(i)
        i += 1
    return out


def card_view(item, retry=False, ctype=None):
    s, a, pos, idx = item.split(":")
    ayah, word, pos_i, idx_i = corpus().word(item)
    rows = _ayah_words(int(s), int(a))
    hl = _highlighted(word, idx_i, ctype)
    compound = any(x[0] for i, x in enumerate(word) if i not in hl)
    words, target_text, meaning = [], "", ""
    for p, text, tr in rows:
        entry = {"t": text}
        if p == pos_i:
            parts = split_by_segments(text, word) if compound else None
            if parts:
                # Слитное слово - выделяется только спрашиваемая часть.
                entry = {"parts": [{"t": pt, "hl": i in hl} for i, pt in enumerate(parts)]}
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
    session = json.loads(row["data"])
    # Заход, сохранённый до навыков (17.09.2026), - без «skill» у карточки:
    # такой начинаем заново, иначе экран висит на «Загрузке».
    if "open" not in session or (session.get("current") and "skill" not in session["current"]):
        return None
    return session


def _save_session(user_id, session):
    with db() as c:
        c.execute("INSERT INTO nahw_sessions(user_id, date, data) VALUES(?,?,?)"
                  " ON CONFLICT(user_id) DO UPDATE SET date=excluded.date, data=excluded.data",
                  (str(user_id), get_date(), json.dumps(session, ensure_ascii=False)))


def _next_card(user_id, session):
    limit, avoid = _pool_limit(user_id), _recent_items(user_id) | set(session["used"])
    passed = session.get("passed", 0)
    if session["asked"] < session["size"]:
        skills = open_skills(user_id, passed)
        skill = _choose_skill(user_id, skills, passed) if skills else None
        ctype = skill and _choose_ctype(user_id, skill, stage_of(user_id, skill), limit)
        retry, left = False, 0
    elif session["retry"]:
        skill, ctype, left = session["retry"].pop(0)
        retry = True
    else:
        session["current"] = None
        return
    item = ctype and _pick_item(skill, ctype, limit, avoid)
    if not item:
        session["current"] = None
        return
    if not retry:
        session["asked"] += 1
    session["used"].append(item)
    session["current"] = {"skill": skill, "item": item, "ctype": ctype, "retry": retry,
                          "left": left, "stage": _stage(ctype)}


def start(user_id, passed=0):
    skills = open_skills(user_id, passed)
    if not skills:
        return None
    session = {"passed": passed, "size": SESSION_SIZE, "asked": 0, "retry": [], "used": [],
               "results": [], "current": None,
               "open": [s["id"] for s in skills], "stage": stage_of(user_id)}
    _next_card(user_id, session)
    _save_session(user_id, session)
    return session


def _summary(session):
    """Что получается и что стоит повторить - по типам случаев, не счётом."""
    by = {}
    for skill, ctype, ok in session["results"]:
        by.setdefault((skill, ctype), []).append(ok)
    label = lambda k: _SKILL[k[0]]["ctypes"][k[1]][1]
    return {"good": [label(k) for k, oks in by.items() if all(oks)],
            "weak": [label(k) for k, oks in by.items() if not all(oks)]}


def right_answer(cur):
    return _SKILL[cur["skill"]]["ctypes"][cur["ctype"]][0]


def state(user_id, feedback=None, passed=0):
    session = _load_session(user_id) or start(user_id, passed)
    out = {"daily_count": daily_count(user_id), "daily_target": DAILY_TARGET,
           "feedback": feedback, "source": "Quranic Arabic Corpus · corpus.quran.com"}
    if session is None:
        out["empty"] = True
        return out
    cur = session["current"]
    if cur is None:
        out["finished"] = dict(_summary(session), size=session["size"],
                               stage_up=session.get("stage_up", False),
                               new_skill=session.get("new_skill"))
        return out
    skill = _SKILL[cur["skill"]]
    view = card_view(cur["item"], cur["retry"], cur["ctype"])
    out["card"] = dict(view, id=cur["skill"] + "|" + cur["item"], skill=skill["title"],
                       question=skill.get("question_part", skill["question"]) if view["compound"]
                       else skill["question"],
                       pos=min(session["asked"], session["size"]), size=session["size"])
    out["options"] = list(skill["options"])
    return out


def answer(user_id, card_id, choice, passed=0):
    """(ответ для клиента, достигнута ли норма дня именно этим ответом)."""
    session = _load_session(user_id)
    cur = session["current"] if session else None
    if not cur or cur["skill"] + "|" + cur["item"] != card_id:
        return state(user_id, passed=passed), False          # устаревший или двойной тап
    skill = _SKILL[cur["skill"]]
    if choice not in [o["key"] for o in skill["options"]]:
        raise ValueError("bad_choice")
    right = right_answer(cur)
    correct = choice == right
    before = daily_count(user_id)
    with db() as c:
        # Первая встреча с этим типом случая: приложение не листает карточку
        # само даже после верного ответа - правило надо раз увидеть спокойно.
        first_meet = not c.execute("SELECT 1 FROM nahw_answers WHERE user_id=? AND skill=? AND ctype=? LIMIT 1",
                                   (str(user_id), cur["skill"], cur["ctype"])).fetchone()
        c.execute("INSERT INTO nahw_answers(user_id, date, skill, ctype, stage, item, correct, retry)"
                  " VALUES(?,?,?,?,?,?,?,?)",
                  (str(user_id), get_date(), cur["skill"], cur["ctype"], cur["stage"],
                   cur["item"], int(correct), int(cur["retry"])))
    if not cur["retry"]:
        session["results"].append((cur["skill"], cur["ctype"], correct))
    if not correct and cur["left"] < MAX_RETRIES_PER_CARD:
        session["retry"].append((cur["skill"], cur["ctype"], cur["left"] + 1))
    reached = before < DAILY_TARGET <= before + int(correct)
    opt = next(o for o in skill["options"] if o["key"] == right)
    view = card_view(cur["item"])
    feedback = {"correct": correct, "first_meet": first_meet, "answer": right, "answer_ar": opt["ar"], "answer_ru": opt["ru"],
                "explain": explain(cur["item"], cur["ctype"]), "breakdown": breakdown(cur["item"]),
                "word": view["word"], "meaning": view["meaning"]}
    _next_card(user_id, session)
    if session["current"] is None:
        # Итог захода говорит о новом один раз - в тот заход, где оно открылось.
        if session.get("stage") == 1 and stage_of(user_id) == 2:
            session["stage_up"] = True
        now_open = open_skills(user_id, session.get("passed", 0))
        fresh = [s["title"] for s in now_open if s["id"] not in session.get("open", [])]
        if fresh:
            session["new_skill"] = fresh[-1]
    _save_session(user_id, session)
    return state(user_id, feedback, passed), reached


def new_session(user_id, passed=0):
    with db() as c:
        c.execute("DELETE FROM nahw_sessions WHERE user_id=?", (str(user_id),))
    return state(user_id, passed=passed)
