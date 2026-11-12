# -*- coding: utf-8 -*-
"""Сборка приложения: app_src/ -> mushaf_data/index.html (12.11.2026).

Зачем. index.html - 19 500 строк в одном файле: правят его несколько человек, и любая
параллельная правка - конфликт. Но разрезать его «по-настоящему» (отдельные файлы,
которые грузит браузер) без переписывания кода нельзя: весь JS - одна замкнутая функция
`(function () { ... })();`, ~14 500 строк с общими переменными. Поэтому первый шаг -
разрезать ИСХОДНИКИ, а на прод по-прежнему уходит один файл, байт в байт тот же, что и
до разреза. Поведение приложения не меняется вообще; сервер, кэш, service worker,
стенды и тесты как читали mushaf_data/index.html, так и читают.

Как устроено:
  app_src/index.html      каркас: разметка, а на месте стилей и кода - две метки
  app_src/css/NNN_*.css   куски <style>, склеиваются по порядку имён
  app_src/js/NNN_*.js     куски тела той самой функции, склеиваются по порядку имён

Куски JS - не самостоятельные скрипты, а подряд идущие части одного тела функции:
переменные и функции одного файла видны во всех остальных. Порядок важен (номер в имени).

Правило: править app_src/, потом собрать. mushaf_data/index.html руками не править.
Он остаётся в git как результат сборки (деплой и стенды берут его), а тест
tests/test_app_build.py не даст запушить, если он разошёлся с исходниками.

    python scripts/build_app.py            # собрать app_src -> mushaf_data/index.html
    python scripts/build_app.py --check    # сравнить, ничего не писать (код 1 - разошлись)
    python scripts/build_app.py --adopt    # наоборот: разложить index.html по файлам app_src
    python scripts/build_app.py --split js/140_x.js 166 142_confirm
                                           # отрезать от куска хвост со строки 166 в новый кусок

--adopt - для переходного времени и для слияний: если index.html правили напрямую (старая
ветка, конфликт слияния решён в нём), команда раскладывает его обратно по кускам. Границы
ищет по первой строке каждого существующего куска, поэтому первую строку куска (обычно
комментарий-заголовок раздела) не менять. Новый кусок: создать файл с его первой строкой
и запустить --adopt, либо просто вырезать руками и собрать.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "app_src"
OUT = ROOT / "mushaf_data" / "index.html"
CSS_MARK = "/*@@APP_CSS@@*/\n"
JS_MARK = "/*@@APP_JS@@*/\n"
# Границы областей в готовом index.html (для --adopt). Строки целиком.
CSS_OPEN, CSS_CLOSE = "<style>\n", "</style>\n"
JS_OPEN, JS_CLOSE = "<script>\n(function () {\n", "})();\n</script>\n"


def read(path):
    """Текст с LF: git на Windows отдаёт рабочую копию с CRLF, на сервере LF."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def parts(kind):
    files = sorted((SRC / kind).glob("*." + kind))
    if not files:
        raise SystemExit("нет кусков в app_src/%s" % kind)
    return files


def build():
    tpl = read(SRC / "index.html")
    for mark in (CSS_MARK, JS_MARK):
        if tpl.count(mark) != 1:
            raise SystemExit("в app_src/index.html метка %s должна быть ровно одна" % mark.strip())
    out = tpl
    for kind, mark in (("css", CSS_MARK), ("js", JS_MARK)):
        body = ""
        for f in parts(kind):
            text = read(f)
            if not text.endswith("\n"):
                raise SystemExit("%s: файл должен кончаться переводом строки" % f.relative_to(ROOT))
            body += text
        out = out.replace(mark, body)
    return out


def region(text, open_, close, last=False):
    """(до, тело, после) - тело между открывающей и закрывающей строками."""
    a = text.index(open_) + len(open_)
    b = text.rindex(close) if last else text.index(close, a)
    return text[:a], text[a:b], text[b:]


