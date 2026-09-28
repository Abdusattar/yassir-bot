"""Проверка черновика перевода интерфейса приложения через Gemini (28.09.2026).

Черновик кыргызского готовит Claude (i18n/ky_draft.json), Gemini смотрит его
вторым взглядом - решение пользователя: «главное качество». Пользователю на
просмотр идут только расхождения.

Как устроено (решения 28.09.2026):
- 4 пачки по ~100 строк, а не одним махом: длинный список модель проверяет
  неровно, и ответ на 393 строки мог бы обрезаться; в ответе - ТОЛЬКО
  замечания, так что по токенам почти как одним запросом.
- Промпт на английском (wiki/i18n.md: иначе модель путается с языком).
- Словарь - уже утверждённые 49 кыргызских строк приложения
  (i18n/ky_existing.json): «Машыгуу», «Кыстарма», «эсептелди», «сен».
- Строки с пометкой note (сомнения черновика) модель обязана разобрать явно.
- Стоимость - реальная, из usage.cost ответа OpenRouter.

Запуск (нужен OPENROUTER_API_KEY в .env):
    python scripts/i18n_review.py ky
Результат - i18n/ky_review.json: [{key, ru, draft, suggestion, severity, reason}].
"""
import json
import re
import sys
import time

import requests

sys.path.insert(0, ".")
from config import OR_API_KEY, OR_URL

MODEL = "google/gemini-3.1-pro-preview"
BATCH = 100
MAX_TOKENS = 32000

LANGS = {
    "ky": {"name": "Kyrgyz", "draft": "i18n/ky_draft.json", "existing": "i18n/ky_existing.json",
           "missing": "i18n/ru_missing_ky.json", "out": "i18n/ky_review.json"},
    # Узбекский в приложении - КИРИЛЛИЦЕЙ (решение пользователя 30.08.2026),
    # хотя бот в группах пишет латиницей (core/i18n.py).
    "uz": {"name": "Uzbek", "draft": "i18n/uz_draft.json", "existing": "i18n/uz_existing.json",
           "missing": "i18n/ru_missing_uz.json", "out": "i18n/uz_review.json"},
}

PROMPT = """You are a native {lang} editor reviewing the user-interface texts of a Quran-learning
mobile app used by Muslim students in Kyrgyzstan (memorization of the Quran, revision,
Quranic vocabulary, tajweed, Arabic grammar (nahw), hadith; teachers are called "устаз").

Below is a DRAFT {lang} translation of Russian UI strings. Review every item.

Rules the translation must follow:
1. Meaning must match the Russian exactly; natural, idiomatic {lang}, not a calque of Russian word order.
2. Address the student informally ("сен"), as in the approved glossary.
3. Keep placeholders like %N%, %M%, %A%, %P% exactly (same set), keep emoji, arrows and HTML tags as is.
4. Keep terms consistent with the APPROVED GLOSSARY below (these strings are already live in the app).
   Islamic/subject terms stay as they are used by Kyrgyz Muslims: устаз, аят, сүрө, мусхаф, хадис,
   тажвид, нахв, муфрадат, Бакара.
5. UI strings must stay short: buttons are 1-3 words.
   For Uzbek: CYRILLIC script only (ў, қ, ғ, ҳ), never Latin - the app shows Uzbek in Cyrillic.
6. Kyrgyz has no grammatical gender: male/female variants may be identical.
7. Items with a "note" field carry the drafter's doubt - you MUST return every such item with a verdict
   (severity "ok" if the draft is right, and say why in "reason").

Return ONLY items that need a change, plus all items that have a "note".
Answer strictly as JSON: {{"items": [{{"key": "...", "suggestion": "full corrected {lang} string",
"severity": "error" | "style" | "ok", "reason": "short explanation IN RUSSIAN"}}]}}
"error" = wrong meaning, grammar or spelling; "style" = correct but clearly more natural wording exists.
Do not return items that are fine and have no note.

APPROVED GLOSSARY (Russian -> {lang}):
{glossary}

ITEMS TO REVIEW:
{items}
"""


def ask(prompt):
    for attempt in range(3):
        r = requests.post(OR_URL, headers={"Authorization": f"Bearer {OR_API_KEY}"}, json={
            "model": MODEL, "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
            "usage": {"include": True},
        }, timeout=600)
        if r.status_code == 200:
            data = r.json()
            text = data["choices"][0]["message"]["content"] or ""
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                return json.loads(m.group(0)), (data.get("usage") or {}).get("cost") or 0.0
            print("  ответ без JSON, повтор", attempt + 1)
        else:
            print("  HTTP", r.status_code, r.text[:200], "- повтор", attempt + 1)
        time.sleep(5)
    raise SystemExit("Gemini не ответил трижды - остановлено, прошлые пачки в файле")


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "ky"
    cfg = LANGS[lang]
    ru = json.load(open(cfg["missing"], encoding="utf-8"))
    draft = json.load(open(cfg["draft"], encoding="utf-8"))
    existing = json.load(open(cfg["existing"], encoding="utf-8"))
    glossary = "\n".join(f"- {v['ru']} -> {v[lang]}" for v in existing.values())

    keys = list(ru)
    out, total = [], 0.0
    for n in range(0, len(keys), BATCH):
        part = keys[n:n + BATCH]
        items = [{"key": k, "ru": ru[k], lang: draft[k][lang],
                  **({"note": draft[k]["note"]} if draft[k].get("note") else {})} for k in part]
        prompt = PROMPT.format(lang=cfg_name(lang), glossary=glossary,
                               items=json.dumps(items, ensure_ascii=False, indent=1))
        print(f"пачка {n // BATCH + 1}: строки {n + 1}-{n + len(part)}…", flush=True)
        answer, cost = ask(prompt)
        total += cost
        got = 0
        for it in answer.get("items", []):
            k = it.get("key")
            if k not in part:
                continue
            sug = it.get("suggestion") or draft[k][lang]
            bad = sorted(re.findall(r"%[A-Z]%", ru[k])) != sorted(re.findall(r"%[A-Z]%", sug))
            out.append({"key": k, "ru": ru[k], "draft": draft[k][lang], "suggestion": sug,
                        "severity": it.get("severity", "style"), "reason": it.get("reason", ""),
                        "note": draft[k].get("note", ""),
                        **({"placeholders_broken": True} if bad else {})})
            got += 1
        print(f"  замечаний: {got}, стоимость ${cost:.4f}", flush=True)
        json.dump(out, open(cfg["out"], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by = {}
    for it in out:
        by[it["severity"]] = by.get(it["severity"], 0) + 1
    print(f"\nИтого: {len(out)} строк с ответом {by}, стоимость ${total:.4f} -> {cfg['out']}")


def cfg_name(lang):
    return {"ky": "Kyrgyz", "uz": "Uzbek (Cyrillic script)"}[lang]


if __name__ == "__main__":
    main()
