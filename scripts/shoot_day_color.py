"""Цвет дня в «Моём месяце» и у устаза (11.11.2026) - снимки глазами.

Повод - Розалина: в группе 4 задания, 3 из 4 горело как полный день.
Стенд shoot_onboarding, группе стенда ставим 4 задания (m,r,t,j) без даты
«обязательно с», и сеем дни этого месяца по кругу: 4 из 4, 3 из 4, 2 из 4,
1 из 4, ничего. Снимки: свой месяц студента и календарь студента у устаза.
Картинки «Знаний» не трогаем - пишем в logs/day_color/.

    python scripts/shoot_day_color.py
"""
import pathlib
import sqlite3
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "day_color"
PORT = 8815
PATTERN = ["mrtj", "mrj", "mr", "m", "", "mrtj", "mrtj", "mrt"]


def _seed_days(db, uid, gid, month, last):
    with sqlite3.connect(db.DB) as c:
        c.execute("UPDATE groups SET tasks='m,r,t,j' WHERE id=?", (gid,))
        c.execute("DELETE FROM group_task_since WHERE group_id=?", (gid,))
        c.execute("DELETE FROM score_events WHERE student_id=? AND group_id=? AND date LIKE ?",
                  (uid, gid, month + "-%"))
    for day in range(1, last):
        keys = PATTERN[(day - 1) % len(PATTERN)]
        if keys:
            db.save_report(uid, gid, "%s-%02d" % (month, day), {k: True for k in keys})


def seed():
    from core import db
    import core.mufradat as m
    for uid in (stand.STUDENT, stand.USTAZ):
        m.set_current_lang(uid, "ru")    # язык мог остаться от съёмки «Знаний» на zh
    # У устаза первой открывается N-1 - сеем тот же узор её первому студенту.
    with sqlite3.connect(db.DB) as c:
        row = c.execute("SELECT g.id, u.id FROM groups g JOIN user_groups ug ON ug.group_id=g.id"
                        " JOIN users u ON u.id=ug.user_id WHERE g.title='N-1' AND u.name='Ибрахим'"
                        " AND ug.role='student'").fetchone()
    if row:
        _seed_days(db, row[1], row[0], db.get_date()[:7], int(db.get_date()[8:10]))
    # Группа, которую приложение берёт как учебную (у стенда это не CHAT).
    g = db.get_learning_group(stand.STUDENT, include_prep=True)
    u = db.find_user_by_phone(stand.STUDENT)
    today = db.get_date()
    month = today[:7]
    with sqlite3.connect(db.DB) as c:
        c.execute("UPDATE groups SET tasks='m,r,t,j' WHERE id=?", (g["id"],))
        c.execute("DELETE FROM group_task_since WHERE group_id=?", (g["id"],))
        c.execute("DELETE FROM score_events WHERE student_id=? AND group_id=? AND date LIKE ?",
                  (u["id"], g["id"], month + "-%"))
    for day in range(1, int(today[8:10])):
        keys = PATTERN[(day - 1) % len(PATTERN)]
        if keys:
            db.save_report(u["id"], g["id"], "%s-%02d" % (month, day), {k: True for k in keys})


def build():
    app = stand.build_app()

    async def student(request):
        seed()
        return web.Response(text=stand.dev_index(), content_type="text/html")

    async def ustaz(request):
        seed()
        return web.Response(text=stand.dev_index(stand.USTAZ, "Устаз"), content_type="text/html")

    app.router.add_get("/s", student)
    app.router.add_get("/u", ustaz)
    return app


def main():
    threading.Thread(target=lambda: web.run_app(build(), host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 844})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{PORT}/s?bot=male")
        pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('dash-subs').click()")
        pg.wait_for_timeout(1800)
        pg.evaluate("document.getElementById('subs-month').click()")
        pg.wait_for_timeout(1200)
        pg.evaluate("var c=document.querySelector('.stu-cal'); if (c) c.scrollIntoView({block:'center'})")
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(OUT / "student_month.png"))
        cells = pg.evaluate("Array.prototype.map.call(document.querySelectorAll('.stu-cal .c:not(.empty)'),"
                            " e => e.textContent.trim() + ':' + e.className).slice(0, 9)")
        print("студент:", cells)

        pg.goto(f"http://127.0.0.1:{PORT}/u?bot=male")
        pg.wait_for_timeout(2500)
        pg.evaluate("document.getElementById('dash-ustaz').click()")
        pg.wait_for_timeout(1900)
        pg.evaluate("document.querySelector('.ustaz-zones [data-zone=\"students\"]').click()")
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(OUT / "ustaz_list.png"))
        pg.evaluate("Array.prototype.forEach.call(document.querySelectorAll('[data-sid]'),"
                    " function (e) { if (e.textContent.indexOf('Ибрахим') >= 0) e.click(); })")
        pg.wait_for_timeout(2000)
        pg.screenshot(path=str(OUT / "ustaz_student.png"))
        cells = pg.evaluate("Array.prototype.map.call(document.querySelectorAll('.c:not(.empty)'),"
                            " e => e.textContent.trim() + ':' + e.className).slice(0, 9)")
        print("устаз:", cells)
        print("ошибки:", errors[:3])
        b.close()


if __name__ == "__main__":
    main()
