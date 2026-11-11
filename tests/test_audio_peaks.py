"""Волна громкости для плеера устаза (11.11.2026): расчёт по сырому PCM и
чтение рядом с копией."""
import json
import math

import core.audio_compat as ac


def _pcm(seconds, amp, hz=440, rate=1000):
    out = bytearray()
    for i in range(seconds * rate):
        v = int(amp * math.sin(2 * math.pi * hz * i / rate))
        out += int(v).to_bytes(2, "little", signed=True)
    return bytes(out)


def test_peaks_shape_and_scale():
    raw = _pcm(10, 12000) + _pcm(10, 1200)      # громкая половина, потом тихая
    peaks = ac.peaks_from_pcm(raw, n=48)
    assert len(peaks) == 48
    assert all(0.0 <= p <= 1.0 for p in peaks)
    assert max(peaks[:24]) == 1.0               # нормировка на самый громкий
    assert max(peaks[24:]) < 0.2                # тихая часть в десять раз ниже


def test_silence_and_empty():
    assert ac.peaks_from_pcm(b"", n=8) == [0.0] * 8
    assert ac.peaks_from_pcm(bytes(2000), n=8) == [0.0] * 8


def test_peaks_for_reads_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ac, "CACHE_DIR", str(tmp_path))
    assert ac.peaks_for("nope") is None
    assert ac.peaks_for(None) is None
    ac._store(ac._cache_path("f1", "peaks.json"), json.dumps([0.1, 1.0, 0.5]).encode())
    assert ac.peaks_for("f1") == [0.1, 1.0, 0.5]
    ac._store(ac._cache_path("f2", "peaks.json"), b"not json")
    assert ac.peaks_for("f2") is None
