"""Тренажёр хадисов на стенде (23.09.2026): снимки всего пути глазами.

Хаб «Тренажёры» → «Хадис» → выбор хадиса → выбор слова → слово дня →
закрепление (вопрос в обе стороны, верный и неверный ответ) → итог.
Группе стенда включается задание «h», как у N-1.

    python scripts/shoot_hadith.py                 # 390x844
    python scripts/shoot_hadith.py --w 360 --h 740

Снимки: logs/hadith/<шаг>.png. Плюс замер: не вылезает ли что-то вбок.
"""
import argparse
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand            # noqa: E402
import core.db as db                        # noqa: E402
from aiohttp import web                     # noqa: E402

OUT = ROOT / "logs" / "hadith"
PORT = 8813
OVER = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=390)
    ap.add_argument("--h", type=int, default=844)
    ap.add_argument("--hadith", type=int, default=8)
    ap.add_argument("--pos", type=int, default=9)
    a = ap.parse_args()

    app = stand.build_app()
    db.update_group_tasks(stand.CHAT, "m,r,t,h")
    with db.db() as c:
        for t in ("hadith_progress", "hadith_new_words", "hadith_answers", "hadith_sessions"):
            c.execute("DELETE FROM %s WHERE user_id=?" % t, (stand.STUDENT,))
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    problems = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": a.w, "height": a.h})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def shot(name):
            pg.wait_for_timeout(700)
            pg.screenshot(path=str(OUT / (name + ".png")))
            over = pg.evaluate(OVER)
            if over > 0:
                problems.append("%s: вылезает вбок на %dpx" % (name, over))
            print("  ", name)

        pg.goto("http://127.0.0.1:%d/?bot=male" % PORT)
        pg.wait_for_timeout(2500)
        pg.click("#dash-trainer")
        pg.wait_for_timeout(1000)
        shot("1_hub")
        pg.click("#trh-hadith")
        pg.wait_for_selector(".hd-pick button")
        shot("2_pick_hadith")
        pg.click(".hd-pick button[data-n='%d']" % a.hadith)
        pg.wait_for_selector(".hd-words button")
        shot("3_pick_word")
        pg.click(".hd-words button[data-i='%d']" % a.pos)
        pg.wait_for_selector("#hd-learn")
        shot("4_word_of_day")
        pg.click("#hd-learn")
        pg.wait_for_selector(".hd-opt")
        shot("5_card_ar2ru")
        # Неверный ответ - чтобы увидеть разбор и «вернётся в конце захода».
        right = pg.evaluate("() => null")
        import core.hadith_trainer as ht
        cur = ht._load_session(stand.STUDENT)["current"]
        wrong = next(o["key"] for o in cur["options"] if o["key"] != cur["right"])
        pg.click(".hd-opt[data-key=\"%s\"]" % wrong.replace('"', '\\"'))
        pg.wait_for_selector("#hd-next")
        shot("6_wrong")
        pg.click("#hd-next")
        pg.wait_for_selector(".hd-opt")
        shot("7_card_next")
        # Что под вариантами: прокрутили до конца - хадис и смысловой перевод.
        pg.evaluate("() => { var b = document.getElementById('hadith-body'); b.scrollTop = b.scrollHeight; }")
        shot("7c_scrolled")
        pg.evaluate("() => { document.getElementById('hadith-body').scrollTop = 0; }")
        first_right = True
        for _ in range(12):
            if not pg.query_selector(".hd-opt:not([disabled])"):
                break
            cur = ht._load_session(stand.STUDENT)["current"]
            if cur is None:
                break
            pg.click(".hd-opt[data-key=\"%s\"]" % cur["right"].replace('"', '\\"'))
            pg.wait_for_selector("#hd-next")
            if first_right:
                first_right = False
                pg.wait_for_timeout(1500)
                pg.screenshot(path=str(OUT / "7d_right_running.png"))
                print("   7d_right_running")
            pg.click("#hd-next")
            pg.wait_for_timeout(500)
        pg.wait_for_selector("#hd-round")
        shot("8_finished")
        if errors:
            problems.append("ошибки страницы: %s" % errors[:3])
        b.close()
    print("\nПРОБЛЕМЫ:" if problems else "\nпроблем нет")
    for p in problems:
        print("  " + p)


if __name__ == "__main__":
    main()
