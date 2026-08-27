"""Добавляет смысловой перевод (Кулиев, api.quran.com resource_id=45) в уже
экспортированные страницы мусхафа (mushaf_data/page{N}.json) - отдельным
проходом, не трогая scripts/export_mushaf_page.py, чтобы не гонять заново
дорогой таджвид+глиф-запрос по всем 604 страницам ради одного нового поля.

Разрешение правообладателя на постоянное размещение перевода в нашем
приложении подтверждено пользователем лично 28.08.2026 ("подтвердили,
дали зелёный свет") - тот же принцип, что и с шрифтом/вёрсткой QUL, см.
feedback_never_invent_quran_translations в памяти (не выдумываем, берём
из подтверждённого источника, разрешение на переразмещение отдельно от
точности источника).

Источник - тот же api.quran.com, что уже используем для таджвида
(scripts/export_mushaf_page.py: fetch_tajweed_ayah), пословный запрос по
странице (не по аяту) - 604 вызова на весь Коран, не 6236.

Идемпотентно: перезаписывает существующее поле "meaning" на каждом аяте,
безопасно перезапускать.

Запускать вручную:
    python scripts/add_ayah_meaning.py
"""
import glob
import json
import os
import sys
import time

import requests

sys.path.insert(0, ".")

TRANSLATION_RESOURCE_ID = 45  # Elmir Kuliev
OUT_DIR = "mushaf_data"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fetch_page_meanings(page_number, retries=3):
    """{verse_key: text} для всей страницы, один запрос."""
    for attempt in range(retries):
        try:
            r = requests.get(
                f"https://api.quran.com/api/v4/verses/by_page/{page_number}",
                params={"translations": TRANSLATION_RESOURCE_ID},
                timeout=20,
            )
            r.raise_for_status()
            verses = r.json()["verses"]
            out = {}
            for v in verses:
                translations = v.get("translations") or []
                if translations:
                    out[v["verse_key"]] = translations[0]["text"]
            return out
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise


def patch_page_file(path, meanings):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    missing = []
    for ayah in data["ayahs"]:
        key = f"{ayah['surah']}:{ayah['ayah']}"
        text = meanings.get(key)
        if text:
            ayah["meaning"] = text
        else:
            missing.append(key)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    return len(data["ayahs"]), missing


def main():
    paths = sorted(
        glob.glob(os.path.join(OUT_DIR, "page*.json")),
        key=lambda p: int(os.path.basename(p)[4:-5]),
    )
    for path in paths:
        page_number = int(os.path.basename(path)[4:-5])
        try:
            meanings = fetch_page_meanings(page_number)
            n_ayahs, missing = patch_page_file(path, meanings)
        except Exception as e:
            print(f"страница {page_number}: ОШИБКА - {e}")
            continue
        msg = f"страница {page_number}: {n_ayahs} аятов"
        if missing:
            msg += f", нет перевода для {missing}"
        print(msg)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
