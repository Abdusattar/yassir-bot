"""Голосовое в группе и указатель 40+40 (13.09.2026, Ибрахим из Н-1).

Голосовое в группе двигает указатель вперёд (решение 02.09) - но не у того,
кто сдаёт из приложения: его голосовое в группе - ответ устазу на замечание,
и такое голосовое увело Ибрахима с первой половины листа на вторую.
Признак «сдаёт из приложения» - хоть одна сдача с местом на листе."""

import core.db as db


def _student(name, phone):
    db.save_group("-100555", "N-test", tasks="m,r,t")
    g = db.get_group("-100555")
    db.add_student(name, g["id"], phone=phone)
    return db.find_user_by_phone(phone), g


def test_group_only_student_has_no_app_submissions(test_db):
    u, g = _student("Голосовой", "p-voice")
    db.save_voice_submission(u["id"], g["id"], "-100555", 11, db.get_date(), file_id="v1")
    assert db.has_app_submissions(u["id"]) is False


def test_app_submission_marks_student_as_app_user(test_db):
    u, g = _student("Ибрахим", "p-app")
    db.save_voice_submission(u["id"], g["id"], "-100555", 12, db.get_date(), file_id="v2",
                             hifz_page=13, hifz_line=0, hifz_stage=2)
    # Потом голосовое в группе (ответ устазу) - признак не пропадает.
    db.save_voice_submission(u["id"], g["id"], "-100555", 13, db.get_date(), file_id="v3")
    assert db.has_app_submissions(u["id"]) is True
