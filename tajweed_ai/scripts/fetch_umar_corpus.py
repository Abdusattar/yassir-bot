# -*- coding: utf-8 -*-
"""
Stage 0 (R&D таджвида, 23.07.2026): локально скачивает пары (запись
студента + голосовая/текстовая коррекция Умар устаза) в data/umar_corpus/.

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
           vs.review_type, vs.review_file_id, vs.review_text, u.name
    FROM voice_submissions vs JOIN users u ON u.id = vs.student_id
    WHERE vs.review_type IS NOT NULL
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


def fetch_all():
    fetched = load_json_set(FETCHED_PATH)
    rows = fetch_umar_reviews()
    new_rows = [r for r in rows if r["id"] not in fetched]
    print(f"Всего реплаев Умара в БД: {len(rows)}, новых: {len(new_rows)}")

    for r in new_rows:
        pair_dir = CORPUS_DIR / str(r["id"])
        pair_dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "submission_id": r["id"],
            "student_id": r["student_id"],
            "student_name": r["name"],
            "group_id": r["group_id"],
            "sent_at": r["sent_at"],
            "review_type": r["review_type"],
        }

        if r["file_id"]:
            audio = download_voice(r["file_id"])
            (pair_dir / "student.ogg").write_bytes(audio)

        if r["review_type"] == "voice" and r["review_file_id"]:
            audio = download_voice(r["review_file_id"])
            (pair_dir / "umar_review.ogg").write_bytes(audio)
        elif r["review_type"] == "text" and r["review_text"]:
            meta["review_text"] = r["review_text"]

        (pair_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        fetched.add(r["id"])
        print(f"  [{r['id']}] {r['name']} ({r['review_type']}) -> {pair_dir}")

    save_json_set(FETCHED_PATH, fetched)
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
    args = ap.parse_args()

    if args.purge_reviewed:
        purge_reviewed()
    else:
        fetch_all()
