"""Пословный словарь «Сорока хадисов» для тренажёра хадисов (23.09.2026).

Два источника, каждый берём за то, в чём он надёжен:

* PDF «40 хадисов» (materials/, прислал пользователь): у каждого хадиса
  таблица «арабский — русский», каждое слово матна по порядку, включая
  частицы и повторы. Русский извлекается чисто, а арабский в PDF побит:
  буквы идут в обратном порядке, огласовки съезжают, лигатура «Аллах»
  теряет букву. Из PDF берём порядок слов и их ПЕРЕВОД.
* sources/arbain/arbain.json (scripts/fetch_arbain_arru.py, архив ar-ru.ru):
  текст хадиса по фразам с огласовками и переводом фразы. Отсюда берём
  арабское слово С ОГЛАСОВКАМИ и смысловой перевод.

Сопоставляем по буквам без огласовок (feedback: арабское сравнивать по
буквам). Что не сопоставилось - в отчёт, руками.

    python scripts/build_arbain.py "materials/<pdf>"      # -> core/arbain.json.gz + отчёт

Ответы не генерируются: и переводы слов, и арабский - из источников.
"""
import difflib
import gzip
import json
import pathlib
import re
import sys

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARRU = ROOT / "sources" / "arbain" / "arbain.json"
OUT = ROOT / "core" / "arbain.json.gz"
REPORT = ROOT / "sources" / "arbain" / "build_report.txt"
# Запасной текст с огласовками - для слов, которых нет в ar-ru (другое
# издание: цитата Корана в 10-м, отдельные слова в 22, 29, 35, 36).
HJSON = ROOT / "sources" / "arbain" / "nawawi40_hadith_json.json"
CONJ = {"و", "ف"}
QURAN = ROOT / "sources" / "quran-simple.txt"
# Хадис цитирует аят - огласовка слов цитаты из текста Корана, не из памяти.
QURAN_QUOTES = {10: ["23|51|", "2|172|"]}
SPELLED_SALAWAT = "صليللاعليهوسلم"

_HARAKAT = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_NOT_LETTER = re.compile(r"[^ء-ي]")
# «Хадис 1.», а с 14-го - «Хадис 14:». С начала строки: «Этот хадис» не заголовок.
HEAD_RE = re.compile(r"^Хадис\s+(\d+)\s*[.:]")


def letters(s, reverse=False):
    """Буквы слова без огласовок, с общим видом алифа/я/та-марбуты."""
    s = _HARAKAT.sub("", s or "")
    s = _NOT_LETTER.sub("", s)
    if reverse:
        s = s[::-1]
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return s


SALAWAT = "ﷺ"                 # ﷺ одним знаком: в тексте это четыре слова
ALLAH = "الله"


def pdf_letters(raw):
    """Буквы слова из ячейки PDF: (обратный порядок, прямой). Буквы там в
    основном в обратном порядке, но лигатуры («لا», «الل» у «Аллах», который
    к тому же теряет последнюю букву) приходят прямыми - сравниваем оба."""
    if SALAWAT in raw:
        return SALAWAT
    rev, fwd = letters(raw, reverse=True), letters(raw)
    rev = re.sub("للا$", ALLAH, rev)
    fwd = re.sub("الل$", ALLAH, fwd)
    return rev + "|" + fwd


def pdf_rows(path):
    """{номер хадиса: [(буквы, русский), ...]} в порядке таблиц."""
    heads, tables = [], []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages):
            for w in page.extract_words(keep_blank_chars=True):
                pass
            text_lines = page.extract_text_lines() if hasattr(page, "extract_text_lines") else []
            for ln in text_lines:
                m = HEAD_RE.search(ln["text"])
                if m:
                    heads.append((pi, ln["top"], int(m.group(1))))
            for t in page.find_tables():
                tables.append((pi, t.bbox[1], t.extract()))
    heads.sort()
    out = {}
    for pi, top, rows in sorted(tables, key=lambda x: (x[0], x[1])):
        owner = None
        for hp, ht, n in heads:
            if (hp, ht) <= (pi, top):
                owner = n
        if owner is None:
            continue
        for r in rows:
            cells = [c for c in r if c not in (None, "")]
            if len(cells) < 2:
                continue
            ar_raw, ru = cells[0], " ".join(cells[1].split())
            if ru.count(")") > ru.count("("):            # «Всеведущий )» - хвост цитаты
                ru = ru.replace(")", "").strip()
            if ru.lower() == "русский":
                continue
            out.setdefault(owner, []).append((pdf_letters(ar_raw), ru))
    return out


def arru_words(h):
    """Слова хадиса из ar-ru: (буквы, с огласовками, № фразы)."""
    words = []
    for i, p in enumerate(h["phrases"]):
        for w in p["ar"].replace("\"", " ").split():
            lt = letters(w)
            if lt:
                words.append((lt, w.strip("،,.:«»\"()[]؛؟"), i))
    return words