def split_by_anchors(body, files, kind):
    """Режет тело по первым строкам существующих кусков, по порядку."""
    lines = body.split("\n")
    assert lines[-1] == "", "тело области должно кончаться переводом строки"
    lines.pop()
    cuts, pos = [0], 0
    for f in files[1:]:
        anchor = read(f).split("\n", 1)[0]
        if not anchor.strip():
            raise SystemExit("%s: первая строка пустая - по ней границу не найти" % f.name)
        try:
            pos = lines.index(anchor, pos + 1)
        except ValueError:
            raise SystemExit("в index.html не нашёл начало куска %s/%s:\n  %s\n"
                             "(первую строку куска меняли? верни её или вырежи кусок руками)"
                             % (kind, f.name, anchor))
        cuts.append(pos)
    cuts.append(len(lines))
    return ["\n".join(lines[a:b]) + "\n" for a, b in zip(cuts, cuts[1:])]


def adopt():
    text = read(OUT)
    head, css, rest = region(text, CSS_OPEN, CSS_CLOSE)
    mid, js, tail = region(rest, JS_OPEN, JS_CLOSE, last=True)
    changed = []
    for kind, body in (("css", css), ("js", js)):
        files = parts(kind)
        for f, chunk in zip(files, split_by_anchors(body, files, kind)):
            if read(f) != chunk:
                write(f, chunk)
                changed.append("%s/%s" % (kind, f.name))
    tpl = head + CSS_MARK + mid + JS_MARK + tail
    if read(SRC / "index.html") != tpl:
        write(SRC / "index.html", tpl)
        changed.append("index.html")
    if build() != text:
        raise SystemExit("после раскладки сборка не равна index.html - это ошибка скрипта, не пушить")
    print("разложено по app_src; изменились: " + (", ".join(changed) or "ничего"))


def split(rel, line, new_name):
    """Хвост куска со строки line (с 1) - в новый кусок. Сборка от этого не меняется:
    новый кусок по имени должен встать сразу после старого."""
    f = SRC / rel
    kind = f.suffix[1:]
    new = f.with_name(new_name + "." + kind)
    lines = read(f).split("\n")
    head, tail = lines[:line - 1], lines[line - 1:]
    if not head or not tail[0].strip() or new.exists():
        raise SystemExit("нельзя: пустая голова, пустая первая строка нового куска или файл уже есть")
    names = [p.name for p in parts(kind)]
    after = names.index(f.name)
    if not (f.name < new.name and (after + 1 == len(names) or new.name < names[after + 1])):
        raise SystemExit("имя %s не встаёт сразу после %s - порядок сборки изменился бы" % (new.name, f.name))
    before = build()
    write(f, "\n".join(head) + "\n")
    write(new, "\n".join(tail))
    if build() != before:
        raise SystemExit("сборка изменилась - это ошибка, откати: git checkout app_src")
    print("%s: %d строк; %s: %d строк; сборка та же" % (f.name, len(head), new.name, len(tail) - 1))


def first_diff(a, b):
    la, lb = a.split("\n"), b.split("\n")
    for i, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return "строка %d:\n  сборка:     %s\n  index.html: %s" % (i, x[:110], y[:110])
    return "разная длина: сборка %d строк, index.html %d" % (len(la), len(lb))


def check():
    built, cur = build(), read(OUT)
    if built == cur:
        print("ок: mushaf_data/index.html равен сборке из app_src")
        return 0
    print("РАЗОШЛИСЬ: mushaf_data/index.html не равен сборке из app_src.\n" + first_diff(built, cur))
    print("Правили app_src -> python scripts/build_app.py\n"
          "Правили index.html напрямую -> python scripts/build_app.py --adopt")
    return 1


def main():
    if "--check" in sys.argv:
        sys.exit(check())
    if "--adopt" in sys.argv:
        adopt()
        return
    if "--split" in sys.argv:
        i = sys.argv.index("--split")
        split(sys.argv[i + 1], int(sys.argv[i + 2]), sys.argv[i + 3])
        return
    built = build()
    if OUT.exists() and read(OUT) == built:
        print("без изменений: mushaf_data/index.html уже равен сборке")
        return
    write(OUT, built)
    print("собрано: mushaf_data/index.html, %d строк" % built.count("\n"))


if __name__ == "__main__":
    main()
