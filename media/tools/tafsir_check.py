"""Проверка контекста аята по тафсирам (05.10.2026, «Яссир Медиа», strategy.md §6).

Сверка текста и перевода (quran.com) не отвечает на вопрос «не вырван ли аят из
контекста». Для этого - тафсиры: ас-Саади (рус., quran.com id 170), Ибн Касир
сокращённый (англ., 169), ат-Тафсир аль-Муяссар (араб., 16). Скрипт кладёт их рядом
с роликом, вывод о соответствии пишется в README ролика с источниками. Умар устаза
зовём, только если толкования расходятся или тема тонкая (хадис, сира, фикх).

    python media/tools/tafsir_check.py 13:28 media/videos/01_skolko_golosov
"""
import json
import pathlib
import re
import sys
import urllib.request

TAFSIRS = [(170, "ас-Саади (рус.)"), (169, "Ибн Касир, сокр. (англ.)"), (16, "аль-Муяссар (араб.)")]
API = "https://api.quran.com/api/v4"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # без него 403
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def main():
    key, out_dir = sys.argv[1], pathlib.Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    arabic = _get(f"{API}/quran/verses/uthmani?verse_key={key}")["verses"][0]["text_uthmani"]
    kuliev = _get(f"{API}/quran/translations/45?verse_key={key}")["translations"][0]["text"]
    lines = [f"# Тафсиры {key}", "", arabic, "", f"Кулиев: {kuliev}", ""]
    for tid, name in TAFSIRS:
        t = _get(f"{API}/tafsirs/{tid}/by_ayah/{key}")["tafsir"]
        lines += [f"## {name}", "", _plain(t.get("text")), ""]
    path = out_dir / f"tafsir_{key.replace(':', '_')}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
