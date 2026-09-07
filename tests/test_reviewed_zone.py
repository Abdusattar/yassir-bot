"""Зона «Проверено» кабинета устаза: что показывает строка (07.09.2026).

Решения пользователя:
  - строку можно открыть и посмотреть то же, что видит студент, — поэтому в
    списке едут признаки содержимого (пометки слов, голос разбора);
  - «на пересдачу» перестаёт быть долгом в тот момент, когда студент записал
    новую сдачу той же единицы (то же правило, что у гейта), — иначе карточка
    висит с красной пометкой, хотя ответ студента уже лежит в «Ждут».
"""

import core.db as db


CHAT = "-100444101"


def _group():
    db.save_group(CHAT, "N-1", tasks="m,r,t")
    return db.get_group(CHAT)


def _submission(sid, group, msg_id, page, line, stage, file_id=True):
    db.save_voice_submission(sid, group["id"], CHAT, msg_id, db.get_date(),
                             file_id=("f%d" % msg_id) if file_id else None,
                             hifz_page=page, hifz_line=line, hifz_stage=stage)
    return db.get_student_submissions(sid)[0]["id"]


def _reviewed(group):
    return db.get_reviewed_submissions([group["id"]])


def test_пометки_и_голос_видны_в_списке(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777101")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.save_submission_review(CHAT, 1, "voice", review_file_id="rev1", review_by="888002")
    db.set_submission_verdict(sub_id, db.VERDICT_ACCEPTED, "888002",
                              [{"line": 7, "word": 2}, {"line": 7, "word": 5}])

    row = _reviewed(group)[0]

    assert row["marks"] == 2
    assert row["has_review_audio"] is True
    assert row["has_audio"] is True


def test_принято_молчком_без_содержимого(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777101")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.set_submission_verdict(sub_id, db.VERDICT_ACCEPTED, "888002")

    row = _reviewed(group)[0]

    assert row["marks"] == 0
    assert row["has_review_audio"] is False


def test_пересдача_ждёт_пока_студент_не_ответил(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777101")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.save_submission_review(CHAT, 1, "voice", review_file_id="rev1", review_by="888002")
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002", [{"line": 7, "word": 2}])

    row = _reviewed(group)[0]

    assert row["verdict"] == db.VERDICT_RETAKE
    assert row["redone"] is False


def test_новая_запись_того_же_места_закрывает_долг(test_db):
    """Пересдал — карточка перестаёт быть долгом, даже если разбор новой
    записи ещё не сделан: гейт снимает сам факт пересдачи."""
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777101")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.save_submission_review(CHAT, 1, "voice", review_file_id="rev1", review_by="888002")
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002", [{"line": 7, "word": 2}])

    _submission(sid, group, 2, 6, 7, 1)      # ответ студента

    row = [r for r in _reviewed(group) if r["id"] == sub_id][0]
    assert row["redone"] is True


def test_сдача_другого_места_долг_не_закрывает(test_db):
    group = _group()
    sid = db.add_student("Сатар", group["id"], phone="777101")
    sub_id = _submission(sid, group, 1, 6, 7, 1)
    db.save_submission_review(CHAT, 1, "voice", review_file_id="rev1", review_by="888002")
    db.set_submission_verdict(sub_id, db.VERDICT_RETAKE, "888002", [{"line": 7, "word": 2}])

    _submission(sid, group, 2, 6, 3, 1)      # другая строка того же листа

    row = [r for r in _reviewed(group) if r["id"] == sub_id][0]
    assert row["redone"] is False
