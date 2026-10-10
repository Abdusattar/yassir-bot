"""Звук, который играют все телефоны (28.09.2026).

Голосовые Telegram - ogg/opus. Safari научился ogg только в iOS 18.4
(caniuse.com/opus: до 17.4 opus только в CAF, 17.4-18.3 только в WebM). Все
браузеры на iPhone - это WebKit той же версии iOS, и приложение внутри
Telegram тоже. Устаз Зейнеб (iOS 17.3) неделями нажимала «Прослушать сдачу» -
звука не было, у 10 из 73 iPhone за три дня то же.

Своя копия на неделю (решение пользователя: «более недели записи не храним»).
Слушают теперь в приложении, а не в Telegram - при приёме сдачи фоном кладём
копию m4a/AAC (играют ВСЕ телефоны, caniuse.com/aac) и отдаём её всем сразу,
без похода в Telegram. Голосовое в группе остаётся постоянной копией.

Старше недели (или копия не успела/не вышла) - путь через Telegram: ogg как
есть, а iOS/Safari ниже 18.4 по User-Agent или по ?fmt=mp3 (страховка в
приложении: телефон сказал NotSupportedError) - mp3 на лету, с кэшем.

Качество - ради таджвида: свист ص س ز, рассеивание ش, шёпот ث ف ح живут в
4-10 кГц. mp3 32k срезает их (~7-8 кГц), поэтому копия - AAC 64k: запись с
Android - opus ~30k, AAC 64k своих потерь к ней почти не добавляет. iPhone
пишет сразу AAC - перекладываем без перекодировки, если он не тяжелее 96k.
mp3 на лету - 64k / 32 кГц (полоса до ~14 кГц): быстрее AAC на наших двух
ядрах (15 минут записи: mp3 ~15-25 с, AAC 37-107 с).
"""

import asyncio
import hashlib
import logging
import os
import re
import tempfile
import time

log = logging.getLogger(__name__)

# С этой версии WebKit играет ogg/opus в <audio> (WebKit Features in Safari 18.4).
OGG_SINCE = (18, 4)

CACHE_DIR = os.path.expanduser("~/.cache/yassir-audio")
CACHE_KEEP_SEC = 7 * 24 * 3600

# 45-минутное повторение на сервере - до минуты с небольшим; nginx ждёт 300 с.
_TIMEOUT = 280

_MP3_ARGS = ["-vn", "-ac", "1", "-ar", "32000",
             "-c:a", "libmp3lame", "-b:a", "64k", "-compression_level", "7"]
_COPY_AAC_ARGS = ["-vn", "-ac", "1", "-c:a", "aac", "-b:a", "64k"]
_COPY_AS_IS_MAX_BPS = 96000

_IOS = re.compile(r"(?:iPhone|iPad|iPod).*? OS (\d+)_(\d+)")
_MAC_SAFARI = re.compile(r"Version/(\d+)\.(\d+)")
_NOT_SAFARI = ("Chrome", "Chromium", "Edg/", "Firefox", "OPR/")

_locks = {}
_bg_sem = None
_bg_tasks = set()


def needs_mp3(user_agent, fmt=None):
    """True - этому телефону ogg не сыграть, отдаём mp3."""
    if fmt == "mp3":
        return True
    ua = user_agent or ""
    m = _IOS.search(ua)
    if m:
        return (int(m.group(1)), int(m.group(2))) < OGG_SINCE
    # Safari на Mac - и iPad в режиме «как на компьютере», он пишет себя Mac'ом.
    if "Macintosh" in ua and "Safari" in ua and not any(s in ua for s in _NOT_SAFARI):
        m = _MAC_SAFARI.search(ua)
        if m:
            return (int(m.group(1)), int(m.group(2))) < OGG_SINCE
    return False


def _cache_path(file_id, ext="mp3"):
    return os.path.join(CACHE_DIR, hashlib.sha1(file_id.encode()).hexdigest() + "." + ext)


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def cached_mp3(file_id):
    """Готовый mp3 из кэша или None - чтобы не качать ogg из Telegram зря."""
    return _read(_cache_path(file_id))


def local_copy_path(file_id):
    """Путь к недельной копии m4a или None (10.10.2026: её отдаём потоком,
    см. core/mufradat_api.py, handle_audio_stream)."""
    if not file_id:
        return None
    path = _cache_path(file_id, "m4a")
    return path if os.path.isfile(path) else None


def local_copy(file_id):
    """Недельная копия m4a (играет везде) или None."""
    return _read(_cache_path(file_id, "m4a")) if file_id else None


