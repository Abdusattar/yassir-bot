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


# Край каждого отрезка - плавный вход/выход. Резка копированием (-acodec
# copy, до 21.09.2026) шла по границе mp3-кадра посреди волны, и на стыках
# слышалось «кыйч»: замер скачка - 1394 против 238 в обычном месте записи.
FADE_SEC = 0.012
BITRATE = "128k"   # как у исходников Husary Muallim (128 кбит/с, 44.1 кГц)


def build_unit(sources, dest):
    """Собрать единицу ОДНИМ проходом ffmpeg (21.09.2026).

    sources - список (путь_к_mp3_аята, start_ms, end_ms) по порядку чтения.
    Каждый отрезок вырезается точно по отсчётам (atrim после декодирования,
    а не по кадрам mp3), на краях - FADE_SEC, потом concat и одно
    кодирование. Пишем во временный файл рядом и переименовываем только при
    успехе: обрыв не оставит битый файл под готовым именем."""
    if not sources:
        return False
    cmd = [FFMPEG, "-y", "-loglevel", "error"]
    for path, _, _ in sources:
        cmd += ["-i", path]
    chains, labels = [], []
    for i, (_, start_ms, end_ms) in enumerate(sources):
        dur = max(0.0, (end_ms - start_ms) / 1000)
        fade = min(FADE_SEC, dur / 4)
        chains.append(
            f"[{i}:a]atrim=start={start_ms / 1000:.3f}:end={end_ms / 1000:.3f},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={max(0.0, dur - fade):.3f}:d={fade:.3f}[a{i}]")
        labels.append(f"[a{i}]")
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(sources)}:v=0:a=1[out]"
    tmp = dest[:-4] + ".tmp.mp3"   # ffmpeg берёт формат по расширению
    cmd += ["-filter_complex", graph, "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", BITRATE, "-ar", "44100", tmp]
    ok = subprocess.run(cmd, capture_output=True).returncode == 0
    if ok:
        os.replace(tmp, dest)
    elif os.path.exists(tmp):
        os.remove(tmp)
    return ok


# ── Сборка одной строки/перехода в список (verse_key, start_ms, end_ms) ──

def unit_word_segments(page_number, line_indices, timings_cache, tail_from_last=False,
                       tail_apart=False):
    """Токены НЕСКОЛЬКИХ строк подряд, слитые в один список (verse_key,
    start_ms, end_ms) - соседние токены ОДНОГО аята объединяются в общий
    непрерывный отрезок ДАЖЕ через границу строки.

    Раньше half/full клеились из уже нарезанных ПОСТРОЧНЫХ кусочков
    (line_word_segments по каждой строке отдельно) - если аят продолжался
    на следующей строке, получались два независимых реза одного и того же
    исходного mp3 в соседних точках и шов между ними. Резка -acodec copy
    режет по границе mp3-фрейма (~26 мс), не по миллисекундам - два
    отдельных реза почти никогда не совпадают идеально, шов слышен
    (поймано пользователем на слух 02.09.2026). Эта функция режет аят
    ОДНИМ куском независимо от того, сколько строк он занимает - шов
    остаётся только на границе между РАЗНЫМИ аятами (разные исходные
    mp3 - это уже не наша резка, а естественная пауза чтеца)."""
    lines = text_lines(page_number)
    out = []

    def add_token(t):
        vk = f"{t['surah']}:{t['ayah']}"
        timings = timings_cache.setdefault(t["surah"], fetch_chapter_timings(t["surah"]))
        seg = word_segment_ms(vk, t["position"], timings)
        if not seg:
            return
        start_ms, end_ms = seg
        if out and out[-1] is not None and out[-1][0] == vk:
            out[-1] = (vk, out[-1][1], end_ms)
        else:
            out.append((vk, start_ms, end_ms))

    for li in line_indices:
        for t in lines[li].get("tokens") or []:
            if t.get("type") == "word":
                add_token(t)

    if tail_from_last:
        next_line, foreign, count = tail_tokens(page_number, line_indices[-1])
        # tail_apart - переходное слово отдельным отрезком, даже если оно из
        # того же аята. У строки так было всегда: Хусари-Muallim после
        # отрывка молчит, давая ученику повторить (стр. 5, строка 0: конец
        # строки 11.9 с, переходное слово с 20.9 с), и слитый отрезок
        # захватил бы эти девять секунд тишины (поймано 21.09.2026).
        if tail_apart:
            out.append(None)
        if count and next_line:
            for t in (next_line.get("tokens") or [])[:count]:
                if t.get("type") == "word":
                    add_token(t)

    return [x for x in out if x is not None]


