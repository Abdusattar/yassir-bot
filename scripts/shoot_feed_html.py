# -*- coding: utf-8 -*-
"""Снимок ленты с сообщением бота в HTML-разметке Telegram (12.11.2026), 390x844, обе темы.

Лента хранит текст бота как он ушёл в Telegram (<b>, ссылки); приложение должно
рисовать оформление, а не показывать теги. Ответ /feed подменяем (route).

    python scripts/shoot_feed_html.py     # -> logs/feed_html/feed_{light,dark}.png
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("LAND_PORT", "8814")
import shoot_landscape as land              # noqa: E402

OUT = ROOT / "logs" / "feed_html"
TEXT = ("📖 <b>Пословный перевод: обновление</b>\n\nАссаляму алейкум! Мы обновляем русские подписи "
        "под словами Корана &amp; начали с первого джуза.\n\n<b>Что изменилось:</b> подписи читаются "
        "фразой, без скобок и «досл.».\n\nВсе изменения: <a href=\"https://yassirilm.com/wbw/\">yassirilm.com/wbw</a>"
        "\n\n<i>Команда Яссир</i>")
FEED = {"chats": [{"id": "-100", "title": "N-1", "unread": 1}],
        "items": [{"id": 2, "chat_id": "-100", "source": "N-1", "who": "Яссир", "is_bot": True, "kind": "text",
                   "text": TEXT, "has_media": False, "mine": False, "at": "2026-11-12 10:00:00"},
                  {"id": 1, "chat_id": "-100", "source": "N-1", "who": "Абдулла", "is_bot": False, "kind": "text",
                   "text": "Пишу <b> как текст", "has_media": False, "mine": False, "at": "2026-11-12 09:00:00"}]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    land.serve({"new": land.page_html(None)})
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for theme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, color_scheme=theme)
            ctx.add_init_script("try{localStorage.setItem('yassir_theme','%s');}catch(e){}" % theme)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.route("**/feed", lambda r: r.fulfill(status=200, content_type="application/json",
                                                     body=json.dumps(FEED, ensure_ascii=False)))
            pg.route("**/feed/read", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.goto(f"http://127.0.0.1:{land.PORT}/new?bot=male")
            pg.wait_for_timeout(2500)
            pg.evaluate("document.getElementById('dash-brief').click()")
            pg.wait_for_timeout(1200)
            txt = pg.evaluate("Array.from(document.querySelectorAll('#feed .l-txt')).map(e => e.innerHTML)")
            print(theme, txt, "ошибки JS:", errs)
            pg.screenshot(path=str(OUT / f"feed_{theme}.png"))
            ctx.close()
        b.close()


if __name__ == "__main__":
    main()
