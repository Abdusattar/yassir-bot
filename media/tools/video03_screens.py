"""Экраны приложения для ролика 3 «Путь» (05.10.2026): стенд + Playwright, 1080 px по ширине.

Сцены стенда scripts/shoot_onboarding.py, но без обучающей подсветки (.onb-spot)
и в высоком разрешении (390x844 CSS при DPR 1080/390).

    python media/tools/video03_screens.py   # PNG в media/videos/03_put/screens/
"""
import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import shoot_onboarding as stand    # noqa: E402
from aiohttp import web             # noqa: E402

OUT = ROOT / "media" / "videos" / "03_put" / "screens"
PORT = 8796
SCENES = ["dash", "pointer", "word_tap", "trainer_q", "rec"]
CLEAN = ("html body .onb-spot{outline:none!important;box-shadow:none!important}"
         "html body #rotate-hint,html body .rotate-hint{display:none!important}")


def main():
    app = stand.build_app()
    import sqlite3
    from core import db
    with sqlite3.connect(db.DB) as c:     # тестовое объявление с доски - не для ролика
        c.execute("DELETE FROM feed_messages WHERE notice_link='help:whatsapp'")
    threading.Thread(target=lambda: web.run_app(app, host="127.0.0.1", port=PORT, print=None,
                                                handle_signals=False), daemon=True).start()
    time.sleep(3)
    OUT.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for scene in SCENES:
            stand.set_state(stand.PRE_STATE.get(scene, "fresh"))
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1080 / 390)
            pg = ctx.new_page()
            pg.add_init_script("document.addEventListener('DOMContentLoaded',function(){"
                               "var s=document.createElement('style');s.textContent=%r;"
                               "document.head.appendChild(s)})" % CLEAN)
            pg.goto("http://127.0.0.1:%d/?bot=male&scene=%s" % (PORT, scene))
            pg.wait_for_timeout(9000)
            pg.screenshot(path=str(OUT / ("%s.png" % scene)))
            ctx.close()
            print("ok", scene)
        b.close()


if __name__ == "__main__":
    main()
