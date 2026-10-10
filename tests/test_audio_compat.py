"""Звук старым iPhone (28.09.2026): ogg/opus Safari играет только с iOS 18.4,
ниже - отдаём mp3 (core/audio_compat.py). Живой случай - устаз Зейнеб, iOS
17.3: «Прослушать сдачу» молчала у всех студентов."""

import asyncio
import os
import shutil
import subprocess

import pytest

import core.audio_compat as ac
import core.mufradat_api as api

ZEINEB = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Mobile/15E148")


def _ios(ver):
    return ZEINEB.replace("17_3", ver)


@pytest.mark.parametrize("ua, want", [
    (ZEINEB, True),
    (_ios("18_2"), True),
    (_ios("18_3_1"), True),
    (_ios("18_4"), False),
    (_ios("18_4_1"), False),
    (_ios("18_10"), False),           # числами, не строкой: "18_10" < "18_4"
    (_ios("26_0"), False),
    (_ios("15_8"), True),
    ("Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15", True),
    # Chrome на iPhone - тот же WebKit, решает версия iOS
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) CriOS/120.0 Mobile Safari", True),
    ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/17.3 Safari/605.1.15", True),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/18.4 Safari/605.1.15", False),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/120 Safari/537.36", False),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36", False),
    ("", False),
    (None, False),
])
def test_needs_mp3_by_user_agent(ua, want):
    assert ac.needs_mp3(ua) is want


def test_fmt_mp3_asks_even_on_android():
    """Страховка из приложения: телефон сказал NotSupportedError."""
    assert ac.needs_mp3("Mozilla/5.0 (Linux; Android 14)", "mp3") is True
    assert ac.needs_mp3("Mozilla/5.0 (Linux; Android 14)", "ogg") is False


class _Req:
    def __init__(self, ua, query=None):
        self.headers = {"User-Agent": ua}
        self.query = query or {}


def test_old_iphone_gets_mp3_from_cache_without_telegram(tmp_path, monkeypatch):
    """Готовый mp3 в кэше - в Telegram не ходим вовсе (сеть в тесте не нужна)."""
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    ac._store(ac._cache_path("fid-1"), b"ID3fake")
    resp = asyncio.run(api._telegram_audio_response("fid-1", _Req(ZEINEB)))
    assert resp.content_type == "audio/mpeg"
    assert resp.body == b"ID3fake"


def test_store_drops_old_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    old = ac._cache_path("old")
    ac._store(old, b"x")
    os.utime(old, (1, 1))
    ac._store(ac._cache_path("new"), b"y")
    assert not os.path.exists(old)
    assert ac.cached_mp3("new") == b"y"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="нет ffmpeg")
def test_to_mp3_real_ogg(tmp_path, monkeypatch):
    """Настоящий ogg/opus -> mp3 той же длины, второй раз - из кэша."""
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path / "cache"))
    src = tmp_path / "v.ogg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-ac", "1", "-c:a", "libopus", "-b:a", "32k", str(src)], check=True)
    out = asyncio.run(ac.to_mp3(src.read_bytes(), "fid-2"))
    assert out and (out[:3] == b"ID3" or out[0] == 0xFF)
    mp3 = tmp_path / "o.mp3"
    mp3.write_bytes(out)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(mp3)], capture_output=True, text=True).stdout
    assert abs(float(dur) - 3.0) < 0.3
    assert ac.cached_mp3("fid-2") == out


def test_to_mp3_broken_input_returns_none(tmp_path, monkeypatch):
    """Битый файл - None, вызывающий отдаст исходник, а не 500."""
    if not shutil.which("ffmpeg"):
        pytest.skip("нет ffmpeg")
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    assert asyncio.run(ac.to_mp3(b"not audio at all", "fid-3")) is None
    assert ac.cached_mp3("fid-3") is None


# --- Недельная копия m4a (28.09.2026) ---------------------------------------

def _make(tmp_path, name, args):
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=3",
                    "-ac", "1", *args, str(out)], check=True)
    return out.read_bytes()


def _probe(data, tmp_path):
    f = tmp_path / "probe.bin"
    f.write_bytes(data)
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                          "-show_entries", "stream=codec_name,bit_rate:format=duration",
                          "-of", "default=nw=1", str(f)], capture_output=True, text=True).stdout
    return dict(line.split("=", 1) for line in out.split())


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="нет ffmpeg")


@needs_ffmpeg
def test_copy_from_android_opus_is_aac_64k(tmp_path):
    ogg = _make(tmp_path, "a.ogg", ["-c:a", "libopus", "-b:a", "32k"])
    asyncio.run(ac._make_copy("fid-a", [ogg], ogg))
    info = _probe(ac.local_copy("fid-a"), tmp_path)
    assert info["codec_name"] == "aac"
    assert abs(float(info["duration"]) - 3.0) < 0.3


