"""Сборка приложения из app_src (12.11.2026, scripts/build_app.py).

1. mushaf_data/index.html обязан быть равен сборке из app_src: править можно только
   исходники, а готовый файл - результат. Разошлись - значит, кто-то поправил одно
   и забыл другое, и на прод ушло бы не то, что лежит в исходниках.
2. Каждый кусок JS обязан разбираться сам по себе (как тело функции): граница куска
   не должна проходить посреди оператора, иначе файл нельзя ни проверить, ни прочитать.
3. В каждом куске CSS скобки сходятся: граница не проходит посреди правила или @media.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_app  # noqa: E402


def test_index_equals_build():
    built = build_app.build()
    current = build_app.read(build_app.OUT)
    assert built == current, (
        "mushaf_data/index.html не равен сборке из app_src.\n" + build_app.first_diff(built, current)
        + "\nПравили app_src -> python scripts/build_app.py"
          "\nПравили index.html напрямую -> python scripts/build_app.py --adopt")


def test_template_has_no_code():
    """В каркасе - только разметка: стили и код живут в кусках."""
    tpl = build_app.read(build_app.SRC / "index.html")
    assert tpl.count(build_app.CSS_MARK) == 1 and tpl.count(build_app.JS_MARK) == 1
    assert tpl.count("<style>") == 1


def test_css_parts_balanced():
    for f in build_app.parts("css"):
        text = re.sub(r"/\*.*?\*/", "", build_app.read(f), flags=re.S)
        text = re.sub(r"\"[^\"\n]*\"|'[^'\n]*'", "", text)
        assert text.count("{") == text.count("}"), "%s: скобки не сходятся - граница посреди правила" % f.name


@pytest.mark.skipif(not shutil.which("node"), reason="нет node")
def test_js_parts_parse():
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in build_app.parts("js"):
            probe = os.path.join(tmp, f.name)
            with open(probe, "w", encoding="utf-8", newline="") as fh:
                fh.write("(function () {\n" + build_app.read(f) + "})();\n")
            r = subprocess.run(["node", "--check", probe], capture_output=True, text=True, encoding="utf-8")
            if r.returncode:
                bad.append("%s: %s" % (f.name, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "ошибка"))
    assert not bad, "куски JS не разбираются сами по себе:\n" + "\n".join(bad)
