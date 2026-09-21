"""Найти записи, к которым прилипли прежние попытки (21.09.2026).

С 20.09 22:23 до выкладки фикса «Перезаписать» в приложении не стирал куски
на телефоне: прежние попытки уходили вместе с новой, и устаз слышал начало
несколько раз (живой случай пользователя - трижды).

Признак на самом голосовом: у склейки время каждой попытки начинается с нуля,
поэтому длина по ffprobe (последняя метка времени) короче, чем звука при
раскодировании. У честной записи они совпадают.

    python scripts/find_glued_recordings.py --profile male
    python scripts/find_glued_recordings.py --profile female --since 2026-09-20T22:00

Только читает: базу не меняет, никому ничего не пишет. Запускать на сервере
из корня репозитория от владельца базы (stursunkul): нужны ffmpeg/ffprobe и
токен бота из .env / .env.female.
"""
import argparse
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backfill_voice_duration import _download, _load_env, probe_seconds  # noqa: E402

GAP_SEC = 2.0   # разница больше - это уже не погрешность кодека, а лишний звук


def decoded_seconds(audio_bytes):
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        out = subprocess.run(["ffmpeg", "-v", "quiet", "-i", tmp, "-ac", "1", "-ar", "8000",
                              "-f", "s16le", "pipe:1"], capture_output=True, timeout=120).stdout
        return len(out) / 16000
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--since", default="2026-09-20T22:00", help="sent_at не раньше (время Бишкека)")
    args = ap.parse_args()

    os.environ["BOT_PROFILE"] = args.profile
    db_path = os.environ.get("DB_PATH") or str(ROOT / f"quran_{args.profile}.db")
    _load_env(args.profile)
    sys.path.insert(0, str(ROOT))
    from config import TELEGRAM_TOKEN  # noqa: E402

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = []
    for table, kind in (("voice_submissions", "сдача"), ("revision_recordings", "повторение")):
        rows += [(kind, r) for r in con.execute(
            f"SELECT t.id, t.file_id, t.sent_at, t.chat_id, t.message_id, "
            f"COALESCE(u.name, '?') AS name, COALESCE(g.title, '?') AS grp "
            f"FROM {table} t LEFT JOIN users u ON u.id = t.student_id "
            f"LEFT JOIN groups g ON g.id = t.group_id "
            f"WHERE t.file_id IS NOT NULL AND t.sent_at >= ? ORDER BY t.sent_at", (args.since,))]
    print(f"база: {db_path}  записей с {args.since}: {len(rows)}")

    found = 0
    for kind, r in rows:
        try:
            data = _download(TELEGRAM_TOKEN, r["file_id"])
        except Exception as e:
            print(f"  – {kind} [{r['id']}] {r['name']}: не скачать ({e})")
            continue
        probe, heard = probe_seconds(data), decoded_seconds(data)
        if probe is not None and heard - probe > GAP_SEC:
            found += 1
            print(f"  ! {kind} [{r['id']}] {r['sent_at'][:16]}  {r['name']} ({r['grp']})  "
                  f"слышно {heard:.0f} с, а длина {probe:.0f} с - лишних {heard - probe:.0f} с  "
                  f"chat {r['chat_id']} msg {r['message_id']}")
    print(f"склеенных: {found} из {len(rows)}")


if __name__ == "__main__":
    main()
