"""Экспорт данных страницы мусхафа (арабский текст с таджвидной разметкой +
пословный перевод) в JSON для веб-страницы Mini App (мусхаф-ридер, 27.08.2026).

Таджвидная разметка - РЕАЛЬНЫЙ источник (api.quran.com, официальный API
проекта Quran.com), не собственная генерация/детекция - см.
feedback_never_invent_quran_translations в памяти, тот же принцип
распространяется и на таджвид (неверная разметка собьёт человека при
чтении, это серьёзнее, чем ошибка в переводе).

Выравнивание слов: API отдаёт цельный HTML-текст аята с вкраплёнными
<tajweed class=...>...</tajweed> спанами. Разбиваем по пробелам на токены:
  - "۞" (маркер четверти/хизба, чисто типографский) - отдельный тип
    "marker", не участвует в тап-переводе
  - <span class=end>N</span> (номер аята) - извлекается ДО разбивки по
    пробелам (у него внутри тега есть буквальный пробел - "class=end", а
    не "class=end" - ломает наивный split), отдельный тип "ayah_end"
  - всё остальное - слова, по порядку сопоставляются с позициями в нашей
    mufradat_words (проверено эмпирически 27.08.2026: 0 расхождений в
    счёте слов на всех 69 аятах сур 2, кроме самого ۞, который правильно
    исключён из подсчёта)

Источник перевода - наша mufradat_words (language='ru', тот же движок,
что у тренажёра муфрадата) - подключение к прогрессу/закладке студента
делается в самом веб-приложении, не здесь (этот скрипт - чистый экспорт
статики).

Запускать вручную:
    python scripts/export_mushaf_page.py
"""
import json
import re
import sys
import time

import requests

# Консоль Windows по умолчанию cp1251 - print() с арабским/кириллицей в
# одной строке (например текст ошибки с непопавшим словом) валит скрипт
# UnicodeEncodeError-ом ДО того, как per-page try/except в main() успевает
# сработать (28.08.2026, поймано на первом полном прогоне 1-604 - страница
# упала не из-за самой ошибки данных, а из-за краша при её печати).
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, ".")
from core.sampler import HADITHS_DB
import sqlite3
import quran_transcript as qt

START_PAGE = 1
END_PAGE = 604  # весь мусхаф (28.08.2026) - см. модульный docstring про
# развязку от core.quran_pages.PAGES (тот остаётся 2-221, только для
# тренажёра муфрадата - см. build_lines/export_page ниже)
SOURCE_LANGUAGE = "ru"

# Пословные глиф-коды шрифта QPC V4 Tajweed (King Fahd Complex, цвета
# таджвида зашиты В САМ ШРИФТ через COLR/CPAL, не через CSS) - датасет QUL
# "V4 Glyphs(With Tajweed) - Word by word", получен пользователем через его
# аккаунт QUL 27.08.2026 (лицензионное разрешение подтверждено пользователем
# лично - "я проверил, они дают зелёный цвет"). Ключ - "сура:аят:позиция",
# позиция включает служебный номер аята (N+1-й "word" после N реальных слов
# - проверено эмпирически на 7:206, сура с меткой суджуда: 11 слов + 1
# номер аята = 12 записей, ни ۞, ни ۩ отдельного слота не занимают).
QPC_V4_GLYPHS_PATH = "sources/qpc_v4_extract/qpc-v4.json"
_glyphs = None


def _load_glyphs():
    global _glyphs
    if _glyphs is None:
        with open(QPC_V4_GLYPHS_PATH, encoding="utf-8") as f:
            _glyphs = json.load(f)
    return _glyphs


def get_code_v4(surah, ayah, position):
    return _load_glyphs().get(f"{surah}:{ayah}:{position}", {}).get("text")


def font_url_for_page(page_number, fmt="woff2"):
    """Хотлинк на CDN QUL (static-cdn.tarteel.ai), НЕ самохостинг - так и
    задокументировано в их же примере @font-face на странице ресурса.
    Убирает вопрос переразмещения 604 файлов и синхронизации с CI."""
    return f"https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/{fmt}/p{page_number}.{fmt}"

# Типографские маркеры мусхафа, не являющиеся словами - при разбивке на
# чанки идут как отдельные токены, не сопоставляются со строками
# mufradat_words. ۞ (رub el-hizb, начало четверти) ловили сразу, ۩ (место
# обязательного суджуда) поймали на первом полном прогоне 220 страниц
# (сура 7, аят 206 - единственный сбой из 1464 аятов).
_MARKER_CHARS = {"۞", "۩"}
OUT_DIR = "mushaf_data"

