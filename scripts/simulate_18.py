#!/usr/bin/env python3
"""
Симуляция 18:00 — personal_reminders().
Печатает в терминал вместо отправки в Telegram.

Опции:
  --dry-run   Отменяет used_at в БД после выборки (не расходует пул)
"""
import sys, asyncio, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

DRY_RUN = "--dry-run" in sys.argv

# ── Патчим send_message ДО любых импортов ─────────────────────────────────────
import core.tg as _tg

_sent = []

async def _fake_send(chat_id, text, **kwargs):
    _sent.append((chat_id, text))
    print(f"\n{'='*60}")
    print(f"  TO: {chat_id}")
    print(f"{'='*60}")
    print(text)

_tg.send_message = _fake_send

# ── Патчим sampler если --dry-run ─────────────────────────────────────────────
import core.sampler as _sampler

if DRY_RUN:
    _orig_sample_hadith = _sampler.sample_hadith
    _orig_sample_ayah   = _sampler.sample_ayah

    def _dry_sample_hadith():
        h = _orig_sample_hadith()
        if h:
            with sqlite3.connect(_sampler.HADITHS_DB) as conn:
                conn.execute("UPDATE hadiths SET used_at=NULL WHERE id=?", (h["id"],))
        return h

    def _dry_sample_ayah():
        a = _orig_sample_ayah()
        if a:
            with sqlite3.connect(_sampler.HADITHS_DB) as conn:
                conn.execute(
                    "UPDATE quran_ayahs SET used_at=NULL WHERE sura=? AND aya=?",
                    (a["sura"], a["aya"])
                )
        return a

    _sampler.sample_hadith = _dry_sample_hadith
    _sampler.sample_ayah   = _dry_sample_ayah
    print("[DRY-RUN] used_at не будет сохранён в БД")

# ── Теперь импортируем планировщик ────────────────────────────────────────────
from core.scheduler import personal_reminders
from core.db import get_all_groups

async def main():
    groups = get_all_groups()
    non_tad = [g for g in groups if (g["group_type"] or "relaxed") != "tadabbur"]
    print(f"Групп для рассылки: {len(non_tad)}")
    for g in non_tad:
        gtype = g["group_type"] or "relaxed"
        print(f"  [{gtype:8s}] {g['title'] or g['chat_id']}")

    print(f"\n{'='*60}")
    mode = "DRY-RUN" if DRY_RUN else "ПОЛНАЯ СИМУЛЯЦИЯ"
    print(f"personal_reminders() (18:00) — {mode}")
    print(f"{'='*60}")

    await personal_reminders()

    print(f"\n{'='*60}")
    print(f"Итого сообщений: {len(_sent)}")

asyncio.run(main())
