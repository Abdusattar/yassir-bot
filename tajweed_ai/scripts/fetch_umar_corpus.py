# -*- coding: utf-8 -*-
"""
Stage 0 (R&D таджвида, 23.07.2026): локально скачивает пары (запись
студента + голосовая/текстовая коррекция устаза) в data/umar_corpus/.

14.09.2026: выборка расширена - берём и реплаи других устазов (review_by
в meta.json различает, NULL = Умар до появления колонки), и сдачи хифза из
YassirApp с вердиктом accepted/retake + пометками слов (error_words,
координаты: line = 0-based текстовая строка листа, word = индекс токена в
строке, включая маркеры/знаки конца аята - см. applyErrorMarks в
mushaf_data/index.html).

Архитектура та же, что у check_voices.py: сервер хранит только file_id
(core/db.py: voice_submissions.review_file_id/review_text, см.
core/handlers.py - пишется ТОЛЬКО для CURRICULUM_REVIEWER_ID). Тяжёлая
часть (скачивание, разбор) - здесь, локально, вручную по запросу или
периодически.

НЕ авто-удаляет скачанное - см. вики/обсуждение 23.07: "поучились" не
машинный триггер. Даёт --purge-reviewed для сознательной чистки того, что
уже разобрано (см. data/umar_corpus_reviewed.json).
"""
import argparse
import json
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent

_env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        _env[k.strip()] = v.strip()

BOT_TOKEN = _env["BOT_TOKEN"]
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

CORPUS_DIR = ROOT / "data" / "umar_corpus"
FETCHED_PATH = ROOT / "data" / "umar_corpus_fetched.json"
REVIEWED_PATH = ROOT / "data" / "umar_corpus_reviewed.json"

SSH_CMD = [
    "ssh", "-i", str(Path.home() / ".ssh" / "claude_gcp"),
    "claude-access@34.51.213.67",
]

# У Умара реплаи могут быть в любой группе, где он админ - не ограничиваемся
# G2b (в отличие от check_voices.py, который специально пилотирует одну
# группу для теневой проверки).
DB_PATH = "/home/stursunkul/yassir-bot/quran_male.db"


def load_json_set(path):
    if path.exists():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()


def save_json_set(path, ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def fetch_umar_reviews():
    """Read-only SSH-запрос: все voice_submissions с непустым review_type
    (то есть Умар реплайнул) - вместе с file_id самой сдачи студента."""
    query = f"""
import sqlite3, json
c = sqlite3.connect('{DB_PATH}')
c.row_factory = sqlite3.Row
rows = c.execute('''
    SELECT vs.id, vs.student_id, vs.group_id, vs.file_id, vs.sent_at,
           vs.review_type, vs.review_file_id, vs.review_text, vs.review_by,
           vs.hifz_page, vs.hifz_line, vs.hifz_stage, vs.duration,
           vs.verdict, vs.verdict_at, vs.verdict_by, vs.error_words,
           u.name, ru.name AS review_by_name, vu.name AS verdict_by_name
    FROM voice_submissions vs JOIN users u ON u.id = vs.student_id
    LEFT JOIN users ru ON ru.phone = vs.review_by
    LEFT JOIN users vu ON vu.phone = vs.verdict_by
    WHERE vs.review_type IS NOT NULL OR vs.verdict IS NOT NULL
    ORDER BY vs.id
''').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False))
"""
    result = subprocess.run(
        SSH_CMD + [f"sudo -u stursunkul /home/stursunkul/yassir-bot/venv/bin/python3 -c \"{query}\""],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH query failed: {result.stderr.decode('utf-8', errors='replace')}")
    stdout_text = result.stdout.decode("utf-8", errors="replace")
    return json.loads(stdout_text.strip().splitlines()[-1])


def download_voice(file_id):
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{TG_API}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]
        audio_resp = client.get(f"{TG_FILE_API}/{file_path}")
        audio_resp.raise_for_status()
        return audio_resp.content


def fetch_all(only=None):
    """only: None - всё; "verdict" - только сдачи с вердиктом из хифза;
    "voice" - только голосовые коррекции. meta.json переписывается для ВСЕХ
    строк выборки при каждом запуске (вердикт/пометки могли появиться позже),
    аудио докачивается только если пары ещё нет."""
    fetched = load_json_set(FETCHED_PATH)
    rows = fetch_umar_reviews()
    if only == "verdict":
        rows = [r for r in rows if r["verdict"]]
    elif only == "voice":
        rows = [r for r in rows if r["review_type"] == "voice"]
    new_rows = [r for r in rows if r["id"] not in fetched]
    print(f"Строк в выборке: {len(rows)}, новых: {len(new_rows)}", flush=True)

    for r in rows:
        pair_dir = CORPUS_DIR / str(r["id"])
        pair_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "submission_id": r["id"],
            "student_id": r["student_id"],
            "student_name": r["name"],
            "group_id": r["group_id"],
            "sent_at": r["sent_at"],
            "duration": r["duration"],
            "review_type": r["review_type"],
            "review_by": r["review_by"],
            "review_by_name": r["review_by_name"],
            "hifz_page": r["hifz_page"],
            "hifz_line": r["hifz_line"],
            "hifz_stage": r["hifz_stage"],
            "verdict": r["verdict"],
            "verdict_at": r["verdict_at"],
            "verdict_by": r["verdict_by"],
            "verdict_by_name": r["verdict_by_name"],
            "error_words": json.loads(r["error_words"]) if r["error_words"] else None,
        }
        if r["review_type"] == "text" and r["review_text"]:
            meta["review_text"] = r["review_text"]
        (pair_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        if r["id"] in fetched:
            continue
        try:
            if r["file_id"] and not (pair_dir / "student.ogg").exists():
                (pair_dir / "student.ogg").write_bytes(download_voice(r["file_id"]))
            if r["review_type"] == "voice" and r["review_file_id"] \
                    and not (pair_dir / "umar_review.ogg").exists():
                (pair_dir / "umar_review.ogg").write_bytes(download_voice(r["review_file_id"]))
        except httpx.HTTPError as e:
            print(f"  [{r['id']}] ОШИБКА скачивания: {e}", flush=True)
            continue
        fetched.add(r["id"])
        save_json_set(FETCHED_PATH, fetched)
        print(f"  [{r['id']}] {r['name']} ({r['review_type']}/{r['verdict']}) -> {pair_dir}", flush=True)

    print(f"\nГотово. Всего скачано пар: {len(fetched)}")


def purge_reviewed():
    reviewed = load_json_set(REVIEWED_PATH)
    if not reviewed:
        print("Нет отмеченных как разобранные (data/umar_corpus_reviewed.json пуст) - удалять нечего.")
        return
    n = 0
    for sid in reviewed:
        pair_dir = CORPUS_DIR / str(sid)
        if pair_dir.exists():
            for f in pair_dir.iterdir():
                f.unlink()
            pair_dir.rmdir()
            n += 1
    print(f"Удалено {n} разобранных пар.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge-reviewed", action="store_true",
                     help="удалить пары, чей id вручную добавлен в data/umar_corpus_reviewed.json")
    ap.add_argument("--only", choices=["verdict", "voice"],
                     help="verdict - только сдачи хифза с вердиктом; voice - только голосовые коррекции")
    args = ap.parse_args()

    if args.purge_reviewed:
        purge_reviewed()
    else:
        fetch_all(args.only)
