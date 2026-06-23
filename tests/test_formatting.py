from core.db import (
    save_group, get_group, add_student, save_report, get_date,
    format_daily_report, format_period_report,
)


def test_daily_report_empty_group(test_db):
    save_group("-100777", "Группа М")
    g = get_group("-100777")
    report = format_daily_report(g["id"], "Группа М", ["m", "r", "t"])
    assert "Группа М" in report
    assert isinstance(report, str)


def test_daily_report_with_student(test_db):
    save_group("-100778", "Группа Н")
    g = get_group("-100778")
    sid = add_student("Эрлан", g["id"], phone="111000111")
    save_report(sid, g["id"], get_date(), {"m": True, "r": True, "t": True})
    report = format_daily_report(g["id"], "Группа Н", ["m", "r", "t"])
    assert "Эрлан" in report


def test_period_report_empty_group(test_db):
    save_group("-100779", "Группа О")
    g = get_group("-100779")
    report = format_period_report(g["id"], "Группа О", ["m", "r", "t"], 7)
    assert "Группа О" in report
    assert isinstance(report, str)


def test_period_report_with_student(test_db):
    save_group("-100780", "Группа П")
    g = get_group("-100780")
    sid = add_student("Карим", g["id"], phone="222000222")
    save_report(sid, g["id"], get_date(), {"m": True, "r": False, "t": True})
    report = format_period_report(g["id"], "Группа П", ["m", "r", "t"], 7)
    assert "Карим" in report
