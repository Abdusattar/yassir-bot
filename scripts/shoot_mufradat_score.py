"""Тренажёр слов: «Выучено N%», итог сеанса в словах, точность за дни,
строка рейтинга (11.11.2026) - снимки глазами.

Стенд shoot_onboarding, закладка стр. 3. Прогресс студента ставится явно:
  full    - все слова пула выучены: карточка повтора и итог «всё держится»;
  partial - 15 слов не выучены, за сеанс 3 стали выученными (+3);
  down    - за сеанс 2 выученных слова сорвались (ошибка) - «нужно повторить».
Сдвиг «за сеанс» делается маршрутом /shift уже после открытия тренажёра:
сервер запоминает выученное при первом вопросе, потом прогресс меняется.

    python scripts/shoot_mufradat_score.py

Снимки: logs/muf_score/<сцена>.png. Стенд: http://127.0.0.1:8814/m?mode=partial
"""
import pathlib
import sqlite3
import sys
import threading
import time
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "muf_score"
PORT = 8814
HDB = str(stand.TMP / "hadiths.db")


def _pool():
    import core.mufradat as m
    return sorted({w["progress_key"] for w in m.get_words_for_bookmark(stand.STUDENT)})


def prepare(mode):
    import core.mufradat as m
    import core.mufradat_api as api
    stand.set_state("words")                # закладка стр. 3, дневной счёт 12/7
    keys = _pool()
    not_learned = set(keys[:15]) if mode in ("partial", "down") else set()
    with sqlite3.connect(HDB) as c:
        m._ensure_progress_schema(c)
        c.execute("DELETE FROM mufradat_progress WHERE user_id=?", (stand.STUDENT,))
        c.executemany(
            "INSERT INTO mufradat_progress(user_id, word_id, correct_streak, wrong_count, days_correct,"
            " correct_count) VALUES(?,?,?,?,?,?)",
            [(stand.STUDENT, k, 2 if k in not_learned else m.MASTERY_STREAK, 1, 3, 6) for k in keys])
        # Точность за дни: 9 дней по 40 ответов, 4 ошибки в день - 90%.
        c.execute(m._DAILY_STATS_SCHEMA)
        c.execute("DELETE FROM mufradat_daily_stats WHERE user_id=?", (stand.STUDENT,))
        today = date.fromisoformat(m._today())
        c.executemany("INSERT INTO mufradat_daily_stats(user_id, date, correct, wrong) VALUES(?,?,?,?)",
                      [(stand.STUDENT, (today - timedelta(days=d)).isoformat(), 36, 4) for d in range(9)])
    api._active.pop(stand.STUDENT, None)   # новый сеанс - новое «выучено на старте»
    return keys


def shift(mode):
    """То, что случилось «за сеанс»: partial - 3 слова дошли до выученного,
    down - 2 выученных сорвались."""
    import core.mufradat as m
    keys = _pool()
    with sqlite3.connect(HDB) as c:
        if mode == "partial":
            for k in keys[:3]:
                c.execute("UPDATE mufradat_progress SET correct_streak=? WHERE user_id=? AND word_id=?",
                          (m.MASTERY_STREAK, stand.STUDENT, k))
        if mode == "down":
            for k in keys[-2:]:
                c.execute("UPDATE mufradat_progress SET correct_streak=0 WHERE user_id=? AND word_id=?",
                          (stand.STUDENT, k))


def build():
    app = stand.build_app()

    async def page(request):
        prepare(request.query.get("mode", "partial"))
        return web.Response(text=stand.dev_index(), content_type="text/html")

    async def do_shift(request):
        shift(request.query.get("mode", ""))
        return web.Response(text="ok")

    app.router.add_get("/m", page)
    app.router.add_get("/shift", do_shift)
    return app


def main():
    threading.Thread(target=lambda: web.run_app(build(), host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for mode in ("full", "partial", "down"):
            ctx = b.new_context(viewport={"width": 390, "height": 844})
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{PORT}/m?mode={mode}&bot=male")
            pg.wait_for_timeout(2500)
            pg.evaluate("document.getElementById('dash-trainer').click()")
            pg.wait_for_timeout(1200)
            pg.evaluate("document.getElementById('trh-words').click()")
            pg.wait_for_selector("#tr-end", timeout=15000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / f"{mode}_card.png"))
            pg.evaluate(f"fetch('/shift?mode={mode}')")
            pg.wait_for_timeout(500)
            pg.evaluate("document.getElementById('tr-end').click()")
            pg.wait_for_selector("#tr-restart", timeout=15000)
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / f"{mode}_end.png"))
            info = pg.evaluate("""() => Array.prototype.map.call(
                document.querySelectorAll('.trainer-learned, .trainer-info'), e => e.textContent)""")
            print(f"  {mode:<8} {info}")
            if mode == "partial":
                pg.evaluate("document.getElementById('tr-restart').click()")
                pg.wait_for_selector("#tr-top", timeout=15000)
                pg.evaluate("document.getElementById('tr-top').click()")
                pg.wait_for_selector(".trainer-lb-order", timeout=15000)
                pg.wait_for_timeout(800)
                pg.screenshot(path=str(OUT / "leaderboard.png"))
            doc_x = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if doc_x > 0 or errors:
                problems.append(f"{mode}: вылезает {doc_x} / ошибки {errors[:2]}")
            ctx.close()
        b.close()
    print("\nПРОБЛЕМЫ:" if problems else "\nпроблем нет")
    for p in problems:
        print("  " + p)


if __name__ == "__main__":
    main()
