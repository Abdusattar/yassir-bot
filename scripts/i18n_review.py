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

Второй заход (19.10.2026, решение пользователя - «группами достаточными без
падения качества»): набор строк - третьим аргументом.
    python scripts/i18n_review.py ky learn    - главы «Знаний» (i18n/learn_*)
    python scripts/i18n_review.py ky recheck  - 126 строк коммита 0c8d29e (16.10),
                                                их проверки не было
Пачка - не по числу строк, а по объёму русского текста (BUDGET знаков):
в «Знаниях» абзацы по 300-500 знаков, сто таких - уже неровная проверка.
Раздел «Знаний» в пачку идёт целиком (i18n/learn_sections.json) - модель
видит связный текст, а не обрывки. Словарь - весь живой словарь приложения
этого языка (i18n/<lang>_live_glossary.json) без проверяемых строк.
"""
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, ".")
from config import OR_API_KEY, OR_URL

MODEL = "google/gemini-3.1-pro-preview"
BATCH = 100
BUDGET = 3000          # знаков русского текста на пачку (наборы learn/recheck)
MAX_ITEMS = 60         # и не больше строк: короткие подписи тоже не валим сотней
MAX_TOKENS = 32000

LANGS = {
    "ky": {"name": "Kyrgyz", "draft": "i18n/ky_draft.json", "existing": "i18n/ky_existing.json",
           "missing": "i18n/ru_missing_ky.json", "out": "i18n/ky_review.json"},
    # Узбекский в приложении - КИРИЛЛИЦЕЙ (решение пользователя 30.08.2026),
    # хотя бот в группах пишет латиницей (core/i18n.py).
    "uz": {"name": "Uzbek", "draft": "i18n/uz_draft.json", "existing": "i18n/uz_existing.json",
           "missing": "i18n/ru_missing_uz.json", "out": "i18n/uz_review.json"},
}

SETS = {
    "learn": {"missing": "i18n/learn_ru.json", "draft": "i18n/learn_{lang}_draft.json",
              "existing": "i18n/{lang}_live_glossary.json", "sections": "i18n/learn_sections.json",
              "out": "i18n/learn_{lang}_review.json"},
    "recheck": {"missing": "i18n/recheck_ru_{lang}.json", "draft": "i18n/recheck_{lang}_draft.json",
                "existing": "i18n/{lang}_live_glossary.json", "sections": None,
                "out": "i18n/recheck_{lang}_review.json"},
}

# Для глав «Знаний»: это не кнопки, а абзацы объяснений; подписи кнопок
# в «ёлочках» должны дословно совпадать с тем, что человек видит на экране.
LEARN_RULES = """
EXTRA RULES for these items (they are paragraphs of the in-app guide, not buttons):
- Rule 5 about short buttons applies only to *_name, *_desc and *_t (titles); *_b are paragraphs - natural flowing prose.
- Any button/label/status quoted in «» must be written EXACTLY as the same label in the APPROVED GLOSSARY
  (it is what the student sees on screen). If the glossary has two variants, say so in "reason".
- The guide speaks as the bot in first person singular ("я") to the student ("сен"/"сен" in Uzbek); keep that.
- Numbers, rules and conditions (points, limits, days, hours) must stay exactly as in Russian.
"""

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


def batches(ru, sections):
    """Пачки по BUDGET знаков русского текста; раздел (если есть) не рвётся."""
    groups = [ks for ks in (sections or {}).values()]
    seen = {k for ks in groups for k in ks}
    groups += [[k] for k in ru if k not in seen]
    out, cur, size = [], [], 0
    for ks in groups:
        ks = [k for k in ks if k in ru]
        n = sum(len(ru[k]) for k in ks)
        if cur and (size + n > BUDGET or len(cur) + len(ks) > MAX_ITEMS):
            out.append(cur)
            cur, size = [], 0
        cur, size = cur + ks, size + n
    if cur:
        out.append(cur)
    return out


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "ky"
    kind = sys.argv[2] if len(sys.argv) > 2 else None
    cfg = LANGS[lang] if kind is None else {k: v and v.format(lang=lang) for k, v in SETS[kind].items()}
    ru = json.load(open(cfg["missing"], encoding="utf-8"))
    draft = json.load(open(cfg["draft"], encoding="utf-8"))
    existing = json.load(open(cfg["existing"], encoding="utf-8"))
    glossary = "\n".join(f"- {v['ru']} -> {v[lang]}" for v in existing.values())
    template = PROMPT + (LEARN_RULES if kind == "learn" else "")

    if kind is None:
        keys = list(ru)
        parts = [keys[n:n + BATCH] for n in range(0, len(keys), BATCH)]
    else:
        sections = json.load(open(cfg["sections"], encoding="utf-8")) if cfg.get("sections") else None
        parts = batches(ru, sections)
    # Продолжение после обрыва (19.10.2026: кончились деньги на OpenRouter
    # посреди прогона): ключи готовых пачек - в <out>.done, их не шлём снова.
    done_path = cfg["out"] + ".done"
    out, total, done = [], 0.0, set()
    if kind is not None and os.path.exists(done_path):
        done = set(json.load(open(done_path, encoding="utf-8")))
        out = json.load(open(cfg["out"], encoding="utf-8"))
    for i, part in enumerate(parts):
        if set(part) <= done:
            print(f"пачка {i + 1}/{len(parts)}: уже проверена", flush=True)
            continue
        items = [{"key": k, "ru": ru[k], lang: draft[k][lang],
                  **({"note": draft[k]["note"]} if draft[k].get("note") else {})} for k in part]
        prompt = template.format(lang=cfg_name(lang), glossary=glossary,
                                 items=json.dumps(items, ensure_ascii=False, indent=1))
        print(f"пачка {i + 1}/{len(parts)}: {len(part)} строк, "
              f"{sum(len(ru[k]) for k in part)} знаков…", flush=True)
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
        done |= set(part)
        json.dump(sorted(done), open(done_path, "w", encoding="utf-8"))

    by = {}
    for it in out:
        by[it["severity"]] = by.get(it["severity"], 0) + 1
    print(f"\nИтого: {len(out)} строк с ответом {by}, стоимость ${total:.4f} -> {cfg['out']}")


def cfg_name(lang):
    return {"ky": "Kyrgyz", "uz": "Uzbek (Cyrillic script)"}[lang]


if __name__ == "__main__":
    main()
