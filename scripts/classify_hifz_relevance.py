#!/usr/bin/env python3
"""
Переклассификация хадисов и аятов на уместность для мотивации студентов хифза.
Добавляет колонку hifz_relevant (1=уместен, 0=нет) в hadiths и quran_ayahs.

После запуска sampler.py автоматически исключает неуместные записи.

Запуск:
  python scripts/classify_hifz_relevance.py           # всё сразу
  python scripts/classify_hifz_relevance.py --hadiths  # только хадисы
  python scripts/classify_hifz_relevance.py --ayahs    # только аяты
  python scripts/classify_hifz_relevance.py --resume   # пропустить уже размеченные
"""
import sys, asyncio, json, sqlite3, argparse, os
from pathlib import Path
import aiohttp

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH    = Path(__file__).parent.parent / "sources" / "hadiths.db"
OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL      = "anthropic/claude-haiku-4-5"
HADITH_BATCH = 20
AYAH_BATCH   = 30

HADITH_SQL = """
    SELECT h.id, h.english_text
    FROM hadiths h
    JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
    WHERE LENGTH(h.english_text) > 90
      AND LENGTH(h.english_text) < 700
      AND h.english_text NOT LIKE 'This hadith has been%'
      AND h.english_text NOT LIKE '%same chain of transmitters%'
      AND h.english_text NOT LIKE '%same as above%'
"""

HADITH_SYSTEM = """\
You are an Islamic scholar reviewing hadith texts.
For each hadith, decide: is it APPROPRIATE as a daily motivational reminder
for students who are memorizing the Quran (hifz)?

Answer YES if the hadith is about:
- Virtues of Quran recitation, memorization, or carrying the Quran
- Seeking knowledge, teaching, status of scholars
- Patience, consistency, steadfastness in worship
- Allah's mercy, forgiveness, reward for good deeds
- General Islamic character that motivates a Quran student

Answer NO if the hadith is about:
- Specific fiqh rulings (marriage, divorce, inheritance, trade, ablution)
- Military expeditions, specific battles, political events
- Virtues of specific tribes, ethnic groups, or geographic regions
- Severe punishments without motivational context

Return ONLY JSON: {"1": true, "2": false, ...}  (true = YES, false = NO)
"""

AYAH_SYSTEM = """\
You are an Islamic scholar reviewing Quran verses.
For each ayah, decide: is it APPROPRIATE and MEANINGFUL as a daily motivational
reminder for students memorizing the Quran (hifz)?

Answer YES if the ayah:
- Directly encourages reciting, learning, or reflecting on the Quran
- Inspires patience, consistency, or striving in good deeds
- Speaks of Allah's mercy and reward for those who do good
- Motivates a student generally toward worship and knowledge

Answer NO if the ayah:
- Is addressed to disbelievers demanding punishment or a sign
- Describes divine punishment being hastened
- Is a detailed legal ruling (inheritance, divorce, war spoils)
- Is a specific historical narrative with no motivational takeaway
- Would be confusing or misleading taken out of its original context

Return ONLY JSON: {"1": true, "2": false, ...}  (true = YES, false = NO)
"""


def migrate(conn: sqlite3.Connection):
    """Добавляет hifz_relevant если ещё нет."""
    cols_h = {r[1] for r in conn.execute("PRAGMA table_info(hadiths)")}
    cols_a = {r[1] for r in conn.execute("PRAGMA table_info(quran_ayahs)")}
    if "hifz_relevant" not in cols_h:
        conn.execute("ALTER TABLE hadiths ADD COLUMN hifz_relevant INTEGER")
        print("  + hadiths.hifz_relevant добавлена")
    if "hifz_relevant" not in cols_a:
        conn.execute("ALTER TABLE quran_ayahs ADD COLUMN hifz_relevant INTEGER")
        print("  + quran_ayahs.hifz_relevant добавлена")
    conn.commit()


async def ask_haiku(session: aiohttp.ClientSession, system: str, user: str) -> dict[int, bool]:
    headers = {"Authorization": "Bearer " + OR_API_KEY, "Content-Type": "application/json"}
    data = {
        "model": MODEL,
        "max_tokens": 600,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    }
    for attempt in range(3):
        try:
            async with session.post(OR_URL, headers=headers, json=data,
                                    timeout=aiohttp.ClientTimeout(total=40)) as resp:
                result = await resp.json()
                if "error" in result:
                    print(f"  API error: {result['error']}")
                    await asyncio.sleep(3)
                    continue
                text = result["choices"][0]["message"]["content"].strip()
                start = text.find("{")
                end   = text.rfind("}") + 1
                parsed = json.loads(text[start:end])
                return {int(k): bool(v) for k, v in parsed.items()}
        except Exception as e:
            print(f"  Попытка {attempt+1} ошибка: {e}")
            await asyncio.sleep(3)
    return {}