_END_SPAN_RE = re.compile(r"<span class=end>([^<]*)</span>")
_TAG_OR_TEXT_RE = re.compile(r"(<[^>]+>)")


def _tokenize_arabic_html(body):
    """Разбивает HTML-текст аята на слова-чанки по ПРОБЕЛАМ ВНЕ тегов, с
    закрытием/переоткрытием тегов на границе слова.

    Два независимых бага, оба пойманы 27.08.2026 на первом же тесте, до
    выкладки:
    1) Наивный body.split() ломается на <tajweed class=...> - у этого тега
       ЕСТЬ буквальный пробел внутри (между "tajweed" и "class="). Чиним
       через re.split с захватывающей группой на теги - чередование
       [текст, тег, текст, тег, ...], тег всегда целиком в нечётной
       позиции, пробелы внутри него не видны как разделители.
    2) Некоторые правила таджвида (идгам и т.п.) грамматически связывают
       КОНЕЦ одного слова с НАЧАЛОМ следующего - <tajweed>-спан у API
       пересекает границу слова. Если резать по словам как есть, одно
       слово получит незакрытый открывающий тег, соседнее - висячий
       закрывающий - невалидный HTML при рендере каждого слова отдельным
       DOM-узлом (нужно для тап-перевода). Отслеживаем стек открытых
       тегов и на каждой границе слова ЗАКРЫВАЕМ их (конец текущего
       чанка) и ПЕРЕОТКРЫВАЕМ теми же тегами (начало следующего) - тот
       же класс/цвет с обеих сторон, визуально непрерывно, при этом
       каждое слово - валидный самостоятельный HTML-фрагмент."""
    parts = _TAG_OR_TEXT_RE.split(body)
    chunks = []
    current = ""
    open_stack = []

    def push_chunk():
        nonlocal current
        if current:
            chunks.append(current + "</tajweed>" * len(open_stack))
        current = "".join(open_stack)

    for i, part in enumerate(parts):
        if i % 2 == 1:
            if part == "</tajweed>":
                if open_stack:
                    open_stack.pop()
            else:
                open_stack.append(part)
            current += part
            continue
        if not part:
            continue
        pieces = re.split(r"\s+", part)
        current += pieces[0]
        for piece in pieces[1:]:
            push_chunk()
            current += piece
    if current:
        chunks.append(current + "</tajweed>" * len(open_stack))
    return chunks


