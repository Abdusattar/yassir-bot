# -*- coding: utf-8 -*-
"""Gemini проверяет пословный ru Claude (12.11.2026). Методика - wiki/wbw_ru_method.md.

Gemini - ПРОВЕРЯЮЩИЙ, не второй переводчик: видит те же опоры (sources/wbw_ru_refs/,
scripts/wbw_ru_refs.py) и подписи Claude, отвечает только списком проблем.
Один аят - один запрос (урок ky 26.08: батч обрывается на reasoning).
Цена - реальная, usage.cost OpenRouter. Готовые аяты повторно не гоняет.

Запуск - пользователь сам (ключ OpenRouter, дневной лимит):
    python scripts/wbw_ru_gemini.py [папка]      # по умолчанию logs/wbw_ru_sample
Итог - <папка>/gemini.json, затем scripts/wbw_ru_review.py соберёт review.md.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import OR_API_KEY, OR_URL  # noqa: E402

REFS = ROOT / "sources" / "wbw_ru_refs"
MODEL = "google/gemini-3.1-pro-preview"
MAX_TOKENS = 14000
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def build_prompt(key, ref, glosses):
    rows = "\n".join(
        f"{w['pos']}. {w['ar']} | QAC: {w['qac']} | EN wbw: {w['en_wbw']} | OUR RU: {g}"
        for w, g in zip(ref["words"], glosses))
    t, taf = ref["translations"], ref["tafsir"]
    return f'''You are a Quranic Arabic scholar REVIEWING a Russian word-by-word (interlinear) gloss of Quran {key}.
The gloss is shown under each Arabic word in a Quran app and is also used as the answer in a vocabulary trainer.

Goals of the gloss:
1. Each gloss gives the meaning of THIS Arabic word in THIS ayah (faithful to the word: root, form, tense, person).
2. Read in sequence, the glosses form a natural Russian phrase consistent with the ayah's meaning per standard tafsir (al-Muyassar is the arbiter).
3. No brackets, no "досл.", no explanations inside a gloss. Short.
4. "*" means the word is fused with the PREVIOUS word's gloss - do not flag "*" positions.
5. Where authoritative tafsir genuinely differ, a literal gloss that keeps both readings is preferred.
6. Attributes of Allah: literal, no interpretation of "how".

Words (position. Arabic | morphology | English word-by-word | OUR Russian gloss):
{rows}

References:
- Tafsir al-Muyassar (Arabic): {taf.get("muyassar_ar", "")}
- As-Sa'di (Russian): {taf.get("saadi_ru", "")[:1500]}
- Saheeh International: {t.get("saheeh", "")}
- Abdel Haleem: {t.get("abdel_haleem", "")}
- Kuliev (Russian): {t.get("kuliev", "")}
- Abu Adel (Russian): {t.get("abu_adel", "")}

TASK: list ONLY real problems: wrong meaning, wrong tense/person/number, meaning lost or moved to another position,
contradiction with al-Muyassar, unnatural Russian that misleads, inconsistent term. Do NOT list stylistic preferences.
If everything is correct, output [].
Output STRICT JSON ONLY: a list of objects
{{"pos": <int>, "problem": "<коротко по-русски>", "suggestion": "<русская подпись>", "source": "<на какую опору опираешься>"}}.
No markdown fences, no text before or after.'''


def call(prompt):
    resp = requests.post(
        OR_URL,
        headers={"Authorization": "Bearer " + OR_API_KEY, "Content-Type": "application/json"},
        json={"model": MODEL, "max_tokens": MAX_TOKENS, "temperature": 0.1,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=180)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data["choices"][0]["message"]["content"].strip(), (data.get("usage") or {}).get("cost", 0.0)


def main():
    if not OR_API_KEY:
        raise SystemExit("OPENROUTER_API_KEY не задан (проверь .env)")
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logs" / "wbw_ru_sample"
    new = json.loads((d / "wbw_ru_new.json").read_text(encoding="utf-8"))
    out_path = d / "gemini.json"
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    total = 0.0
    for key, glosses in new.items():
        if key in out:
            continue
        ref = json.loads((REFS / f"{key.replace(':', '_')}.json").read_text(encoding="utf-8"))
        last = None
        for attempt in range(3):
            try:
                content, cost = call(build_prompt(key, ref, glosses))
                m = _JSON_ARRAY_RE.search(content)
                items = json.loads(m.group(0)) if m else ([] if content.strip() in ("[]", "") else None)
                if items is None:
                    raise ValueError("нет JSON в ответе")
                break
            except Exception as e:  # noqa: BLE001 - сеть/формат: повторить
                last = e; items = None; cost = 0.0
                time.sleep(3)
        if items is None:
            print(f"{key}: не удалось ({last})")
            continue
        total += cost or 0.0
        out[key] = items
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{key}: замечаний {len(items)}, ${cost or 0:.4f}", flush=True)
    print(f"итого ${total:.4f}; дальше: python scripts/wbw_ru_review.py {d}")


if __name__ == "__main__":
    main()
