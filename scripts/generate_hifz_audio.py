#!/usr/bin/env python3
"""Аудио Хусари (Muallim) для режима заучивания 40+40 (02.09.2026).

Нарезка по НАШЕЙ раскладке строк (mushaf_data/page*.json), НЕ по
`line_number` api.quran.com — тот сверен эмпирически и расходится с
нашей (уже проверенной по печатной раскладке KFGQPC V4) разбивкой: на
стр. 7 не совпадает строка у 4 слов из 129 (3.1%), см.
wiki/hifz_audio_husary.md. Взят у проекта `qrum` (tools/
generate_line_audio_v2.py) сам механизм — тайминги/скачивание/ffmpeg —
но не источник границ строки.

Переходное слово — ТОЧНЫЙ порт hifzTailTokens/hifzTailLine из
mushaf_data/index.html (комментарий там же формулирует правило словами):
  • первое слово следующей строки (или первой строки следующего листа,
    если строка последняя на этой странице);
  • если в нём ≤3 буквы без огласовок (предлог/местоимение/частица) —
    добавляем второе;
  • если слово — конец аята, добавляем ещё одно;
  • потолок три слова.
Не взята упрощённая версия из qrum — иначе то, что видно на экране, и
то, что слышно в записи, разошлись бы на границе строк.

Источник таймингов — v4 API, тот же, что у qrum:
    api.qurancdn.com/api/v4/recitations/{id}/by_chapter/{n}?fields=segments
сегмент = [w0, w1, start_ms, end_ms], w0 — 0-based индекс слова в аяте
(наш `position` 1-based = w0+1, проверено на 1605 аятах, 0.12% расхождений
на «склеенных» словах — см. вики).

Использование (из корня проекта):
    python scripts/generate_hifz_audio.py --pages 2-10
    python scripts/generate_hifz_audio.py --pages 5 --out /tmp/test

Требует ffmpeg в PATH (или FFMPEG_BIN в окружении).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from collections import defaultdict

RECITER_ID = 12  # Mahmoud Khalil Al-Husary, Muallim (учительский стиль)
V4_API = "https://api.qurancdn.com/api/v4"

# Без User-Agent api.qurancdn.com отвечает 403 - urllib по умолчанию
# шлёт "Python-urllib/x.y", сервер такое режет как бот-трафик.
_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; yassir-bot/1.0)"}
_HTTP_RETRIES = 4
_HTTP_RETRY_DELAY = 3  # сек, растёт линейно с попыткой


def _fetch_json_with_retry(url):
    """GET -> json с ретраями (растущая пауза) - одиночный сетевой сбой
    (DNS/таймаут) не должен ронять многочасовой прогон."""
    last_err = None
    for attempt in range(_HTTP_RETRIES):
        try:
            req = urllib.request.Request(url, headers=_HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt + 1 < _HTTP_RETRIES:
                time.sleep(_HTTP_RETRY_DELAY * (attempt + 1))
    raise last_err

FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "mushaf_data")
CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "sources", "audio_cache", "husary_verses")

HARAKAT_RE = re.compile("[ً-ٰٟۖ-ۭـ]")
TAG_RE = re.compile(r"<[^>]+>")


def base_len(html):
    """Длина слова без тегов и огласовок — портирует hifzBaseLen 1:1."""
    return len(HARAKAT_RE.sub("", TAG_RE.sub("", html or "")))


# ── Наши данные страницы ────────────────────────────────────────────────

_page_cache = {}


def text_lines(page_number):
    """Текстовые строки страницы (без title/basmala) - тот же фильтр, что
    hifzTextLines() во фронтенде. None, если страницы не существует."""
    if page_number in _page_cache:
        return _page_cache[page_number]
    path = os.path.join(DATA_DIR, f"page{page_number}.json")
    if not os.path.exists(path):
        _page_cache[page_number] = None
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    lines = [l for l in data.get("lines", []) if l.get("type") == "text"]
    _page_cache[page_number] = lines
    return lines


def tail_line(page_number, line_idx):
    """Порт hifzTailLine: следующая строка ЭТОЙ страницы, либо первая
    строка СЛЕДУЮЩЕЙ (foreign=True), либо None."""
    lines = text_lines(page_number)
    if not lines:
        return None
    if line_idx + 1 < len(lines):
        return lines[line_idx + 1], False
    nxt = text_lines(page_number + 1)
    if nxt:
        return nxt[0], True
    return None


def tail_tokens(page_number, line_idx):
    """Порт hifzTailTokens: (следующая_строка, foreign, число_токенов)."""
    res = tail_line(page_number, line_idx)
    if not res:
        return None, False, 0
    next_line, foreign = res
    toks = next_line.get("tokens") or []
    taken, last_idx = 0, -1
    for i, t in enumerate(toks):
        if taken >= 3:
            break
        if t.get("type") != "word":
            continue
        taken += 1
        last_idx = i
        if taken == 1 and base_len(t.get("html")) > 3:
            after = toks[i + 1] if i + 1 < len(toks) else None
            if not after or after.get("type") != "ayah_end":
                break
        elif taken >= 2:
            after2 = toks[i + 1] if i + 1 < len(toks) else None
            if not after2 or after2.get("type") != "ayah_end":
                break
    return next_line, foreign, last_idx + 1


def half_range(page_number, half):
    """Порт hifzHalfRange: [первая, последняя] строка половины (0 или 1)."""
    n = len(text_lines(page_number) or [])
    mid = n // 2
    return (0, mid - 1) if half == 0 else (mid, n - 1)


# ── Тайминги Хусари (v4 API, по суре целиком, с кэшем на диске) ─────────

def fetch_chapter_timings(chapter):
    """{verse_key: {"url": str, "segments": [[w0,w1,start_ms,end_ms],...]}}"""
    cache_path = os.path.join(CACHE_DIR, f"timings_{chapter}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    result = {}
    page = 1
    while True:
        url = (f"{V4_API}/recitations/{RECITER_ID}/by_chapter/{chapter}"
               f"?fields=segments&per_page=50&page={page}")
        data = _fetch_json_with_retry(url)
        for af in data.get("audio_files", []):
            result[af["verse_key"]] = {"url": af.get("url", ""), "segments": af.get("segments", [])}
        pag = data.get("pagination", {})
        if page >= pag.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.1)

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return result


def word_segment_ms(verse_key, pos_1based, timings):
    """(start_ms, end_ms) для слова по 1-based позиции, или None."""
    t = timings.get(verse_key)
    if not t or not t["segments"]:
        return None
    for w0, w1, start_ms, end_ms in t["segments"]:
        if w0 + 1 == pos_1based:
            return start_ms, end_ms
    return None


def download_verse(verse_key, timings):
    """Качает mp3 аята с диска-кэша либо с сервера, возвращает путь."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    chap, ayah = verse_key.split(":")
    fname = f"{int(chap):03d}{int(ayah):03d}.mp3"
    dest = os.path.join(CACHE_DIR, fname)
    if os.path.exists(dest):
        return dest
    url_path = timings.get(verse_key, {}).get("url", "").lstrip("/")
    if not url_path:
        return None
    full_url = f"https://{url_path}"
    for attempt in range(_HTTP_RETRIES):
        try:
            req = urllib.request.Request(full_url, headers=_HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                content = r.read()
            with open(dest, "wb") as f:
                f.write(content)
            return dest
        except (urllib.error.URLError, OSError) as e:
            if attempt + 1 == _HTTP_RETRIES:
                print(f"    ОШИБКА скачивания {verse_key} (после {_HTTP_RETRIES} попыток): {e}")
                return None
            time.sleep(_HTTP_RETRY_DELAY * (attempt + 1))
    return None


def cut(src, start_ms, end_ms, dest):
    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-ss", f"{start_ms / 1000:.3f}", "-to", f"{end_ms / 1000:.3f}",
           "-i", src, "-acodec", "copy", dest]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def concat(parts, dest):
    if not parts:
        return False
    if len(parts) == 1:
        shutil.copy(parts[0], dest)
        return True
    list_file = dest + ".txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
               "-i", list_file, "-acodec", "copy", dest]
        return subprocess.run(cmd, capture_output=True).returncode == 0
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)


