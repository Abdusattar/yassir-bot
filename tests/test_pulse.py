"""«Дыхание Яссира»: ритм джамаата для главного экрана (core/pulse.py).

Проверяем ровно то, на чём экран может соврать: что задания и разборы устаза
попадают в ОДИН счёт, что вторая база складывается с первой, что отсутствие
второй базы (локальная разработка, раннер Actions) ничего не ломает, и что
кэш не отдаёт вчерашний ответ после того, как его сбросили.
"""
import core.db as db
import core.pulse as pulse


CHAT = "-100777001"


def _fresh(monkeypatch, path):
    """Пульс читает свою базу через core.db, а парную — по пути рядом с DB."""
    monkeypatch.setattr(pulse, "DB", path)
    pulse._cache["at"] = 0.0
    pulse._cache["data"] = None


def _group():
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    return db.get_group(CHAT)


def test_tasks_and_ustaz_reviews_share_one_count(test_db, monkeypatch):
    _fresh(monkeypatch, test_db)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_report(sid, group["id"], today, {"m": True, "r": True, "t": True})
    db.save_voice_submission(sid, group["id"], CHAT, 10, today, file_id="own")
    db.mark_voice_reviewed(CHAT, 10)

    data = pulse.get_pulse()

    assert data["today"]["m"] == 1
    assert data["today"]["r"] == 1
    assert data["today"]["t"] == 1
    # Разбор устаза — такое же действие джамаата, идёт в общий счёт.
    assert data["today"]["review"] == 1
    assert data["today"]["people"] == 1
    assert sum(data["today"]["hourly"]) == 4
    assert data["days"][-1]["date"] == today
    assert data["people_total"] == 1


def test_pair_database_adds_up(test_db, monkeypatch, tmp_path):
    """Мужской и женский боты — две базы, но джамаат один: цифры общие."""
    _fresh(monkeypatch, test_db)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    today = db.get_date()
    db.save_report(sid, group["id"], today, {"m": True})

    # Вторая база рядом со своей, с тем же именем, что ищет _pair_path().
    pair = tmp_path / ("quran_%s.db" % ("female" if pulse.PROFILE == "male" else "male"))
    monkeypatch.setattr(pulse, "DB", str(tmp_path / ("quran_%s.db" % pulse.PROFILE)))
    real_db = db.DB
    monkeypatch.setattr(db, "DB", str(pair))
    db.init()
    db.save_group("-100777002", "Ж-1", tasks="m,r,t")
    g2 = db.get_group("-100777002")
    sid2 = db.add_student("Айша", g2["id"], phone="777002")
    db.save_report(sid2, g2["id"], today, {"m": True, "r": True})
    monkeypatch.setattr(db, "DB", real_db)

    data = pulse.get_pulse()

    assert data["today"]["m"] == 2      # по одному заданию из каждой базы
    assert data["today"]["r"] == 1
    assert data["today"]["people"] == 2
    assert data["people_total"] == 2


def test_missing_pair_database_is_not_an_error(test_db, monkeypatch):
    """На машине разработчика и в раннере второй базы нет вовсе."""
    _fresh(monkeypatch, test_db)
    monkeypatch.setattr(pulse, "_pair_path", lambda: None)

    data = pulse.get_pulse()

    assert data["days"]
    assert data["today"]["people"] == 0
    assert data["quiet_min"] is None


def test_broken_pair_database_leaves_own_half(test_db, monkeypatch, tmp_path):
    """Второй бот мог остановиться посреди миграции — главный экран должен
    показать свою половину джамаата, а не упасть."""
    _fresh(monkeypatch, test_db)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_report(sid, group["id"], db.get_date(), {"m": True})
    broken = tmp_path / "broken.db"
    broken.write_text("это не sqlite", encoding="utf-8")
    monkeypatch.setattr(pulse, "_pair_path", lambda: str(broken))

    data = pulse.get_pulse()

    assert data["today"]["m"] == 1


def test_best_day_ignores_today(test_db, monkeypatch):
    """Рекорд — планка из прошлого: неполный сегодняшний день ей не считается."""
    _fresh(monkeypatch, test_db)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    with db.db() as c:
        c.execute(
            "INSERT INTO score_events(student_id,group_id,date,category,subcategory,points)"
            " VALUES(?,?,date('now','-1 day'),'task','m',1)", (sid, group["id"]))
        c.execute(
            "INSERT INTO score_events(student_id,group_id,date,category,subcategory,points)"
            " VALUES(?,?,date('now','-1 day'),'task','r',1)", (sid, group["id"]))
    db.save_report(sid, group["id"], db.get_date(), {"m": True})

    data = pulse.get_pulse()

    assert data["best"]["total"] == 2
    assert data["best"]["date"] != db.get_date()


def test_cache_holds_between_calls(test_db, monkeypatch):
    _fresh(monkeypatch, test_db)
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777001")
    db.save_report(sid, group["id"], db.get_date(), {"m": True})

    first = pulse.get_pulse()
    db.save_report(sid, group["id"], db.get_date(), {"r": True})
    second = pulse.get_pulse()

    assert second is first                  # минуту отдаём тот же ответ
    pulse._cache["at"] = 0.0
    assert pulse.get_pulse()["today"]["r"] == 1