def _sim(lt, w):
    if lt == SALAWAT:
        return 1.0 if w == "صلي" else 0.0
    return max(difflib.SequenceMatcher(None, v, w).ratio() for v in lt.split("|"))


def align(pdf, src):
    """Каждому слову PDF - слово ar-ru с огласовками. Глобальное выравнивание
    (как сравнение двух текстов целиком): порядок у обоих один, в ar-ru
    лишнее (иснад, «передал аль-Бухари»), в PDF буквы иногда побиты. Жадный
    проход ошибался каскадом - одна ложная пара сдвигала весь остаток."""
    n, m = len(pdf), len(src)
    SKIP_PDF = -0.4                                # слово PDF без пары
    NEG = float("-inf")
    sim = [[_sim(pdf[i][0], src[k][0]) for k in range(m)] for i in range(n)]
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    for k in range(m + 1):
        dp[0][k] = 0.0                             # пропуск слов ar-ru бесплатен
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + SKIP_PDF
        bk[i][0] = "p"
        for k in range(1, m + 1):
            best, how = dp[i][k - 1], "s"          # пропустить слово ar-ru
            if dp[i - 1][k] + SKIP_PDF > best:
                best, how = dp[i - 1][k] + SKIP_PDF, "p"
            r = sim[i - 1][k - 1]
            if r >= 0.6 and dp[i - 1][k - 1] + r > best:
                best, how = dp[i - 1][k - 1] + r, "m"
            dp[i][k], bk[i][k] = best, how
    pairs, i, k = {}, n, m
    while i > 0:
        how = bk[i][k]
        if how == "m":
            pairs[i - 1] = k - 1
            i, k = i - 1, k - 1
        elif how == "s":
            k -= 1
        else:
            i -= 1
    res, miss = [], 0
    for i, (lt, ru) in enumerate(pdf):
        k = pairs.get(i)
        if k is None:
            res.append({"ar": "ﷺ" if lt == SALAWAT else None, "ru": ru, "ph": None, "sure": 0.0,
                        "pdf_letters": lt})
            miss += lt != SALAWAT
            continue
        ar = src[k][1]
        if lt == SALAWAT and k + 3 < m and src[k + 3][0] == "وسلم":
            ar = " ".join(w[1] for w in src[k:k + 4])
        res.append({"ar": ar, "ru": ru, "ph": src[k][2], "sure": round(sim[i][k], 2)})
    return res, miss


# Правки переводов PDF (23.09.2026, пользователь: «надо поправить»). Только
# опечатки и явные сбои; смысл не трогаем. Где в PDF вместо перевода мусор -
# слово берётся из перевода ФРАЗЫ (ar-ru, Нирша), разложенного по словам.
RU_TYPOS = {
    "он пересилился": "он переселился",
    "пути (путишествия)": "пути (путешествия)",
    "оперался (опёр)": "опёрся (досл. опёр)",
    "в раздумии": "в раздумье",
    "четырери": "четыре",
    "кроме Нег": "кроме Него",
    "и станут выстоивать": "и станут выстаивать",
    "упоминул": "упомянул",
    "вурующим (досл.верует)": "верующим (досл. верует)",
    "и я поститься (досл. постился)": "и я буду поститься (досл. постился)",
    "Я вас наставлю вас": "Я наставлю вас",
    "Я исчесляю": "Я исчисляю",
    "твоем сердцче (досл.твоей груди)": "твоём сердце (досл. твоей груди)",
    "успокаиваеться": "успокаивается",
    "доискиывайте (досл.ищите)": "доискивайтесь (досл. ищите)",
    "снизходит": "нисходит",
    "предерживался": "придерживался",
    "Всевышенный": "Всевышний",
    "если не (пересанешь)": "если не (перестанешь)",
    "ты приобщая (сотоварещей)": "ты, приобщая (сотоварищей)",
    "ко Мной": "ко Мне",
    "не будь непривязан": "будь непривязан",       # 31-й: второе такое же ازهد - «будь непривязан»
    "(досл.введена)": "опущена (досл. введена)",   # фраза: «игла, опущенная в море»
}
# (хадис, слово по буквам) -> перевод, где в PDF вместо него мусор.
RU_BY_WORD = {
    (24, "فتضروني"): "и навредите Мне",           # «ни причинить Мне вред»
    (24, "فتنفعوني"): "и принесёте пользу Мне",    # «ни принести пользу»
    (24, "صعيد"): "месте",                         # «встали на одном месте»
    (10, "ايها"): "(обращение)",                   # после «يَا — О»: своего перевода нет
}


def fix_ru(n, w):
    ru = re.sub(r"[ؐ-ًؚ-ٰٟ]", "", w["ru"]).strip()   # огласовки, прилипшие к русскому
    fixed = RU_BY_WORD.get((n, letters(w["ar"] or "")))
    if fixed and (not re.search("[а-яА-Я]", ru) or ru.isdigit()):
        return fixed
    return RU_TYPOS.get(ru, ru)


