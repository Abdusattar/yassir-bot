"""Смысловой перевод (02.11.2026): место отдельного чтения и данные по сурам."""
import asyncio
import json
import pathlib

import core.mufradat_api as api
import core.mushaf_words as mw

ROOT = pathlib.Path(__file__).resolve().parent.parent
MEANING = ROOT / "mushaf_data" / "meaning"


def _call(method, user_id, body=None):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            kw = {"json": body} if body is not None else {}
            resp = await client.request(method, "/api/muf/meaning_pos",
                                        headers={"X-Telegram-Init-Data": user_id}, **kw)
            return resp.status, await resp.json()
        finally:
            await client.close()
    return asyncio.run(run())


def test_meaning_pos_roundtrip(test_db, test_hadiths_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    assert _call("GET", "201") == (200, {})
    status, d = _call("POST", "201", {"surah": 21, "ayah": 73})
    assert status == 200 and (d["surah"], d["ayah"]) == (21, 73)
    status, d = _call("GET", "201")
    assert (d["surah"], d["ayah"]) == (21, 73) and d["updated_at"]
    # Своё у каждого - и не задевает 🔖 и указатель заучивания.
    assert _call("GET", "202") == (200, {})
    assert mw.get_reading_bookmark("201") is None
    assert mw.get_hifz_pointer("201") is None


def test_meaning_pos_rejects_garbage(test_db, test_hadiths_db, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    for body in ({"surah": 0, "ayah": 1}, {"surah": 115, "ayah": 1}, {"surah": 2, "ayah": 0},
                 {"surah": 2, "ayah": 287}, {"surah": "x", "ayah": 1}, {"ayah": 1}):
        assert _call("POST", "201", body)[0] == 400
    assert _call("GET", "201") == (200, {})


def test_every_translation_has_every_ayah():
    """Каждый перевод - 114 сур и одинаковое число аятов в каждой суре."""
    counts = None
    for src in ("ru_kuliev", "ru_abuadel", "ky", "uz", "zh"):
        per = []
        for s in range(1, 115):
            d = json.loads((MEANING / src / f"{s}.json").read_text(encoding="utf-8"))
            assert d["s"] == s
            assert all(t.strip() for t in d["t"]), (src, s)
            assert not any("<" in t for t in d["t"]), (src, s)
            per.append(len(d["t"]))
        assert sum(per) == 6236, src
        counts = counts or per
        assert per == counts, src
