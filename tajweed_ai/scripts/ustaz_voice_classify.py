# -*- coding: utf-8 -*-
"""
Шаг 2 (14.09.2026): что именно устазы поправляют голосом. Каждая голосовая
коррекция из data/umar_corpus/<id>/umar_review.ogg расшифровывается
аудио-моделью через OpenRouter (Gemini - единственный эндпоинт, который в
июле реально слушал аудио, см. wiki/ai_tajweed_audio.md) и раскладывается в
структурированный список: слово -> тип ошибки. Контекст модели: текст
единицы чтения (если сдача из хифза - страница/строка известны), иначе
только голос устаза.

Это НЕ судья по аудио студента (установлено: универсальная LLM им быть не
может) - это Scribe: понимание обычной речи устаза, в чём LLM хороша.
Первые ~30 расшифровок сверить на слух вручную, прежде чем верить сводке.

Выход: data/ustaz_voice_classified.jsonl + сводка по типам ошибок.
Ключ: OPENROUTER_API_KEY в tajweed_ai/.env.
"""
import argparse
import base64
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "umar_corpus"
OUT_PATH = ROOT / "data" / "ustaz_voice_classified.jsonl"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"

sys.path.insert(0, str(ROOT / "scripts"))

ERROR_TYPES = ["madd", "ghunna", "makhraj", "sifat", "qalqala", "harakat",
               "waqf_wasl", "hifz", "tempo", "other"]

PROMPT = """Ты помощник преподавателя Корана. В аудио — голосовое замечание устаза
студенту после того, как студент прочитал отрывок наизусть. Речь смешанная:
русский, кыргызский, арабские слова из Корана.

{context}

Сделай две вещи:
1. Дословная расшифровка речи устаза (русский/кыргызский как есть, арабские
   слова — арабскими буквами с огласовками, если различимо).
2. Список замечаний в JSON. Для каждого: слово Корана, о котором речь
   (арабскими буквами; если устаз не назвал слово — null), тип ошибки из
   списка, и короткая цитата устаза, на которой основан тип.
   Если устаз показывает «не так, а так» — в поле heard запиши кириллицей,
   КАК ПРОЗВУЧАЛ неверный вариант (например «фасамма»), а в quote — верный:
   арабская запись обеих версий одинакова, разница слышна только в звуке.
   Если устаз читает пропущенный кусок целиком — в word поставь его первое
   слово.

Типы ошибок:
- madd — длина растяжки (тянул/не тянул, длиннее/короче)
- ghunna — гунна/назализация (нун/мим, идгам, ихфа)
- makhraj — не та буква или не то место артикуляции (ع/غ/ح/ه, ص/س, ط/ت, ق/ك и т.п.)
- sifat — свойство буквы (тафхим/тарқиқ, толщина/тонкость, шидда)
- qalqala — калькаля
- harakat — не та огласовка (фатха/кясра/дамма, танвин, сукун, шадда)
- waqf_wasl — остановка/соединение, пауза не там, дыхание
- hifz — пропуск/добавление/замена слова, забыл, перепутал аят
- tempo — темп, «медленнее», «по буквам»
- other — всё остальное (организационное, похвала без замечаний и т.п.)

Верни СТРОГО JSON без пояснений:
{{"transcript": "...", "overall": "correction|praise_only|organizational|unclear",
  "items": [{{"word": "...", "type": "...", "quote": "...", "heard": "... или null"}}]}}"""


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def unit_context(meta):
    if meta.get("hifz_page") is None:
        return "Отрывок неизвестен (сдача из группы Telegram без привязки к странице)."
    from hifz_eval import unit_words
    import quran_transcript as qt
    words = unit_words(meta["hifz_page"], meta["hifz_line"] or 0, meta["hifz_stage"] or 1)
    cache, texts = {}, []
    for (_, _, s, a, p, _, _) in words:
        if (s, a) not in cache:
            cache[(s, a)] = qt.Aya(s, a).get().uthmani_words
        texts.append(cache[(s, a)][p - 1])
    stage = {1: "строчка", 2: "половина листа", 3: "вся страница"}.get(meta.get("hifz_stage") or 1)
    return (f"Студент читал: стр. {meta['hifz_page']} мусхафа, {stage}. Текст отрывка:\n"
            + " ".join(texts))