# ── Сборка одной строки/перехода в список (verse_key, start_ms, end_ms) ──

def line_word_segments(page_number, line_idx, timings_cache):
    """Токены строки, разбитые на подряд идущие по одному аяту куски —
    каждый кусок физически лежит в СВОЁМ mp3 (аят), резать общий диапазон
    по всей строке нельзя, если она пересекает границу аята."""
    lines = text_lines(page_number)
    line = lines[line_idx]
    out = []
    for t in line.get("tokens") or []:
        if t.get("type") != "word":
            continue
        vk = f"{t['surah']}:{t['ayah']}"
        timings = timings_cache.setdefault(t["surah"], fetch_chapter_timings(t["surah"]))
        seg = word_segment_ms(vk, t["position"], timings)
        if not seg:
            continue
        start_ms, end_ms = seg
        if out and out[-1][0] == vk:
            out[-1] = (vk, out[-1][1], end_ms)  # тот же аят - расширяем диапазон
        else:
            out.append((vk, start_ms, end_ms))
    return out


def tail_word_segments(page_number, line_idx, timings_cache):
    next_line, foreign, count = tail_tokens(page_number, line_idx)
    if not count or not next_line:
        return []
    toks = (next_line.get("tokens") or [])[:count]
    out = []
    for t in toks:
        if t.get("type") != "word":
            continue
        vk = f"{t['surah']}:{t['ayah']}"
        timings = timings_cache.setdefault(t["surah"], fetch_chapter_timings(t["surah"]))
        seg = word_segment_ms(vk, t["position"], timings)
        if not seg:
            continue
        start_ms, end_ms = seg
        if out and out[-1][0] == vk:
            out[-1] = (vk, out[-1][1], end_ms)
        else:
            out.append((vk, start_ms, end_ms))
    return out