async def to_mp3(audio_bytes, file_id):
    """ogg (или что угодно со звуком) -> mp3. None - не вышло, вызывающий
    отдаёт исходник: пусть лучше не заиграет у одного, чем 500 у всех."""
    # Замок на файл: устаз жмёт «Прослушать» дважды, пока длинная запись
    # кодируется, - второй запрос ждёт первый и берёт из кэша, а не
    # запускает ещё один ffmpeg на двух ядрах.
    lock = _locks.setdefault(file_id, asyncio.Lock())
    try:
        async with lock:
            done = cached_mp3(file_id)
            if done:
                return done
            out = await _ffmpeg(audio_bytes, _MP3_ARGS, "mp3", "mp3")
            if out:
                _store(_cache_path(file_id), out)
            return out
    finally:
        if not lock.locked():
            _locks.pop(file_id, None)


def keep_copy(file_id, parts, ogg):
    """Фоном - недельная копия m4a после отправки записи в группу. Студент
    ответа не ждёт; не вышло - не беда, запись играет путём через Telegram.

    parts - исходники из браузера (кусков больше одного, если чтение
    прерывалось), ogg - то, что ушло в Telegram."""
    if not file_id or not ogg:
        return None
    try:
        task = asyncio.get_running_loop().create_task(
            _make_copy(file_id, [p for p in (parts or []) if p], ogg))
    except RuntimeError:
        return None
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


async def _make_copy(file_id, parts, ogg):
    global _bg_sem
    if _bg_sem is None:
        _bg_sem = asyncio.Semaphore(1)   # по одной: два ядра делим с ботом
    async with _bg_sem:
        try:
            out = None
            if len(parts) == 1:
                bps = await _probe_aac_bps(parts[0])
                if bps is not None and bps <= _COPY_AS_IS_MAX_BPS:
                    # iPhone: перекладка без перекодировки - звук ровно исходный.
                    out = await _ffmpeg(parts[0], ["-vn", "-c:a", "copy"], "ipod", "m4a",
                                        low_priority=True)
            if not out:
                out = await _ffmpeg(ogg, _COPY_AAC_ARGS, "ipod", "m4a", low_priority=True)
            if out:
                _store(_cache_path(file_id, "m4a"), out)
        except Exception:
            log.exception("audio: копия не сделана")


async def _probe_aac_bps(audio_bytes):
    """Битрейт, если это AAC (запись iPhone; 0 - битрейт не указан), иначе None."""
    tmp = tempfile.mkdtemp(prefix="yassir-probe-")
    src = os.path.join(tmp, "in")
    try:
        with open(src, "wb") as f:
            f.write(audio_bytes)
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,bit_rate", "-of", "csv=p=0", src,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        codec, _, bps = (out or b"").decode().strip().partition(",")
        if codec != "aac":
            return None
        return int(bps) if bps.isdigit() else 0
    except (OSError, asyncio.TimeoutError):
        return None
    finally:
        _cleanup(tmp, src)


async def _ffmpeg(audio_bytes, args, fmt, ext, low_priority=False):
    """Один прогон ffmpeg файл -> файл: mp4 в трубу не пишется, оглавлению
    нужна перемотка. low_priority - фоновая копия уступает боту процессор."""
    tmp = tempfile.mkdtemp(prefix="yassir-audio-")
    src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out." + ext)
    extra = ["-movflags", "+faststart"] if fmt == "ipod" else []
    # -nostdin и пустой stdin: иначе ffmpeg читает клавиши с чужого ввода и
    # в фоне может встать навсегда (так зависал прогон тестов).
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-i", src, *args, *extra, "-f", fmt, dst]
    if low_priority and os.name == "posix":
        cmd = ["nice", "-n", "10", *cmd]
    started = time.monotonic()
    try:
        with open(src, "wb") as f:
            f.write(audio_bytes)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except (FileNotFoundError, OSError) as e:
            log.error("audio: ffmpeg недоступен: %s: %s", type(e).__name__, e)
            return None
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            log.error("audio: ffmpeg %s не уложился в %s с (%d байт)", ext, _TIMEOUT, len(audio_bytes))
            return None
        if proc.returncode != 0:
            log.warning("audio: ffmpeg %s вернул %s: %s", ext, proc.returncode, (err or b"")[:200])
            return None
        out = _read(dst)
        if out:
            log.info("audio: %s %d -> %d байт за %.1f с", ext, len(audio_bytes), len(out),
                     time.monotonic() - started)
        return out or None
    finally:
        _cleanup(tmp, src, dst)


def _cleanup(tmp, *files):
    for p in files:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass


def _store(path, data):
    """Атомарно в кэш и заодно чистка старше недели - отдельной задачи не
    заводим: пишем каждый день, значит и чистим каждый день."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        part = path + ".part"
        with open(part, "wb") as f:
            f.write(data)
        os.replace(part, path)
        edge = time.time() - CACHE_KEEP_SEC
        for name in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, name)
            try:
                if os.path.getmtime(p) < edge:
                    os.remove(p)
            except OSError:
                pass
    except OSError as e:
        log.warning("audio: кэш не записан: %s", e)