@needs_ffmpeg
def test_copy_from_iphone_aac_kept_as_is(tmp_path):
    """iPhone пишет AAC - перекладываем без перекодировки: звук ровно исходный."""
    m4a = _make(tmp_path, "i.m4a", ["-c:a", "aac", "-b:a", "64k", "-f", "ipod"])
    ogg = _make(tmp_path, "i.ogg", ["-c:a", "libopus", "-b:a", "32k"])
    asyncio.run(ac._make_copy("fid-i", [m4a], ogg))
    src, copy = _probe(m4a, tmp_path), _probe(ac.local_copy("fid-i"), tmp_path)
    assert copy["codec_name"] == "aac"
    assert copy["bit_rate"] == src["bit_rate"]


@needs_ffmpeg
def test_heavy_iphone_aac_is_squeezed_to_64k(tmp_path):
    """Тяжелее 96k - место на диске считаем, сжимаем в те же 64k."""
    m4a = _make(tmp_path, "h.m4a", ["-c:a", "aac", "-b:a", "160k", "-f", "ipod"])
    ogg = _make(tmp_path, "h.ogg", ["-c:a", "libopus", "-b:a", "32k"])
    asyncio.run(ac._make_copy("fid-h", [m4a], ogg))
    assert int(_probe(ac.local_copy("fid-h"), tmp_path)["bit_rate"]) <= 80000


@needs_ffmpeg
def test_resumed_recording_copy_from_ogg(tmp_path):
    """Несколько кусков (чтение прерывалось) - копия из склеенного ogg."""
    ogg = _make(tmp_path, "r.ogg", ["-c:a", "libopus", "-b:a", "32k"])
    asyncio.run(ac._make_copy("fid-r", [b"part1", b"part2"], ogg))
    assert _probe(ac.local_copy("fid-r"), tmp_path)["codec_name"] == "aac"


def test_broken_copy_leaves_nothing(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("нет ffmpeg")
    asyncio.run(ac._make_copy("fid-b", [b"junk"], b"junk"))
    assert ac.local_copy("fid-b") is None


def test_keep_copy_without_file_id_does_nothing():
    assert ac.keep_copy(None, [b"x"], b"x") is None
    assert ac.keep_copy("fid", [b"x"], b"") is None


@pytest.mark.parametrize("ua", [ZEINEB, _ios("26_0"),
                                "Mozilla/5.0 (Linux; Android 10; K) Chrome/120 Mobile"])
def test_local_copy_served_to_every_phone(tmp_path, ua):
    """Копия есть - m4a всем, в Telegram не ходим (сети в тесте нет)."""
    ac._store(ac._cache_path("fid-c", "m4a"), b"M4Afake")
    resp = asyncio.run(api._telegram_audio_response("fid-c", _Req(ua)))
    assert resp.content_type == "audio/mp4"
    assert resp.body == b"M4Afake"


def _stream(path, headers=None):
    async def go():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            r = await client.get("/api/muf" + path, headers=headers or {})
            return r.status, await r.read(), r.headers
        finally:
            await client.close()
    return asyncio.run(go())


def test_stream_link_plays_with_range(tmp_path, monkeypatch):
    """10.10.2026: устаз ждал длинную 40+40, пока она скачается целиком.
    ?link=1 даёт подписанный адрес копии, а поток отдаёт её кусками (Range)."""
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    ac._store(ac._cache_path("fid-s", "m4a"), b"0123456789" * 100)
    resp = asyncio.run(api._telegram_audio_response("fid-s", _Req("x", {"link": "1"})))
    import json
    url = json.loads(resp.body)["url"]
    assert url.startswith("/audio/s?t=")

    status, body, headers = _stream(url, {"Range": "bytes=10-19"})
    assert status == 206 and body == b"0123456789"
    assert headers["Content-Type"] == "audio/mp4"

    status, body, _ = _stream(url)
    assert status == 200 and len(body) == 1000


def test_stream_link_refuses_forged_or_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    ac._store(ac._cache_path("fid-s", "m4a"), b"secret")
    url = api._audio_link("fid-s")
    name, exp, sig = url.split("t=", 1)[1].rsplit(".", 2)
    other = ac._cache_path("fid-other", "m4a")
    ac._store(other, b"other")
    forged = "/audio/s?t=%s.%s.%s" % (os.path.basename(other), exp, sig)
    assert _stream(forged)[0] == 403
    old = int(exp) - 10 * api._AUDIO_LINK_TTL
    expired = "/audio/s?t=%s.%d.%s" % (name, old, api._audio_link_sig(name, old))
    assert _stream(expired)[0] == 403
    assert _stream("/audio/s?t=../../etc/passwd.1.x")[0] in (400, 403)


def test_no_copy_no_link(tmp_path, monkeypatch):
    """Копии нет - url пустой, приложение качает целиком, как раньше."""
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    resp = asyncio.run(api._telegram_audio_response("fid-none", _Req("x", {"link": "1"})))
    import json
    assert json.loads(resp.body) == {"url": None}