# ── Обработка страницы ────────────────────────────────────────────────

def process_page(page_number, out_dir, timings_cache):
    full_marker = os.path.join(out_dir, f"page_{page_number:03d}_full.mp3")
    if os.path.exists(full_marker):
        print(f"стр. {page_number}: уже готова, пропуск")
        return
    lines = text_lines(page_number)
    if not lines:
        print(f"стр. {page_number}: нет данных, пропуск")
        return
    n = len(lines)
    print(f"\n=== стр. {page_number} ({n} строк) ===")

    tmp_dir = os.path.join(out_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    def cut_segments(segs, tag):
        """Список (verse_key, start_ms, end_ms) -> список нарезанных файлов."""
        parts = []
        for j, (vk, s, e) in enumerate(segs):
            timings = None
            for chap, t in timings_cache.items():
                if vk in t:
                    timings = t
                    break
            src = download_verse(vk, timings or {})
            if not src:
                continue
            dest = os.path.join(tmp_dir, f"p{page_number}_{tag}_{j}.mp3")
            if cut(src, s, e, dest):
                parts.append(dest)
        return parts

    # Каждая строка отдельно: content + свой переход.
    line_content, line_trans = {}, {}
    for li in range(n):
        segs = line_word_segments(page_number, li, timings_cache)
        line_content[li] = cut_segments(segs, f"l{li}c")
        tsegs = tail_word_segments(page_number, li, timings_cache)
        line_trans[li] = cut_segments(tsegs, f"l{li}t")

    mid = n // 2

    def group_slot(idx):
        return f"first_{idx}" if idx < mid else f"second_{idx - mid}"

    for li in range(n):
        parts = line_content[li] + line_trans[li]
        if not parts:
            print(f"  строка {li}: нет сегментов")
            continue
        out = os.path.join(out_dir, f"page_{page_number:03d}_{group_slot(li)}.mp3")
        ok = concat(parts, out)
        print(f"  строка {li} [{group_slot(li)}]: {'OK' if ok else 'ОШИБКА'}")

    # Половины: контент всех строк группы + переход только последней.
    for half, label in ((0, "first_half"), (1, "second_half")):
        r0, r1 = half_range(page_number, half)
        if r0 > r1:
            continue
        parts = []
        for li in range(r0, r1):
            parts.extend(line_content[li])
        parts.extend(line_content[r1])
        parts.extend(line_trans[r1])
        out = os.path.join(out_dir, f"page_{page_number:03d}_{label}.mp3")
        ok = concat(parts, out)
        print(f"  {label}: {'OK' if ok else 'ОШИБКА'}")

    # Страница целиком.
    parts = []
    for li in range(n - 1):
        parts.extend(line_content[li])
    parts.extend(line_content[n - 1])
    parts.extend(line_trans[n - 1])
    # full.mp3 - маркер "страница полностью готова" для пропуска при
    # повторном запуске (process_page выше). Обрыв процесса ПОСЛЕ concat,
    # но не полностью атомарный путь мог оставить файл, который resume
    # принял бы за готовый, хотя он битый (реальный случай 02.09.2026,
    # стр. 89 - full.mp3 совпал по размеру с first_half.mp3, потому что
    # процесс прервался как раз на этом шаге). Пишем во временное имя,
    # переименовываем ТОЛЬКО при успехе - os.replace атомарен на одной
    # файловой системе.
    out = os.path.join(out_dir, f"page_{page_number:03d}_full.mp3")
    # ffmpeg выбирает формат по РАСШИРЕНИЮ файла - ".mp3.building" он не
    # узнаёт как mp3 и падает ("Unable to choose an output format"),
    # поймано 02.09.2026 на живом прогоне (все 18 страниц пилота "full"
    # ОШИБКА, хотя строки и половины - ОК). Держим ".mp3" у временного
    # имени, кладём его в tmp_dir (тот и так чистится в конце функции).
    tmp_out = os.path.join(tmp_dir, f"page_{page_number:03d}_full.mp3")
    ok = concat(parts, tmp_out)
    if ok:
        os.replace(tmp_out, out)
    elif os.path.exists(tmp_out):
        os.remove(tmp_out)
    print(f"  full: {'OK' if ok else 'ОШИБКА'}")

    shutil.rmtree(tmp_dir, ignore_errors=True)


def parse_pages(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="напр. 2-10 или 5,7,9")
    ap.add_argument("--out", default=os.path.join(DATA_DIR, "audio", "husary"))
    args = ap.parse_args()

    print(f"ffmpeg: {FFMPEG}")
    os.makedirs(args.out, exist_ok=True)

    timings_cache = {}
    for page in parse_pages(args.pages):
        process_page(page, args.out, timings_cache)

    print("\nГотово. Файлы:")
    for f in sorted(os.listdir(args.out)):
        if f.endswith(".mp3"):
            size = os.path.getsize(os.path.join(args.out, f)) // 1024
            print(f"  {f}  ({size} KB)")


if __name__ == "__main__":
    main()
