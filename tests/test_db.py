import pytest
from core.db import (
    save_group, get_group, add_student, get_students,
    find_by_phone, find_by_name, register_student, deactivate_student,
    save_report, get_today_report, get_streak_days, get_skip_count_month,
    add_bonus, get_date, count_report_days_since,
    get_users_due_for_survey, get_users_due_for_survey_nudge, start_survey,
    get_survey_stage,
    save_survey_location, save_survey_age, survey_answer_in_window, mark_dm_ok_by_phone, db,
    add_group_admin, get_now,
    has_any_group_history, save_dm_registration_name,
)


# ── Группы ────────────────────────────────────────────────────────────────────

def test_save_and_get_group(test_db):
    save_group("-100111", "Тестовая группа", tasks="m,r,t")
    g = get_group("-100111")
    assert g is not None
    assert g["title"] == "Тестовая группа"
    assert g["tasks"] == "m,r,t"


def test_get_group_not_found(test_db):
    assert get_group("-999999") is None


# ── Студенты ──────────────────────────────────────────────────────────────────

def test_add_and_get_students(test_db):
    save_group("-100222", "Группа А")
    g = get_group("-100222")
    add_student("Бакыт", g["id"])
    students = get_students(g["id"])
    assert len(students) == 1
    assert students[0]["name"] == "Бакыт"


def test_find_by_phone(test_db):
    save_group("-100333", "Группа Б")
    g = get_group("-100333")
    sid = add_student("Азамат", g["id"], phone="111222333")
    found = find_by_phone("111222333", g["id"])
    assert found is not None
    assert found["name"] == "Азамат"


def test_find_by_phone_not_found(test_db):
    save_group("-100334", "Группа В")
    g = get_group("-100334")
    assert find_by_phone("000000000", g["id"]) is None


def test_find_by_name(test_db):
    save_group("-100335", "Группа Г")
    g = get_group("-100335")
    add_student("Закир", g["id"])
    found = find_by_name("Закир", g["id"])
    assert found is not None


def test_register_student_sets_phone(test_db):
    save_group("-100336", "Группа Д")
    g = get_group("-100336")
    sid = add_student("Нурлан", g["id"])
    register_student(sid, "555666777")
    found = find_by_phone("555666777", g["id"])
    assert found is not None
    assert found["name"] == "Нурлан"


def test_deactivate_student(test_db):
    save_group("-100337", "Группа Е")
    g = get_group("-100337")
    sid = add_student("Тимур", g["id"], phone="333444555")
    deactivate_student(sid, g["id"])
    assert find_by_phone("333444555", g["id"]) is None


# ── Отчёты ────────────────────────────────────────────────────────────────────

def test_save_and_get_today_report(test_db):
    save_group("-100444", "Группа Ж")
    g = get_group("-100444")
    sid = add_student("Алибек", g["id"], phone="777888999")
    today = get_date()
    save_report(sid, g["id"], today, {"m": True, "r": True, "t": False})
    rep = get_today_report(sid)
    assert rep is not None
    assert rep["m"] == 1
    assert rep["r"] == 1
    assert rep["t"] == 0


def test_streak_zero_for_new_student(test_db):
    save_group("-100555", "Группа З")
    g = get_group("-100555")
    sid = add_student("Мирлан", g["id"])
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 0