def fetch_tajweed_ayah(surah, ayah, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(
                "https://api.quran.com/api/v4/quran/verses/uthmani_tajweed",
                params={"verse_key": f"{surah}:{ayah}"}, timeout=20
            )
            r.raise_for_status()
            return r.json()["verses"][0]["text_uthmani_tajweed"]
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise


def parse_ayah_tokens(raw_html, words, surah, ayah, missing_glyphs):
    """raw_html - text_uthmani_tajweed сырой из API. words - позиции этого
    аята (position, arabic_text, translation), по порядку. surah/ayah -
    для поиска глиф-кодов v4 (get_code_v4); missing_glyphs - список,
    в который дописываются пропуски (для отчёта, не бросаем исключение -
    страница чтения деградирует до обычного текста на конкретном слове,
    не роняет весь экспорт). Возвращает список токенов для рендера."""
    end_match = _END_SPAN_RE.search(raw_html)
    ayah_end_glyph = end_match.group(1) if end_match else ""
    body = _END_SPAN_RE.sub("", raw_html).strip()

    chunks = [c for c in _tokenize_arabic_html(body) if c.strip()]
    tokens = []
    word_iter = iter(words)
    for chunk in chunks:
        if chunk in _MARKER_CHARS:
            tokens.append({"type": "marker", "html": chunk})
            continue
        w = next(word_iter, None)
        if w is None:
            raise ValueError("больше токенов-слов, чем позиций в аяте")
        code_v4 = get_code_v4(surah, ayah, w["position"])
        if code_v4 is None:
            missing_glyphs.append((surah, ayah, w["position"]))
        tokens.append({
            "type": "word", "html": chunk,
            "position": w["position"], "translation": w["translation"],
            "code_v4": code_v4,
        })
    leftover = list(word_iter)
    if leftover:
        raise ValueError(f"остались несопоставленные слова: {leftover}")

    if ayah_end_glyph:
        end_position = len(words) + 1
        code_v4 = get_code_v4(surah, ayah, end_position)
        if code_v4 is None:
            missing_glyphs.append((surah, ayah, end_position))
        tokens.append({"type": "ayah_end", "html": ayah_end_glyph, "code_v4": code_v4})
    return tokens


def get_ayah_words(conn, surah, ayah):
    """Позиции слов аята - из quran_transcript (весь Коран, надёжно), НЕ из
    mufradat_words (та покрывает только суры 2-10, язык SOURCE_LANGUAGE, и
    раньше была единственным источником, из-за чего страница чтения не
    могла выйти за эти суры - см. модульный docstring, решение 28.08.2026).
    Перевод подмешивается из mufradat_words, если есть - иначе пустая
    строка, вкладка "Слова" на непереведённых страницах просто не покажет
    перевод, само чтение не блокируется."""
    arabic_words = qt.Aya(surah, ayah).get().uthmani_words
    translations = {
        row["position"]: row["translation"]
        for row in conn.execute(
            "SELECT position, translation FROM mufradat_words "
            "WHERE surah_number=? AND ayah_number=? AND language=?",
            (surah, ayah, SOURCE_LANGUAGE)
        )
    }
    return [
        {"position": i, "arabic_text": w, "translation": translations.get(i, "")}
        for i, w in enumerate(arabic_words, 1)
    ]


QUL_LAYOUT_URL = "https://raw.githubusercontent.com/zonetecde/mushaf-layout/refs/heads/main/mushaf/page-{:03d}.json"


def fetch_qul_layout(page_number, retries=3):
    """QUL (Quranic Universal Library, TarteelAI) - разбивка настоящего
    печатного мусхафа (King Fahd Complex, 15 строк/страница) на строки.
    Группировка слов по строкам (location "сура:аят:позиция" - совпадает
    1-в-1 с нашей нумерацией, проверено эмпирически 27.08.2026 на 76 аятах,
    0 расхождений), а с 28.08.2026 ЭТИ ЖЕ данные (words[].location) - ещё и
    источник границ аятов на странице (см. ayah_ranges_from_qul), вместо
    ручной core.quran_pages.PAGES (та осталась только для тренажёра
    муфрадата, 2-221 - см. модульный docstring). Шрифт V4 (глиф-коды) -
    отдельный датасет QUL "V4 Glyphs (With Tajweed)", см. get_code_v4."""
    url = QUL_LAYOUT_URL.format(page_number)
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise


def ayah_ranges_from_qul(qul):
    """[(surah, start_ayah, end_ayah), ...] для страницы - выведено из тех
    же QUL-строк, что и построчная разметка (words[].location), вместо
    core.quran_pages.resolve_page (та ограничена сурами 2-10 - см.
    fetch_qul_layout). Один аят на печатной странице мусхафа никогда не
    разрывается между сурами не по границе - берём просто min/max аята на
    суру в порядке появления строк."""
    order = []
    bounds = {}
    for qline in qul["lines"]:
        if qline["type"] != "text":
            continue
        for w in qline.get("words", []):
            s, a, _ = (int(x) for x in w["location"].split(":"))
            if s not in bounds:
                order.append(s)
                bounds[s] = [a, a]
            else:
                bounds[s][0] = min(bounds[s][0], a)
                bounds[s][1] = max(bounds[s][1], a)
    return [(s, bounds[s][0], bounds[s][1]) for s in order]


def build_lines(ayahs_out, qul):
    """Строит lines[] (реальная построчная вёрстка) поверх уже готовых
    ayahs_out (наш текст/таджвид/перевод). line_of - откуда какое слово по
    QUL, маркеры/номер аята (нет своей позиции в mufradat_words) наследуют
    строку ПРЕДЫДУЩЕГО токена - они всегда идут сразу после/между словами
    в потоке, это надёжно (проверено на всех страницах диапазона)."""
    line_of = {}
    line_meta = {}
    last_header_surah = None
    for qline in qul["lines"]:
        n = qline["line"]
        if qline["type"] == "text":
            for w in qline.get("words", []):
                s, a, p = (int(x) for x in w["location"].split(":"))
                line_of[(s, a, p)] = n
        elif qline["type"] == "surah-header":
            surah_num = int(qline["surah"])
            last_header_surah = surah_num
            line_meta[n] = {
                "type": "header", "surah": surah_num,
                "surah_name_ar": qt.Aya(surah_num, 1).get().sura_name,
            }
        elif qline["type"] == "basmala":
            bismillah = None
            if last_header_surah:
                bismillah = qt.Aya(last_header_surah, 1).get().bismillah_uthmani
            line_meta[n] = {"type": "bismillah", "html": bismillah}

    lines_out = []
    current_tokens = []
    current_line = None

    def flush():
        if current_line is not None:
            lines_out.append({"line": current_line, "type": "text", "tokens": current_tokens[:]})

    for entry in ayahs_out:
        surah, ayah = entry["surah"], entry["ayah"]
        for t in entry["tokens"]:
            if t["type"] == "word":
                n = line_of.get((surah, ayah, t["position"]), current_line)
            else:
                n = current_line
            if n is None:
                n = 0
            if n != current_line:
                flush()
                current_tokens = []
                current_line = n
            current_tokens.append(t)
    flush()

    for n, meta in line_meta.items():
        lines_out.append({"line": n, **meta})
    lines_out.sort(key=lambda l: l["line"])
    return lines_out


def export_page(conn, page_number):
    qul = fetch_qul_layout(page_number)
    entries = ayah_ranges_from_qul(qul)
    if not entries:
        return None

    ayahs_out = []
    missing_glyphs = []
    skipped_ayat = []
    for surah, start_ayah, end_ayah in entries:
        for ayah in range(start_ayah, end_ayah + 1):
            words = get_ayah_words(conn, surah, ayah)
            raw = fetch_tajweed_ayah(surah, ayah)
            try:
                tokens = parse_ayah_tokens(raw, words, surah, ayah, missing_glyphs)
            except ValueError as e:
                # Расхождение в счёте слов между quran_transcript (words) и
                # токенизацией tajweed-HTML от api.quran.com (та же природа
                # проблемы, что и в scripts/ingest_mufradat.py - два
                # независимых источника иногда расходятся на конкретном
                # аяте). Не гадаем - пропускаем аят целиком (страница
                # чтения покажет дыру ровно в этом месте, не выдуманный
                # текст), логируем для отдельного разбора.
                skipped_ayat.append((surah, ayah, str(e)))
                continue
            entry = {"surah": surah, "ayah": ayah, "tokens": tokens}
            if ayah == 1:
                # Бисмилля - реальный текст из quran_transcript (тот же
                # источник, что и арабский текст слов, core/quran_ref.py),
                # не сочиняем сами. У суры 9 (Ат-Тауба) её традиционно нет -
                # quran_transcript честно отдаёт None, ничего не добавляем.
                # Дублируется в build_lines (для Page view) - тут остаётся
                # для Words view, которому построчная разбивка не нужна.
                bismillah = qt.Aya(surah, 1).get().bismillah_uthmani
                if bismillah:
                    entry["bismillah"] = bismillah
            ayahs_out.append(entry)
            time.sleep(0.1)

    lines = build_lines(ayahs_out, qul)

    surah_numbers = sorted({e[0] for e in entries})
    if missing_glyphs:
        print(f"  страница {page_number}: нет глиф-кода v4 для {len(missing_glyphs)} "
              f"позиций: {missing_glyphs[:5]}{'...' if len(missing_glyphs) > 5 else ''}")
    if skipped_ayat:
        print(f"  страница {page_number}: пропущено аятов (расхождение слов) - "
              f"{[(s, a) for s, a, _ in skipped_ayat]}")

    return {
        "page": page_number,
        "font_url": font_url_for_page(page_number),
        "surah_names": [qt.Aya(s, 1).get().sura_name for s in surah_numbers],
        "ayahs": ayahs_out,
        "lines": lines,
    }


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    conn = sqlite3.connect(HADITHS_DB)
    conn.row_factory = sqlite3.Row

    for page_number in range(START_PAGE, END_PAGE + 1):
        try:
            data = export_page(conn, page_number)
        except Exception as e:
            print(f"страница {page_number}: ОШИБКА - {e}")
            continue
        if data is None:
            print(f"страница {page_number}: нет данных страницы")
            continue
        path = os.path.join(OUT_DIR, f"page{page_number}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        n_words = sum(1 for a in data["ayahs"] for t in a["tokens"] if t["type"] == "word")
        print(f"страница {page_number}: {len(data['ayahs'])} аятов, {n_words} слов -> {path}")


if __name__ == "__main__":
    main()
