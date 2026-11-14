# -*- coding: utf-8 -*-
"""Сквозная проверка: приложение открывается на стенде (wiki/architecture.md Р5, 14.11.2026).

Остальные тесты не запускают приложение в браузере: поломка загрузки листа или пустой
экран «Сегодня» проходила все проверки. Здесь - собранный index.html на стенде
(scripts/shoot_onboarding.py, ненастоящий API) в Chromium 390×844:

  - «Сегодня» не пустой, ошибок скрипта нет;
  - лист мусхафа рисуется в обеих раскладках, у слов есть подписи, тап открывает подсказку;
  - тренажёр слов открывается.

Нужны Playwright с Chromium и листы page50.json (в git их нет, только у разработчика и на
сервере) - иначе тест пропускается (на GitHub Actions так и будет; ловит он перед пушем).
Это не iOS Safari: живой айфон всё равно нужен.
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
pw_api = pytest.importorskip("playwright.sync_api")
if not ((ROOT / "mushaf_data" / "page50.json").exists() and (ROOT / "mushaf_data" / "dm" / "page50.json").exists()):
    pytest.skip("нет листов мусхафа для стенда", allow_module_level=True)


@pytest.fixture(scope="module")
def stand_url():
    os.environ.setdefault("LAND_PORT", "8829")
    sys.path.insert(0, str(ROOT / "scripts"))
    import shoot_landscape as land
    land.serve({"e2e": land.page_html(None)})
    return "http://127.0.0.1:%s/e2e?bot=male" % land.PORT


@pytest.fixture(scope="module")
def browser():
    with pw_api.sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001 - Chromium не установлен
            pytest.skip("Chromium для Playwright не установлен: %s" % type(e).__name__)
        yield b
        b.close()


def _open(browser, url, layout=""):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
    ctx.add_init_script("try{localStorage.setItem('yassir_mushaf_page','50');"
                        "localStorage.setItem('yassir_mushaf_layout','%s')}catch(e){}" % layout)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(url)
    pg.wait_for_function("!!document.getElementById('dash-mushaf')", timeout=15000)
    pg.wait_for_timeout(2500)        # вход и первые ответы API стенда
    return ctx, pg, errors


def test_today_is_not_empty(browser, stand_url):
    ctx, pg, errors = _open(browser, stand_url)
    pg.wait_for_timeout(1500)
    text = pg.evaluate("document.getElementById('dash-doors').innerText.trim().length")
    hero = pg.evaluate("(document.getElementById('dash-hero').innerText || '').trim().length")
    ctx.close()
    assert text > 20, "«Сегодня»: карточки пустые"
    assert hero > 0, "«Сегодня»: главная карточка пустая"
    assert errors == []


@pytest.mark.parametrize("layout", ["", "dm"])
def test_mushaf_page_words_and_popup(browser, stand_url, layout):
    ctx, pg, errors = _open(browser, stand_url, layout)
    pg.evaluate("document.getElementById('dash-mushaf').click()")
    pg.wait_for_function("document.querySelectorAll('#ayah-text .mushaf-line').length > 0", timeout=15000)
    pg.wait_for_function("document.querySelectorAll('#ayah-text [data-tr]').length > 50", timeout=15000)
    empty = pg.evaluate("Array.from(document.querySelectorAll('#ayah-text [data-tr]'))"
                        ".filter(e => !e.getAttribute('data-tr')).length")
    pg.evaluate("document.querySelectorAll('#ayah-text [data-tr]')[12].click()")
    pg.wait_for_function("(document.getElementById('word-popup').innerText || '').trim().length > 0", timeout=5000)
    ctx.close()
    assert empty == 0, "у %d слов пустая подпись" % empty
    assert errors == []


def test_trainer_opens(browser, stand_url):
    ctx, pg, errors = _open(browser, stand_url)
    pg.evaluate("document.getElementById('dash-trainer').click()")
    pg.wait_for_function("(function(){var a=document.getElementById('trainers-body'),"
                         "b=document.getElementById('trainer-body');"
                         "return ((a&&a.innerText)||'').trim().length + ((b&&b.innerText)||'').trim().length > 10})()",
                         timeout=15000)
    ctx.close()
    assert errors == []