async def classify_hadiths(conn: sqlite3.Connection, resume: bool):
    sql = HADITH_SQL
    if resume:
        sql += " AND h.hifz_relevant IS NULL"
    rows = conn.execute(sql).fetchall()
    total = len(rows)
    print(f"\n[ХАДИСЫ] К классификации: {total}")
    if not total:
        print("  Нечего делать.")
        return

    done = yes_count = no_count = 0
    async with aiohttp.ClientSession() as session:
        for i in range(0, total, HADITH_BATCH):
            batch = rows[i:i + HADITH_BATCH]
            user = "Classify these hadiths:\n\n"
            for j, (hid, text) in enumerate(batch, 1):
                safe = (text or "")[:400].replace("\n", " ")
                user += f"{j}. {safe}\n"

            result = await ask_haiku(session, HADITH_SYSTEM, user)
            for j, (hid, _) in enumerate(batch, 1):
                relevant = result.get(j)
                if relevant is None:
                    continue
                conn.execute(
                    "UPDATE hadiths SET hifz_relevant=? WHERE id=?",
                    (1 if relevant else 0, hid)
                )
                if relevant:
                    yes_count += 1
                else:
                    no_count += 1
                done += 1

            conn.commit()
            pct = round((i + HADITH_BATCH) / total * 100)
            print(f"  [{min(i+HADITH_BATCH, total):5d}/{total}]  {pct:3d}%"
                  f"  ✅ {yes_count}  ❌ {no_count}", end="\r")
            await asyncio.sleep(0.3)

    print(f"\n  Готово. Уместных: {yes_count}, неуместных: {no_count}")


async def classify_ayahs(conn: sqlite3.Connection, resume: bool):
    sql = """
        SELECT sura, aya, arabic, topic_tags
        FROM quran_ayahs
        WHERE topic_tags IS NOT NULL AND topic_tags != 'other'
    """
    if resume:
        sql += " AND hifz_relevant IS NULL"
    sql += " ORDER BY sura, aya"
    rows = conn.execute(sql).fetchall()
    total = len(rows)
    print(f"\n[АЯТЫ] К классификации: {total}")
    if not total:
        print("  Нечего делать.")
        return

    done = yes_count = no_count = 0
    async with aiohttp.ClientSession() as session:
        for i in range(0, total, AYAH_BATCH):
            batch = rows[i:i + AYAH_BATCH]
            user = "Classify these Quran ayahs:\n\n"
            for j, (sura, aya, arabic, tags) in enumerate(batch, 1):
                user += f"{j}. [{sura}:{aya}] (tags: {tags}) {arabic[:200]}\n"

            result = await ask_haiku(session, AYAH_SYSTEM, user)
            for j, (sura, aya, _, _) in enumerate(batch, 1):
                relevant = result.get(j)
                if relevant is None:
                    continue
                conn.execute(
                    "UPDATE quran_ayahs SET hifz_relevant=? WHERE sura=? AND aya=?",
                    (1 if relevant else 0, sura, aya)
                )
                if relevant:
                    yes_count += 1
                else:
                    no_count += 1
                done += 1

            conn.commit()
            pct = round((i + AYAH_BATCH) / total * 100)
            print(f"  [{min(i+AYAH_BATCH, total):5d}/{total}]  {pct:3d}%"
                  f"  ✅ {yes_count}  ❌ {no_count}", end="\r")
            await asyncio.sleep(0.2)

    print(f"\n  Готово. Уместных: {yes_count}, неуместных: {no_count}")


def print_stats(conn: sqlite3.Connection):
    print("\n=== Итог ===")
    for table, pk in [("hadiths", "id"), ("quran_ayahs", "sura")]:
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        yes   = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant = 1"
        ).fetchone()[0]
        no    = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant = 0"
        ).fetchone()[0]
        null  = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant IS NULL"
        ).fetchone()[0]
        print(f"  {table:15s}  всего={total}  ✅={yes}  ❌={no}  ?={null}")


async def main(do_hadiths: bool, do_ayahs: bool, resume: bool):
    conn = sqlite3.connect(DB_PATH)
    print("Миграция схемы...")
    migrate(conn)

    if do_hadiths:
        await classify_hadiths(conn, resume)
    if do_ayahs:
        await classify_ayahs(conn, resume)

    print_stats(conn)
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--hadiths", action="store_true", help="Только хадисы")
    parser.add_argument("--ayahs",   action="store_true", help="Только аяты")
    parser.add_argument("--resume",  action="store_true", help="Пропустить уже размеченные")
    args = parser.parse_args()

    do_hadiths = args.hadiths or (not args.hadiths and not args.ayahs)
    do_ayahs   = args.ayahs   or (not args.hadiths and not args.ayahs)

    asyncio.run(main(do_hadiths, do_ayahs, args.resume))
