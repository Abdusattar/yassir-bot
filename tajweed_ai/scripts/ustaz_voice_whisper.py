# -*- coding: utf-8 -*-
"""Шаг 2 без Gemini (13.11.2026): голосовые Умар устаза -> текст локальным Whisper.

Голосовые - русская речь с цитатами из Корана. Gemini слушает их напрямую, но
ключ OpenRouter умер; проверяем, хватит ли бесплатного Whisper large-v3, чтобы
по его расшифровке разметку делал Claude в сессии. Эталон для сравнения -
расшифровки Gemini в data/ustaz_voice_classified.jsonl (одобрены пользователем).

    python scripts/ustaz_voice_whisper.py --ids 5038,4977      # конкретные
    python scripts/ustaz_voice_whisper.py --compare            # те, что есть у Gemini
    python scripts/ustaz_voice_whisper.py --limit 50           # следующие по порядку

Результат дописывается в data/ustaz_voice_whisper.jsonl (повторно не считает)."""
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "umar_corpus"
GEMINI = ROOT / "data" / "ustaz_voice_classified.jsonl"
OUT = ROOT / "data" / "ustaz_voice_whisper.jsonl"
PROMPT = ("Ассаламу алейкум. Аузу билляхи минаш-шайтанир-раджим. Здесь надо потянуть, "
          "мадд, гунна, идгам, ихфа, калькаля. Не так, а вот так, да.")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--no-vad", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)

    done = {json.loads(l)["id"] for l in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    want = None
    if a.ids:
        want = {int(x) for x in a.ids.split(",")}
    elif a.compare:
        want = {json.loads(l)["id"] for l in GEMINI.read_text(encoding="utf-8").splitlines()}
    todo = []
    for d in sorted(CORPUS_DIR.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        if not (d / "umar_review.ogg").exists():
            continue
        sid = json.loads((d / "meta.json").read_text(encoding="utf-8"))["submission_id"]
        if sid in done or (want is not None and sid not in want):
            continue
        todo.append((sid, d / "umar_review.ogg"))
    if a.limit:
        todo = todo[:a.limit]
    print(f"к расшифровке {len(todo)}, модель {a.model}", flush=True)

    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    for sid, path in todo:
        t = time.time()
        segs, info = model.transcribe(str(path), language=a.lang, initial_prompt=PROMPT,
                                      beam_size=5, vad_filter=not a.no_vad,
                                      condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segs)
        rec = {"id": sid, "transcript": text, "model": a.model, "lang": a.lang,
               "audio_s": round(info.duration, 1), "calc_s": round(time.time() - t, 1)}
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{sid}] {rec['audio_s']}с аудио за {rec['calc_s']}с: {text[:120]}", flush=True)


if __name__ == "__main__":
    main()
