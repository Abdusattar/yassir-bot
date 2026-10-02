"""Переход relaxed→pro - в группу по странице заучивания (02.10.2026).

Эрлан с подготовительной ушёл в N-2a, наименее заполненную, где все далеко
впереди. Теперь - группа, чья медиана страниц ближе к странице студента.
"""
import core.db as db


def _pro(chat_id, title, pages, monkeypatch_pages):
    db.save_group(chat_id, title)
    db.update_group_type(chat_id, "pro")
    g = db.get_group(chat_id)
    db.set_group_invite_link(g["id"], "https://t.me/+" + title)
    for i, p in enumerate(pages):
        phone = chat_id.strip("-") + str(i)
        db.add_student("S", g["id"], phone=phone)
        monkeypatch_pages[phone] = p
    return g


def _setup(monkeypatch):
    pages = {}
    monkeypatch.setattr(db, "hifz_page", lambda phone: pages.get(phone))
    low = _pro("-1001", "G-2c", [4, 11, 12, 15], pages)
    mid = _pro("-1002", "G 2b", [14, 15, 16, 17, 19], pages)
    high = _pro("-1003", "N-2a", [11, 20, 22, 23], pages)
    return low, mid, high


def test_page_picks_nearest_median(test_db, monkeypatch):
    low, mid, high = _setup(monkeypatch)
    assert db.get_best_pro_group_for_upgrade("ru", 10)["id"] == low["id"]
    assert db.get_best_pro_group_for_upgrade("ru", 16)["id"] == mid["id"]
    assert db.get_best_pro_group_for_upgrade("ru", 25)["id"] == high["id"]


def test_no_page_falls_back_to_least_filled(test_db, monkeypatch):
    low, mid, high = _setup(monkeypatch)
    assert db.get_best_pro_group_for_upgrade("ru", None)["cnt"] == 4


def test_full_group_skipped(test_db, monkeypatch):
    low, mid, high = _setup(monkeypatch)
    for i in range(db.UPGRADE_MAX_GROUP_SIZE):
        db.add_student("X", mid["id"], phone="9" + str(i))
    assert db.get_best_pro_group_for_upgrade("ru", 16)["id"] != mid["id"]


def test_n1_never_offered(test_db, monkeypatch):
    pages = {}
    monkeypatch.setattr(db, "hifz_page", lambda phone: pages.get(phone))
    _pro("-1004", "N-1", [30], pages)
    assert db.get_best_pro_group_for_upgrade("ru", 30) is None
