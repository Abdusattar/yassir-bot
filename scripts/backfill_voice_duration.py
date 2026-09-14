"""Добить длину записи у сдач, сохранённых до колонки duration (14.09.2026).

Зачем: кабинет устаза показывает длину записи у каждой сдачи, но у строк,
записанных до 14.09, её нет - Telegram сообщил её один раз, при отправке,
и тогда её никто не сохранял. По file_id файл можно скачать и измерить
ffprobe. По умолчанию берутся только сдачи, которые ЕЩЁ ЖДУТ проверки: у
давно разобранных длина ни к чему, а файлов там сотни.

    python scripts/backfill_voice_duration.py --profile female --dry-run
    python scripts/backfill_voice_duration.py --profile male
    python scripts/backfill_voice_duration.py --profile male --all   # и проверенные

Идемпотентен: строки с уже известной длиной не трогает. Файл, который
Telegram больше не отдаёт (старше нескольких месяцев, удалён), пропускается
с пометкой - длина у него так и остаётся пустой.

Запускать на сервере из корня репозитория от владельца базы (stursunkul):
нужны ffprobe и токен бота из .env / .env.female.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_env(profile):
    path = ROOT / (".env" if profile == "male" else ".env.female")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip("\"'")


def _tg(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (token, method), data=data)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _download(token, file_id):
    info = _tg(token, "getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        raise RuntimeError(info.get("description", "getFile: нет file_path"))
    url = "https://api.telegram.org/file/bot%s/%s" % (token, path)
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def probe_seconds(audio_bytes):
    """Длина через ffprobe. Возвращает float секунд или None."""
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp],
            capture_output=True, text=True, timeout=60,
        )
        val = (out.stdout or "").strip()
        return float(val) if val else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--all", action="store_true", help="и уже проверенные сдачи, не только ждущие")
    ap.add_argument("--dry-run", action="store_true", help="только перечислить кандидатов")
    args = ap.parse_args()

    os.environ["BOT_PROFILE"] = args.profile
    os.environ.setdefault("DB_PATH", str(ROOT / f"quran_{args.profile}.db"))
    _load_env(args.profile)
    sys.path.insert(0, str(ROOT))
    from config import TELEGRAM_TOKEN  # noqa: E402
    from core.db import get_submissions_without_duration, set_submission_duration  # noqa: E402

    rows = get_submissions_without_duration(pending_only=not args.all)
    print(f"база: {os.environ['DB_PATH']}  без длины: {len(rows)}"
          f" ({'все' if args.all else 'только ждущие проверки'})")
    if not rows:
        return 0
    if args.dry_run:
        for r in rows:
            print(f"  [{r['id']}] chat {r['chat_id']} msg {r['message_id']}")
        print("dry-run: ничего не измерено")
        return 0
    if not TELEGRAM_TOKEN:
        print("нет токена бота — проверь .env профиля")
        return 1

    done = skipped = 0
    for r in rows:
        try:
            sec = probe_seconds(_download(TELEGRAM_TOKEN, r["file_id"]))
        except Exception as e:  # файл уже не отдаётся, сеть и т.п.
            print(f"  – [{r['id']}] пропуск: {e}")
            skipped += 1
            continue
        if sec is None:
            print(f"  – [{r['id']}] ffprobe не смог измерить")
            skipped += 1
            continue
        set_submission_duration(r["id"], sec)
        print(f"  ✓ [{r['id']}] {int(round(sec))} сек")
        done += 1
    print(f"записано {done}, пропущено {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
