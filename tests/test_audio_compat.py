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
    ac._store("fid-1", b"ID3fake")
    resp = asyncio.run(api._telegram_audio_response("fid-1", _Req(ZEINEB)))
    assert resp.content_type == "audio/mpeg"
    assert resp.body == b"ID3fake"


def test_store_drops_old_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    ac._store("old", b"x")
    old = ac._cache_path("old")
    os.utime(old, (1, 1))
    ac._store("new", b"y")
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