def test_streak_one_day(test_db):
    save_group("-100556", "Группа И")
    g = get_group("-100556")
    sid = add_student("Санжар", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 1


def test_streak_broken_by_partial_day(test_db):
    """Строгое правило (07.08.2026): не все 3 задания в день - день не
    засчитывается в серию, даже если что-то сдано."""
    save_group("-100558", "Группа Л")
    g = get_group("-100558")
    sid = add_student("Нурлан", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": False})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 0


def test_streak_grace_for_today_not_yet_reported(test_db):
    """Без явной даты (for_date=None) и без сегодняшнего отчёта серия не
    обнуляется - считается по вчерашний день включительно."""
    from datetime import timedelta
    from core.db import get_now
    save_group("-100559", "Группа М")
    g = get_group("-100559")
    sid = add_student("Ислам", g["id"])
    yesterday = (get_now() - timedelta(days=1)).date().isoformat()
    save_report(sid, g["id"], yesterday, {"m": True, "r": True, "t": True})
    assert get_streak_days(sid, g["id"], ["m", "r", "t"]) == 1


def test_count_report_days_since_ignores_partial_days(test_db):
    """12.08.2026: раньше день засчитывался в prep-порог с ЛЮБЫМ одним
    заданием - лазейка, противоречившая решению устаза (все три
    обязательны с первого дня). Теперь тот же строгий критерий, что у
    стрика."""
    save_group("-100560", "Группа Н", tasks="m,r,t")
    g = get_group("-100560")
    sid = add_student("Азим", g["id"])
    save_report(sid, g["id"], get_date(), {"m": True, "r": False, "t": False})
    assert count_report_days_since(sid, g["id"], get_date()) == 0


def test_count_report_days_since_counts_full_days(test_db):
    from datetime import timedelta
    from core.db import get_now
    save_group("-100561", "Группа О", tasks="m,r,t")
    g = get_group("-100561")
    sid = add_student("Бахтияр", g["id"])
    yesterday = (get_now() - timedelta(days=1)).date().isoformat()
    save_report(sid, g["id"], yesterday, {"m": True, "r": True, "t": True})
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert count_report_days_since(sid, g["id"], yesterday) == 2


def test_count_report_days_since_respects_lower_bound(test_db):
    from datetime import timedelta
    from core.db import get_now
    save_group("-100562", "Группа П", tasks="m,r,t")
    g = get_group("-100562")
    sid = add_student("Умар", g["id"])
    old_day = (get_now() - timedelta(days=20)).date().isoformat()
    save_report(sid, g["id"], old_day, {"m": True, "r": True, "t": True})
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    assert count_report_days_since(sid, g["id"], get_date()) == 1


def test_skip_count_zero_for_new_student(test_db):
    save_group("-100557", "Группа К")
    g = get_group("-100557")
    sid = add_student("Руслан", g["id"])
    assert get_skip_count_month(sid) == 0


# ── Бонусы ────────────────────────────────────────────────────────────────────

def test_add_bonus(test_db):
    from core.db import db
    save_group("-100666", "Группа Л")
    g = get_group("-100666")
    sid = add_student("Данияр", g["id"])
    add_bonus(sid, g["id"], get_date(), 10, "bonus", subcategory="тест")
    with db() as c:
        row = c.execute(
            "SELECT SUM(points) as total FROM score_events WHERE student_id=? AND category='bonus'",
            (sid,)
        ).fetchone()
    assert row["total"] == 10


# ── Анкета "откуда и сколько лет" ───────────────────────────────────────────────
# Триггер - 2 дня после joined_date в постоянной (pro/relaxed) группе, не
# added_date (редизайн 17.08.2026).

def _make_survey_candidate(test_db, phone="700111", days_ago=3, dm_ok=1, chat_id="-100790"):
    save_group(chat_id, "Группа С")
    g = get_group(chat_id)
    sid = add_student("Гульнара", g["id"], phone=phone)
    with db() as c:
        c.execute(
            "UPDATE user_groups SET joined_date=date('now', ?) "
            "WHERE user_id=? AND group_id=?",
            (f"-{days_ago} days", sid, g["id"])
        )
        c.execute("UPDATE users SET dm_ok=? WHERE id=?", (dm_ok, sid))
    return sid


def test_get_users_due_for_survey_includes_eligible(test_db):
    _make_survey_candidate(test_db, phone="700111", days_ago=3, dm_ok=1)
    due = get_users_due_for_survey()
    assert [r["phone"] for r in due] == ["700111"]


def test_get_users_due_for_survey_excludes_too_recent(test_db):
    _make_survey_candidate(test_db, phone="700112", days_ago=1, dm_ok=1)
    assert get_users_due_for_survey() == []


def test_get_users_due_for_survey_excludes_dm_not_ok(test_db):
    _make_survey_candidate(test_db, phone="700113", days_ago=3, dm_ok=0)
    assert get_users_due_for_survey() == []


def test_get_users_due_for_survey_excludes_already_started(test_db):
    _make_survey_candidate(test_db, phone="700114", days_ago=3, dm_ok=1)
    start_survey("700114")
    assert get_users_due_for_survey() == []


def test_survey_flow_location_then_age(test_db):
    _make_survey_candidate(test_db, phone="700115", days_ago=3, dm_ok=1)
    assert get_survey_stage("700115") is None

    start_survey("700115")
    assert get_survey_stage("700115") == "asked_location"

    save_survey_location("700115", "Бишкек")
    assert get_survey_stage("700115") == "asked_age"

    save_survey_age("700115", "22")
    assert get_survey_stage("700115") == "done"

    with db() as c:
        row = c.execute(
            "SELECT survey_location, survey_age, survey_birth_year FROM users WHERE phone=?",
            ("700115",)
        ).fetchone()
    assert row["survey_location"] == "Бишкек"
    assert row["survey_age"] == "22"
    assert row["survey_birth_year"] == get_now().year - 22


def test_save_survey_location_greeting_triggers_one_retry_then_accepts(test_db):
    """Ответ на вопрос про локацию - голое приветствие (рефлекс на прошлый
    текст вопроса) - переспрашиваем один раз, второй ответ принимаем как
    есть, даже если снова не похож на место (17.08.2026, найдено на
    реальных ответах: 3 из первых 10 ответили приветствием)."""
    _make_survey_candidate(test_db, phone="700122", days_ago=3, dm_ok=1)
    start_survey("700122")

    stage = save_survey_location("700122", "Ваалейкум ассалам")
    assert stage == "location_retry"
    assert get_survey_stage("700122") == "location_retry"

    stage = save_survey_location("700122", "Сокулук")
    assert stage == "asked_age"
    with db() as c:
        row = c.execute("SELECT survey_location FROM users WHERE phone=?", ("700122",)).fetchone()
    assert row["survey_location"] == "Сокулук"


@pytest.mark.parametrize("text,expected_stage", [
    ("Ваалейкум ассалам", "location_retry"),
    ("Уа Алейкум Ас Салям", "location_retry"),
    ("Ассаляму алейкум", "location_retry"),
    ("Ош", "asked_age"),
    ("Сокулук", "asked_age"),
    ("Кыргызстан Бишкек", "asked_age"),
    ("Германия", "asked_age"),
])
def test_save_survey_location_greeting_detection(test_db, text, expected_stage):
    """Короткие легитимные ответы ("Ош" - 2 буквы) не должны попадать под
    переспрос - регресс-тест на баг, пойманный до коммита (17.08.2026).
    Каждый вызов параметризован на свою изолированную test_db, так что
    фиксированные phone/chat_id между вариантами не конфликтуют."""
    phone = "700199"
    _make_survey_candidate(test_db, phone=phone, days_ago=3, dm_ok=1, chat_id="-100799")
    start_survey(phone)
    assert save_survey_location(phone, text) == expected_stage


def test_save_survey_age_garbage_triggers_one_retry_then_accepts(test_db):
    """Первый нераспознанный ответ -> один переспрос (asked_age_retry), а не
    сразу 'done'. Второй нераспознанный ответ -> принимается как есть, год
    рождения остаётся NULL, анкета не виснет вечно (17.08.2026)."""
    _make_survey_candidate(test_db, phone="700117", days_ago=3, dm_ok=1)
    start_survey("700117")
    save_survey_location("700117", "Бишкек")

    stage = save_survey_age("700117", "не скажу")
    assert stage == "asked_age_retry"
    assert get_survey_stage("700117") == "asked_age_retry"

    stage = save_survey_age("700117", "секрет")
    assert stage == "done"
    with db() as c:
        row = c.execute(
            "SELECT survey_age, survey_birth_year FROM users WHERE phone=?", ("700117",)
        ).fetchone()
    assert row["survey_age"] == "секрет"
    assert row["survey_birth_year"] is None


def test_save_survey_age_retry_recovers_with_valid_number(test_db):
    _make_survey_candidate(test_db, phone="700120", days_ago=3, dm_ok=1)
    start_survey("700120")
    save_survey_location("700120", "Ош")
    assert save_survey_age("700120", "не скажу") == "asked_age_retry"
    assert save_survey_age("700120", "мне 30") == "done"
    with db() as c:
        row = c.execute("SELECT survey_birth_year FROM users WHERE phone=?", ("700120",)).fetchone()
    assert row["survey_birth_year"] == get_now().year - 30


def test_survey_answer_in_window(test_db):
    _make_survey_candidate(test_db, phone="700121", days_ago=3, dm_ok=1)
    start_survey("700121")
    assert survey_answer_in_window("700121") is True

    with db() as c:
        c.execute(
            "UPDATE users SET survey_stage_at=datetime('now', '-25 hours') WHERE phone=?",
            ("700121",)
        )
    assert survey_answer_in_window("700121") is False


def test_get_users_due_for_survey_includes_admin_who_is_also_student(test_db):
    """Устаз, который сам тоже студент где-то (в постоянной группе 2+ дня,
    dm_ok=1) - раньше исключался (13.08.2026, найдено эдвайзери: перехват
    ответа анкеты мог поймать его обычную команду). С 17.08.2026 - общая
    политика ВКЛЮЧАТЬ (решение пользователя, сам в такой ситуации) - теперь
    безопасно благодаря 24-часовому окну (survey_answer_in_window)."""
    save_group("-100791", "Группа Т")
    g1 = get_group("-100791")
    save_group("-100792", "Группа У")
    g2 = get_group("-100792")
    sid = add_student("Умар", g1["id"], phone="700116")
    add_group_admin(g2["id"], "700116")
    with db() as c:
        c.execute(
            "UPDATE user_groups SET joined_date=date('now', '-3 days') "
            "WHERE user_id=? AND group_id=?",
            (sid, g1["id"])
        )
        c.execute("UPDATE users SET dm_ok=1 WHERE id=?", (sid,))
    assert [r["phone"] for r in get_users_due_for_survey()] == ["700116"]


def test_get_users_due_for_survey_returns_all_eligible(test_db):
    save_group("-100793", "Группа Ф")
    g = get_group("-100793")
    for i in range(7):
        sid = add_student(f"Студент{i}", g["id"], phone=f"70012{i}")
        with db() as c:
            c.execute(
                "UPDATE user_groups SET joined_date=date('now', '-3 days') "
                "WHERE user_id=? AND group_id=?",
                (sid, g["id"])
            )
            c.execute("UPDATE users SET dm_ok=1 WHERE id=?", (sid,))
    assert len(get_users_due_for_survey()) == 7


def test_get_users_due_for_survey_nudge(test_db):
    """Застрял на asked_location 8 дней без ответа -> попадает в nudge;
    свежий (1 день назад) - не попадает (17.08.2026)."""
    _make_survey_candidate(test_db, phone="700118", days_ago=3, dm_ok=1, chat_id="-100794")
    start_survey("700118")
    with db() as c:
        c.execute(
            "UPDATE users SET survey_stage_at=datetime('now', '-8 days') WHERE phone=?",
            ("700118",)
        )
    due = get_users_due_for_survey_nudge()
    assert [r["phone"] for r in due] == ["700118"]

    _make_survey_candidate(test_db, phone="700119", days_ago=3, dm_ok=1, chat_id="-100795")
    start_survey("700119")
    phones = [r["phone"] for r in get_users_due_for_survey_nudge()]
    assert "700119" not in phones


# ── DM-регистрация нового человека (17.08.2026) ─────────────────────────────────

def test_has_any_group_history(test_db):
    save_group("-100796", "Группа Х")
    g = get_group("-100796")
    add_student("Хасан", g["id"], phone="700123")
    assert has_any_group_history("700123") is True
    assert has_any_group_history("700999") is False


def test_save_dm_registration_name_simple(test_db):
    """Нет предварительно добавленного тёзки - просто ставим имя на
    строку, которую создал mark_dm_ok_by_phone."""
    mark_dm_ok_by_phone("700124")
    save_dm_registration_name("700124", "Азамат")
    with db() as c:
        row = c.execute("SELECT name, phone, dm_ok FROM users WHERE phone=?", ("700124",)).fetchone()
    assert row["name"] == "Азамат"
    assert row["dm_ok"] == 1


def test_save_dm_registration_name_merges_with_preadded_student(test_db):
    """Устаз уже добавил "Азамат" через /add (phone IS NULL, есть в группе).
    Тот же Азамат потом жмёт новую Start-ссылку и называет своё имя -
    должен связаться с уже существующей записью, а не создать вторую
    личность (17.08.2026, поймано advisor до коммита)."""
    save_group("-100797", "Группа Ц")
    g = get_group("-100797")
    preadded_uid = add_student("Азамат", g["id"], phone=None)

    mark_dm_ok_by_phone("700125")
    save_dm_registration_name("700125", "Азамат")

    with db() as c:
        # Заглушка (name='', phone='700125') не должна остаться отдельной строкой
        stub = c.execute("SELECT * FROM users WHERE phone=? AND name=''", ("700125",)).fetchone()
        assert stub is None

        merged = c.execute("SELECT * FROM users WHERE id=?", (preadded_uid,)).fetchone()
        assert merged["phone"] == "700125"
        assert merged["name"] == "Азамат"

        # Только одна строка с этим телефоном, не две
        count = c.execute("SELECT count(*) as n FROM users WHERE phone=?", ("700125",)).fetchone()["n"]
        assert count == 1

    # Уже привязан к группе (Group Ц) со времён /add - has_any_group_history
    # должен это видеть, чтобы дальше не предлагать подготовительную заново.
    assert has_any_group_history("700125") is True


def test_save_dm_registration_name_no_unique_conflict_if_stub_already_named(test_db):
    """Если строка-заглушка на этом телефоне почему-то уже не пустая (гонка
    / неожиданное состояние) - DELETE не находит её, и код не должен потом
    упасть на UNIQUE(phone) при попытке привязать тот же телефон к
    найденной по имени /add-записи (17.08.2026, поймано advisor)."""
    save_group("-100798", "Группа Ч")
    g = get_group("-100798")
    add_student("Азамат", g["id"], phone=None)

    mark_dm_ok_by_phone("700126")
    with db() as c:
        c.execute("UPDATE users SET name='Уже-Не-Пусто' WHERE phone=?", ("700126",))

    save_dm_registration_name("700126", "Азамат")

    with db() as c:
        count = c.execute("SELECT count(*) as n FROM users WHERE phone=?", ("700126",)).fetchone()["n"]
        row = c.execute("SELECT name FROM users WHERE phone=?", ("700126",)).fetchone()
    assert count == 1
    assert row["name"] == "Азамат"
