"""Прерванное чтение уходит устазу одной записью (20.09.2026).

Бекхан (G-10) читал повторение восемь минут, Telegram перезапустил вкладку -
всё пропало. Теперь приложение хранит начитанное на телефоне и даёт
продолжить; продолжение - отдельный поток MediaRecorder со своим заголовком,
байтами такие файлы не склеить. Сшивает сервер.

Тесты требуют ffmpeg (он же нужен боту в бою). Без него - пропускаем, как и
остальные аудио-тесты.
"""
import asyncio
import shutil
import subprocess

import pytest

import core.mufradat_bot as mb

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="без ffmpeg/ffprobe склеивать и мерить нечем")

# Настоящий замер длины: общая фикстура conftest глушит его для всех тестов
# (там подают ненастоящий звук), а здесь звук настоящий и мерить надо.
REAL_AUDIO_SECONDS = mb.audio_seconds


@pytest.fixture(autouse=True)
def _real_probe(monkeypatch):
    monkeypatch.setattr(mb, "audio_seconds", REAL_AUDIO_SECONDS)
    monkeypatch.setattr(mb, "_probe_ok", None)


def _tone(seconds, freq=440):
    """Кусок настоящего звука в webm/opus - то же, что даёт Chrome."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=%d:duration=%s" % (freq, seconds),
         "-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-ar", "48000",
         "-f", "webm", "pipe:1"],
        capture_output=True)
    assert out.returncode == 0 and out.stdout, out.stderr[:200]
    return out.stdout


def _seconds(ogg):
    return asyncio.run(mb.audio_seconds(ogg))


def test_two_parts_become_one_record():
    """Ради чего всё: два куска дают одну запись их общей длины."""
    parts = [_tone(2), _tone(3, freq=660)]

    ogg = asyncio.run(mb.transcode_parts_to_ogg(parts))

    assert ogg
    sec = _seconds(ogg)
    assert sec is None or 4.0 <= sec <= 6.0, sec


def test_one_part_goes_the_usual_way():
    """Один кусок - обычная сдача, склейка не вмешивается."""
    ogg = asyncio.run(mb.transcode_parts_to_ogg([_tone(2)]))

    assert ogg
    sec = _seconds(ogg)
    assert sec is None or 1.5 <= sec <= 2.5, sec


def test_empty_parts_are_skipped():
    """Пустой кусок бывает, если вкладку убили между запросом и записью."""
    ogg = asyncio.run(mb.transcode_parts_to_ogg([b"", _tone(2), b""]))

    assert ogg


def test_nothing_to_join():
    assert asyncio.run(mb.transcode_parts_to_ogg([])) is None
    assert asyncio.run(mb.transcode_parts_to_ogg([b""])) is None


def test_broken_part_does_not_pass_as_a_record():
    """Битый кусок - не запись: лучше сказать студенту, чем слать мусор."""
    assert asyncio.run(mb.transcode_parts_to_ogg([_tone(2), b"not audio at all"])) is None


def test_checked_parts_report_a_short_join():
    """Склеилось заметно короче, чем шёл таймер на телефоне - это обрыв, а не
    запись. Та же мерка, что у одиночной сдачи (lost_tail)."""
    parts = [_tone(1), _tone(1)]

    ogg, err = asyncio.run(mb.transcode_checked_parts(parts, client_ms=60000))

    assert ogg is None and err == "incomplete"


def test_checked_parts_accept_a_full_join():
    parts = [_tone(2), _tone(2)]

    ogg, err = asyncio.run(mb.transcode_checked_parts(parts, client_ms=4000))

    assert ogg and err is None


def test_stream_heads_counts_glued_attempts(caplog):
    """21.09.2026: «Перезаписать» не стирал куски на телефоне, и прежние
    попытки уходили вместе с новой - начало сдачи звучало трижды. Длина по
    ffprobe этого не видит (у склейки время начинается заново), а заголовки
    потоков видно: у одной записи он один."""
    one = _tone(2)
    glued = _tone(1) + _tone(1, freq=660) + one

    assert mb.stream_heads(one) == 1
    assert mb.stream_heads(glued) == 3
    assert mb.stream_heads(b"") == 0

    asyncio.run(mb.transcode_checked_parts([glued], client_ms=2000))
    assert "склеена из 3 потоков" in caplog.text