# ── Обработка страницы ────────────────────────────────────────────────

def process_page(page_number, out_dir, timings_cache, force=False):
    full_marker = os.path.join(out_dir, f"page_{page_number:03d}_full.mp3")
    if os.path.exists(full_marker) and not force:
        print(f"стр. {page_number}: уже готова, пропуск")
        return
    lines = text_lines(page_number)
    if not lines:
        print(f"стр. {page_number}: нет данных, пропуск")
        return
    n = len(lines)
    print(f"\n=== стр. {page_number} ({n} строк) ===")

    def sources_of(segs):
        """(verse_key, start_ms, end_ms) -> (путь к mp3 аята, start_ms, end_ms)."""
        out = []
        for vk, s, e in segs:
            timings = next((t for t in timings_cache.values() if vk in t), {})
            src = download_verse(vk, timings)
            if src:
                out.append((src, s, e))
        return out

    def make(line_indices, dest, label, tail_apart=False):
        # Пропуск пофайлово: обрыв посреди страницы не заставит пересобирать
        # уже готовое. full - последним, он же маркер «страница готова».
        if os.path.exists(dest) and not force:
            return
        if not unit_word_segments(page_number, line_indices, timings_cache):
            # Пустые ряды (декоративная рамка стр. 1-2): файла быть не должно,
            # иначе останется одно переходное слово из ниоткуда (02.09.2026).
            return
        segs = unit_word_segments(page_number, line_indices, timings_cache, tail_from_last=True,
                                  tail_apart=tail_apart)
        ok = build_unit(sources_of(segs), dest)
        print(f"  {label}: {'OK' if ok else 'ОШИБКА'}")

    mid = n // 2

    def group_slot(idx):
        return f"first_{idx}" if idx < mid else f"second_{idx - mid}"

    # Строка = её слова + переходное слово следующей строки отдельным
    # отрезком (пауза Muallim между ними не нужна, см. unit_word_segments).
    for li in range(n):
        make([li], os.path.join(out_dir, f"page_{page_number:03d}_{group_slot(li)}.mp3"),
             f"строка {li} [{group_slot(li)}]", tail_apart=True)
    for half, label in ((0, "first_half"), (1, "second_half")):
        r0, r1 = half_range(page_number, half)
        if r0 <= r1:
            make(list(range(r0, r1 + 1)),
                 os.path.join(out_dir, f"page_{page_number:03d}_{label}.mp3"), label)
    make(list(range(n)), full_marker, "full")


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
    ap.add_argument("--force", action="store_true",
                    help="пересобрать и готовые файлы (перенарезка 21.09.2026)")
    args = ap.parse_args()

    print(f"ffmpeg: {FFMPEG}")
    os.makedirs(args.out, exist_ok=True)

    timings_cache = {}
    for page in parse_pages(args.pages):
        process_page(page, args.out, timings_cache, force=args.force)

    print("\nГотово. Файлы:")
    for f in sorted(os.listdir(args.out)):
        if f.endswith(".mp3"):
            size = os.path.getsize(os.path.join(args.out, f)) // 1024
            print(f"  {f}  ({size} KB)")


if __name__ == "__main__":
    main()