def audio_b64_wav(path):
    import librosa
    import soundfile as sf
    wave, _ = librosa.load(str(path), sr=16000, mono=True)
    buf = io.BytesIO()
    sf.write(buf, wave, 16000, format="WAV", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode("ascii"), len(wave) / 16000


def classify(client, api_key, model, meta, audio_path):
    b64, sec = audio_b64_wav(audio_path)
    body = {
        "model": model,
        "max_tokens": 6000,
        "temperature": 0,
        # Gemini 2.5 pro съедает лимит на скрытые размышления - 4977 обрезался
        "reasoning": {"effort": "low"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT.format(context=unit_context(meta))},
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
        ]}],
    }
    resp = client.post(OR_URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"transcript": text, "overall": "unclear", "items": [], "parse_error": True}
    return parsed, sec, data.get("usage")


def is_umar(meta_or_row):
    """Умар устаз: review_by = его имя, либо запись до появления колонки
    review_by (тогда save_umar_review писал ТОЛЬКО его реплаи).
    Решение 14.09.2026: других устазов в корпус не берём."""
    if meta_or_row.get("review_by_name") == "Умар":
        return True
    # у первых расшифровок (до 14.09) ключа review_by нет вовсе - не путать с NULL
    return "review_by" in meta_or_row and meta_or_row["review_by"] is None


def summarize(rows, all_ustaz=False):
    if not all_ustaz:
        rows = [r for r in rows if is_umar(r)]
    print(f"\nРасшифровано голосовых{'' if all_ustaz else ' (только Умар устаз)'}: {len(rows)}")
    print("overall:", dict(Counter(r["overall"] for r in rows)))
    types = Counter(it["type"] for r in rows for it in r["items"])
    total = sum(types.values())
    print(f"замечаний всего: {total}")
    for t, n in types.most_common():
        print(f"  {t:10s} {n:4d}  {n / max(1, total):5.0%}")
    by_ustaz = {}
    for r in rows:
        by_ustaz.setdefault(r["review_by_name"] or "Умар (до колонки)", Counter()).update(
            it["type"] for it in r["items"])
    for u, c in by_ustaz.items():
        print(f"  {u}: {dict(c.most_common(5))}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--model", default="google/gemini-2.5-pro")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids")
    ap.add_argument("--shard", help="i/n - только каждая n-я голосовая со сдвигом i (13.11.2026: "
                                     "599 штук в 4 процесса; строки дописываются в один файл)")
    ap.add_argument("--all-ustaz", action="store_true",
                     help="брать и других устазов (по умолчанию - только Умар устаз, решение 14.09)")
    args = ap.parse_args()

    done = [json.loads(l) for l in OUT_PATH.read_text(encoding="utf-8").splitlines()] if OUT_PATH.exists() else []
    if args.summary:
        summarize(done, args.all_ustaz)
        return
    api_key = load_env().get("OPENROUTER_API_KEY")
    if not api_key:
        sys.exit("Нет OPENROUTER_API_KEY в tajweed_ai/.env")

    done_ids = {r["id"] for r in done}
    todo = []
    for d in sorted(CORPUS_DIR.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        if not (d / "umar_review.ogg").exists():
            continue
        m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if m["submission_id"] in done_ids:
            continue
        if not args.all_ustaz and not is_umar(m):
            continue
        if args.ids and str(m["submission_id"]) not in args.ids.split(","):
            continue
        todo.append((d, m))
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        todo = todo[i::n]
    if args.limit:
        todo = todo[:args.limit]
    print(f"К расшифровке: {len(todo)} (готово {len(done)}), модель {args.model}", flush=True)

    with httpx.Client() as client:
        for d, m in todo:
            t0 = time.time()
            try:
                parsed, sec, usage = classify(client, api_key, args.model, m, d / "umar_review.ogg")
            except httpx.HTTPStatusError as e:
                print(f"  [{m['submission_id']}] HTTP {e.response.status_code}: {e.response.text[:200]}", flush=True)
                if e.response.status_code in (401, 402):
                    break
                continue
            row = {"id": m["submission_id"], "student": m["student_name"],
                   "review_by": m.get("review_by"), "review_by_name": m.get("review_by_name"), "page": m.get("hifz_page"),
                   "line": m.get("hifz_line"), "stage": m.get("hifz_stage"),
                   "verdict": m.get("verdict"), "audio_sec": round(sec, 1), "model": args.model,
                   "usage": usage, **parsed}
            with open(OUT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            done.append(row)
            print(f"  [{row['id']}] {row['student']} ({sec:.0f}с, {time.time() - t0:.0f}с): {row['overall']} "
                  f"{[(it.get('word'), it.get('type')) for it in row['items']]}", flush=True)
    summarize(done, args.all_ustaz)


if __name__ == "__main__":
    main()
