"""Профиль в приложении (10.09.2026).

Экран под шестерёнкой правит имя, год рождения и место. Здесь проверяется
то, что легко сломать незаметно: что имя нельзя обнулить (его видит вся
группа в рейтинге), что год рождения не принимает чепуху, и что заполненный
профиль закрывает анкету в личке - иначе бот спросит то, что человек уже
сказал сам.
"""
import asyncio

import pytest

import core.db as db
import core.mufradat_api as api
from core import web_auth as wa

PHONE = "777333"


def _student(phone=PHONE, name="Абдулла"):
    db.save_group("-100902", "N-1", tasks="m,r,t")
    db.add_student(name, db.get_group("-100902")["id"], phone=phone)


def _request(method, path, headers=None, body=None):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request(method, path, headers=headers or {}, json=body)
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def _token(phone=PHONE):
    code = wa.new_login_code()
    wa.claim_login_code(code, phone)
    return {"Authorization": "Bearer " + wa.take_session_for_code(code)[0]}


# ── база ──────────────────────────────────────────────────────────────────

def test_no_such_person_is_none(test_db):
    assert db.get_profile("нет-такого") is None


def test_reads_what_registration_wrote(test_db):
    _student()
    assert db.get_profile(PHONE) == {"name": "Абдулла", "birth_year": None, "location": ""}


def test_name_change_is_seen_by_the_group(test_db):
    """Имя лежит в users.name - оттуда же его берут рейтинг и отчёты
    устазу. Если бы правка легла в другое место, человек переименовался бы
    только у себя на экране."""
    _student()
    db.update_profile(PHONE, name="Абдуллах")
    group = db.get_group("-100902")
    assert [s["name"] for s in db.get_students(group["id"])] == ["Абдуллах"]


def test_name_cannot_be_erased(test_db):
    _student()
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="name_empty"):
            db.update_profile(PHONE, name=bad)
    assert db.get_profile(PHONE)["name"] == "Абдулла"


def test_spaces_in_name_are_tidied(test_db):
    _student()
    assert db.update_profile(PHONE, name="  Абу   Бакр ")["name"] == "Абу Бакр"


def test_birth_year_refuses_nonsense(test_db):
    _student()
    this_year = int(db.get_date()[:4])
    for bad in ("позавчера", 1800, this_year, this_year + 10, 55):
        with pytest.raises(ValueError, match="birth_year_bad"):
            db.update_profile(PHONE, birth_year=bad)


def test_birth_year_can_be_taken_back(test_db):
    """Год рождения - по желанию, значит и передумать можно."""
    _student()
    db.update_profile(PHONE, birth_year=1994)
    assert db.get_profile(PHONE)["birth_year"] == 1994
    db.update_profile(PHONE, birth_year="")
    assert db.get_profile(PHONE)["birth_year"] is None


def test_only_given_fields_are_touched(test_db):
    _student()
    db.update_profile(PHONE, birth_year=1994, location="Чуйская область")
    db.update_profile(PHONE, name="Абдуллах")
    p = db.get_profile(PHONE)
    assert (p["name"], p["birth_year"], p["location"]) == ("Абдуллах", 1994, "Чуйская область")


def test_filled_profile_closes_the_dm_survey(test_db):
    """Человек сказал это сам - значит бот больше не спрашивает."""
    _student()
    db.update_profile(PHONE, birth_year=1994)
    assert db.get_survey_stage(PHONE) != "done"     # места ещё нет
    db.update_profile(PHONE, location="Ош")
    assert db.get_survey_stage(PHONE) == "done"


# ── через HTTP ────────────────────────────────────────────────────────────

def test_profile_needs_authorization(test_db):
    assert _request("GET", "/api/muf/profile")[0] == 401


def test_profile_round_trip_over_http(test_db, test_hadiths_db):
    _student()
    headers = _token()
    assert _request("GET", "/api/muf/profile", headers)[1]["name"] == "Абдулла"

    status, data = _request("POST", "/api/muf/profile", headers,
                            {"location": "Иссык-Кульская область"})
    assert status == 200 and data["location"] == "Иссык-Кульская область"
    assert _request("GET", "/api/muf/profile", headers)[1]["location"] == "Иссык-Кульская область"


def test_bad_value_comes_back_as_400_with_a_code(test_db, test_hadiths_db):
    """Приложению нужен код, а не текст: сообщение человеку оно подбирает
    само, на его языке."""
    _student()
    status, data = _request("POST", "/api/muf/profile", _token(), {"name": "  "})
    assert status == 400 and data["error"] == "name_empty"


def test_empty_body_is_not_a_silent_success(test_db, test_hadiths_db):
    _student()
    assert _request("POST", "/api/muf/profile", _token(), {})[0] == 400
