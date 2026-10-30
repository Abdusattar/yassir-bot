"""В приложении на кыргызском, узбекском и китайском нет русских дыр (19.10.2026,
китайский - 20.10.2026).

15.10 пользователь заметил: узбекский интерфейс «не везде». 16.10 недостающие
ключи словаря закрыты, 19.10 переведены главы «Знаний» (онбординг и
«Правила»). Тест держит это: у ky/uz есть каждый ключ русского словаря
(кроме русских форм множественного числа) и каждый текст глав LEARN, а
подстановки %N% совпадают с русскими.

Словарь и LEARN берутся прямо из index.html и разбираются в node - без node
пропускаем.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="нужен node")

HTML = os.path.join(os.path.dirname(__file__), "..", "mushaf_data", "index.html")

# Формы «few/many» есть только у русского: pulsePlural зовётся лишь при ru.
RU_ONLY = re.compile(r"^(n|pulse_sub)_[a-z]+_(few|many)$")


def _block(src, start, end):
    """Литерал с последней скобки маркера до закрывающей скобки на два пробела."""
    a = src.index(start) + len(start) - 1
    return src[a:src.index(end, a) + len(end)]


@pytest.fixture(scope="module")
def app():
    with open(HTML, encoding="utf-8") as f:
        src = f.read()
    # С 30.10.2026 таблица - в i18nTable(): экран входа сайта зовёт T() раньше,
    # чем скрипт доходит до неё (см. index.html).
    js = ("var I18N = %s; var LEARN = %s; console.log(JSON.stringify({I18N: I18N, LEARN: LEARN}));"
          % (_block(src, "function i18nTable() { return {", "\n  };"), _block(src, "var LEARN = [", "\n  ];")))
    # Через stdin: словарь не влезает в командную строку Windows.
    out = subprocess.run(["node"], input=js, capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _learn_keys(learn):
    for sec in learn:
        yield "learn_%s_name" % sec["id"]
        yield "learn_%s_desc" % sec["id"]
        for k in range(len(sec["steps"])):
            yield "learn_%s_%d_t" % (sec["id"], k)
            yield "learn_%s_%d_b" % (sec["id"], k)


@pytest.mark.parametrize("lang", ["ky", "uz", "zh"])
def test_dictionary_has_every_russian_key(app, lang):
    ru, other = app["I18N"]["ru"], app["I18N"][lang]
    missing = [k for k in ru if k not in other and not RU_ONLY.search(k)]
    assert missing == []


@pytest.mark.parametrize("lang", ["ky", "uz", "zh"])
def test_learn_chapters_translated(app, lang):
    other = app["I18N"][lang]
    missing = [k for k in _learn_keys(app["LEARN"]) if k not in other]
    assert missing == []


@pytest.mark.parametrize("lang", ["ky", "uz", "zh"])
def test_placeholders_match_russian(app, lang):
    ru, other = app["I18N"]["ru"], app["I18N"][lang]
    bad = [k for k in other if k in ru
           and sorted(re.findall(r"%[A-Z]%", ru[k])) != sorted(re.findall(r"%[A-Z]%", other[k]))]
    assert bad == []
