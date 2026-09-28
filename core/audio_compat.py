"""Звук для телефонов, которые не играют ogg/opus (28.09.2026).

Голосовые Telegram - ogg/opus, и так они у нас и хранятся. Safari научился
ogg только в iOS 18.4 (caniuse.com/opus: до 17.4 opus только в CAF, 17.4-18.3
только в WebM). Все браузеры на iPhone - это WebKit той же версии iOS, и
приложение внутри Telegram тоже. Устаз Зейнеб (iOS 17.3) неделями нажимала
«Прослушать сдачу» - звука не было, у 10 из 73 iPhone за три дня то же.

Хранение не трогаем (Telegram, лимит 20 МБ на getFile, быстрый приём с
Android, корпус tajweed_ai) - старым телефонам перекодируем на лету в mp3:
играет везде (caniuse.com/mp3), кодируется быстрее AAC на наших двух ядрах
(15 минут записи: mp3 ~15-25 с, AAC 37-107 с) и CBR перематывается «−10 с».
Готовое кладём в кэш на диске: второй раз та же запись отдаётся сразу.

Кто получает mp3: iOS/Safari ниже 18.4 по User-Agent (без правок в
приложении - старый index.html из кэша PWA тоже заиграет) или любой, кто
попросил ?fmt=mp3 (страховка в приложении: телефон сказал NotSupportedError).
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

# 22 кГц держит голос до 11 кГц - свистящие (с, ш, ص) не теряются.
_MP3_ARGS = ["-vn", "-ac", "1", "-ar", "22050",
             "-c:a", "libmp3lame", "-b:a", "48k", "-compression_level", "7"]

_IOS = re.compile(r"(?:iPhone|iPad|iPod).*? OS (\d+)_(\d+)")
_MAC_SAFARI = re.compile(r"Version/(\d+)\.(\d+)")
_NOT_SAFARI = ("Chrome", "Chromium", "Edg/", "Firefox", "OPR/")

_locks = {}


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


def _cache_path(file_id):
    return os.path.join(CACHE_DIR, hashlib.sha1(file_id.encode()).hexdigest() + ".mp3")


def cached_mp3(file_id):
    """Готовый mp3 из кэша или None - чтобы не качать ogg из Telegram зря."""
    try:
        with open(_cache_path(file_id), "rb") as f:
            return f.read()
    except OSError:
        return None


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
            out = await _transcode(audio_bytes)
            if out:
                _store(file_id, out)
            return out
    finally:
        if not lock.locked():
            _locks.pop(file_id, None)


async def _transcode(audio_bytes):
    tmp = tempfile.mkdtemp(prefix="yassir-mp3-")
    src, dst = os.path.join(tmp, "in"), os.path.join(tmp, "out.mp3")
    started = time.monotonic()
    try:
        with open(src, "wb") as f:
            f.write(audio_bytes)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", src, *_MP3_ARGS, "-f", "mp3", dst,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        except (FileNotFoundError, OSError) as e:
            log.error("mp3: ffmpeg недоступен: %s: %s", type(e).__name__, e)
            return None
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            log.error("mp3: ffmpeg не уложился в %s с (%d байт)", _TIMEOUT, len(audio_bytes))
            return None
        if proc.returncode != 0:
            log.warning("mp3: ffmpeg вернул %s: %s", proc.returncode, (err or b"")[:200])
            return None
        with open(dst, "rb") as f:
            out = f.read()
        log.info("mp3: %d -> %d байт за %.1f с", len(audio_bytes), len(out),
                 time.monotonic() - started)
        return out or None
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def _store(file_id, data):
    """Атомарно в кэш и заодно чистка старого - отдельной задачи не заводим."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _cache_path(file_id)
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
        log.warning("mp3: кэш не записан: %s", e)
