"""Тренажёр таджвида: карточки сифатов (24.09.2026) - снимки глазами.

Стенд shoot_onboarding + группе стенда включён таджвид, опубликованы уроки
первой и второй пары, а все места выхода «отдыхают» (выучены, срок впереди) -
поэтому первой приходит карточка сифата. Сцены: пара на два варианта
(هَمْس/جَهْر) и на три (شِدَّة/تَوَسُّط/رَخَاوَة), до ответа и после ошибки.

    python scripts/shoot_tajweed_sifat.py
    python scripts/shoot_tajweed_sifat.py --engine webkit

Снимки: logs/tajweed_sifat/<сцена>.png. Playwright WebKit - не iOS.
"""
import argparse
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

OUT = ROOT / "logs" / "tajweed_sifat"
PORT = 8813
SIF = "صفات الحروف (Свойства букв)"


def prepare(pair):
    """pair: 'hams' - открыта только первая пара, 'shidda' - и вторая, а
    первая выучена. Места выхода выучены всегда."""
    from core import db, curriculum
    import core.tajweed_trainer as tt
    with sqlite3.connect(db.DB) as c:
        c.execute("UPDATE groups SET tasks='m,r,t,j' WHERE chat_id=?", (stand.CHAT,))
        c.execute("UPDATE curriculum_parts SET published_at='2026-09-10' WHERE subject='j'")
        for n, topic in ((50, "Первая пара: الهمس и الجهر"), (51, "Вторая пара: الشدة، الرخاوة и التوسط")):
            if pair == "hams" and n == 51:
                # База стенда живёт между прогонами: вторую пару убираем явно.
                c.execute("DELETE FROM group_lessons WHERE part_id IN"
                          " (SELECT id FROM curriculum_parts WHERE topic=?)", (topic,))
                c.execute("DELETE FROM curriculum_parts WHERE topic=?", (topic,))
                continue
            if not c.execute("SELECT 1 FROM curriculum_parts WHERE topic=?", (topic,)).fetchone():
                c.execute("INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
                          " order_index, content, published_at) VALUES('j',?,?,1,1,?,'Текст','2026-09-20')",
                          (SIF, topic, n))
        c.execute("DELETE FROM tajweed_card_stats WHERE user_id=?", (stand.STUDENT,))
        rest = [x["id"] for x in tt.CARDS if x["kind"] == "makhraj" or (pair == "shidda" and x["kind"] == "hams")]
        for cid in rest:
            c.execute("INSERT INTO tajweed_card_stats(user_id, card, shown, correct, streak, due)"
                      " VALUES(?,?,3,3,3,'2099-01-01')", (stand.STUDENT, cid))
    curriculum.backfill()
    tt._sessions.clear()


def build():
    app = stand.build_app()

    async def page(request):
        prepare(request.query.get("pair", "hams"))
        return web.Response(text=stand.dev_index(), content_type="text/html")

    app.router.add_get("/t", page)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="chromium")
    args = ap.parse_args()
    threading.Thread(target=lambda: web.run_app(build(), host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        b = getattr(pw, args.engine).launch()
        for pair in ("hams", "shidda"):
            ctx = b.new_context(viewport={"width": 390, "height": 844})
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{PORT}/t?pair={pair}&bot=male")
            pg.wait_for_timeout(2500)
            pg.evaluate("document.getElementById('dash-trainer').click()")
            pg.wait_for_timeout(1200)
            pg.evaluate("document.getElementById('trh-tajweed').click()")
            pg.wait_for_selector(".tj-opt", timeout=15000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / f"{pair}.png"))
            m = pg.evaluate("""() => ({ q: document.querySelector('.tj-q').textContent,
                opts: Array.prototype.map.call(document.querySelectorAll('.tj-opt'), b => b.textContent),
                doc_x: document.documentElement.scrollWidth - document.documentElement.clientWidth })""")
            print(f"  {pair:<7} {m}")
            # Нарочно мимо: на экране должны остаться верный (зелёный) и нажатый (красный).
            pg.evaluate("""() => { var bs=document.querySelectorAll('.tj-opt'); bs[bs.length-1].click(); }""")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=str(OUT / f"{pair}_after.png"))
            want = 2 if pair == "hams" else 3
            if len(m["opts"]) != want:
                problems.append(f"{pair}: вариантов {len(m['opts'])}, ждали {want}")
            if m["q"] == "Откуда выходит буква?":
                problems.append(f"{pair}: пришла карточка места выхода, а не сифата")
            if m["doc_x"] > 0 or errors:
                problems.append(f"{pair}: вылезает {m['doc_x']} / ошибки {errors[:2]}")
            ctx.close()
        b.close()
    print("\nПРОБЛЕМЫ:" if problems else "\nпроблем нет")
    for p in problems:
        print("  " + p)


if __name__ == "__main__":
    main()