def tidy(words, backup):
    """Правки после выравнивания - все по правилам, без угадывания:
    * «[Сура 23:51]» - ссылка, а не слово: убираем;
    * союз «و»/«ف» отдельной строкой («и»), а в тексте он приклеен к
      следующему слову - объединяем: «وَيُقِيمُوا — и совершали»;
    * выписанное «صلى الله عليه وسلم» одной ячейкой - четыре слова;
    * слова, которых нет в ar-ru, - из запасного текста по буквам."""
    out = []
    for w in words:
        if re.match(r"^\[\s*Сура", w["ru"]):
            continue
        out.append(dict(w))
    i = 0
    while i < len(out):
        w = out[i]
        lt = (w.get("pdf_letters") or "").split("|")[0]
        if w["ar"] is None and lt in CONJ and i + 1 < len(out) and out[i + 1]["ar"]                 and letters(out[i + 1]["ar"]).startswith(lt):
            nxt = out[i + 1]
            nxt["ru"] = w["ru"] + " " + nxt["ru"]
            nxt["joined"] = lt
            del out[i]
            continue
        if w["ar"] is None and SPELLED_SALAWAT in (w.get("pdf_letters") or "").replace("ي", "ي"):
            w["ar"], w["sure"] = "صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ", 1.0
        elif w["ar"] is None:
            for v in (w.get("pdf_letters") or "").split("|"):
                hit = backup.get(v)
                if hit:
                    w["ar"], w["sure"], w["src"] = hit, 1.0, "hadith-json"
                    break
        i += 1
    # Слова PDF, которых нет в тексте (другое издание). Тренажёр показывает
    # слово ВНУТРИ текста, поэтому отдельной строкой их не держим: союз
    # отбрасываем, перевод слова - в скобках к соседнему справа.
    i = 0
    while i < len(out):
        w = out[i]
        if w["ar"] is None:
            lt = (w.get("pdf_letters") or "").split("|")[0]
            nxt = out[i + 1] if i + 1 < len(out) else None
            if lt not in CONJ and nxt is not None:
                nxt["ru"] = "(" + w["ru"] + ") " + nxt["ru"]
                nxt["folded"] = lt
            del out[i]
            continue
        i += 1
    return out


def backup_words():
    """{номер: {буквы: слово с огласовками}} из запасного текста."""
    data = json.loads(HJSON.read_text(encoding="utf-8"))
    hs = data["hadiths"] if isinstance(data, dict) else data
    out = {}
    for n, h in enumerate(hs, 1):
        d = {}
        for w in re.split(r"\s+", h["arabic"]):
            w = w.strip("،,.:«»\"()[]؛")
            if letters(w):
                d.setdefault(letters(w), w)
        out[n] = d
    lines = QURAN.read_text(encoding="utf-8").splitlines()
    for n, refs in QURAN_QUOTES.items():
        for ref in refs:
            ayah = next((l[len(ref):] for l in lines if l.startswith(ref)), "")
            for w in ayah.split():
                if letters(w):
                    out[n][letters(w)] = w
    return out


def main():
    pdf_path = sys.argv[1]
    arru = {h["n"]: h for h in json.loads(ARRU.read_text(encoding="utf-8"))}
    rows = pdf_rows(pdf_path)
    backup = backup_words()
    out, report, total, missed = [], [], 0, 0
    for n in sorted(arru):
        h = arru[n]
        words, _ = align(rows.get(n, []), arru_words(h))
        words = tidy(words, backup.get(n, {}))
        for w in words:
            w["ru"] = fix_ru(n, w)
        miss = sum(1 for w in words if w["ar"] is None)
        total += len(words)
        missed += miss
        first_ph = min((w["ph"] for w in words if w["ph"] is not None), default=0)
        report.append("хадис %2d: слов в таблице %3d, не сопоставлено %2d, матн с фразы %d"
                      % (n, len(words), miss, first_ph + 1))
        for i, w in enumerate(words):
            if w["ar"] is None or w["sure"] < 1.0:
                report.append("   #%d %s <- %s  (%s)" % (i + 1, w["ar"] or "?" + w.get("pdf_letters", ""), w["ru"], w["sure"]))
        out.append({"n": n, "words": words,
                    "phrases": [{"ar": p["ar"], "ru": p["ru"]} for p in h["phrases"]],
                    "matn_from": first_ph})
    OUT.write_bytes(gzip.compress(json.dumps(out, ensure_ascii=False).encode("utf-8")))
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("хадисов %d, слов %d, не сопоставлено %d" % (len(out), total, missed))
    print("->", OUT, "; отчёт:", REPORT)


if __name__ == "__main__":
    main()
