#!/usr/bin/env python3
"""
Шаг 2: Хайку классифицирует все аяты по темам.
Батчи по 30 аятов, 1 API вызов на батч.
Запуск: python scripts/batch_classify_quran.py
        python scripts/batch_classify_quran.py --resume  (пропускает уже помеченные)
"""
import sys, os, asyncio, json, sqlite3, argparse
from pathlib import Path
import aiohttp

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH    = Path(__file__).parent.parent / "sources" / "hadiths.db"
OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL      = "anthropic/claude-haiku-4-5"
BATCH_SIZE = 30

VALID_TAGS = {
    "knowledge", "quran", "patience", "striving",
    "reward", "remembrance", "mercy", "faith", "character", "other",
}

SYSTEM = """\
You are an Islamic scholar classifying Quran ayahs by motivational theme.
For each ayah assign ONE or MORE tags from this fixed list:
  knowledge  - about learning, teaching, seeking knowledge (علم، تعليم)
  quran      - virtues of Quran, recitation, memorization (تلاوة، حفظ، القرآن)
  patience   - sabr, perseverance, steadfastness (صبر، استقامة)
  striving   - effort, striving in the path of Allah (جهد، سعي، جهاد النفس)
  reward     - divine reward, good deeds rewarded, paradise (أجر، ثواب، جنة)
  remembrance - dhikr, du'a, repentance, gratitude, tawbah (ذكر، دعاء، توبة، شكر)
  mercy      - Allah's mercy, forgiveness, hope (رحمة، مغفرة، غفور)
  faith      - iman, tawakkul, trust in Allah (إيمان، توكل، يقين)
  character  - good manners, honesty, virtues (أخلاق، صدق، فضائل)
  other      - fiqh rulings, specific historical narratives, threats/punishments only

Rules:
- Assign 'other' when the ayah is about specific legal rulings (prayer times, inheritance, divorce), detailed war narratives, or severe punishment descriptions.
- An ayah can have multiple tags. Do NOT assign 'other' together with positive tags.
- Return ONLY a JSON object, no explanation: {"1": ["tag1", "tag2"], "2": ["tag"], ...}
  where the key is the batch index (1-based string).
"""


def load_batches(conn: sqlite3.Connection, resume: bool) -> list[list[tuple]]:
    if resume:
        rows = conn.execute(
            "SELECT sura, aya, arabic FROM quran_ayahs WHERE topic_tags IS NULL ORDER BY sura, aya"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sura, aya, arabic FROM quran_ayahs ORDER BY sura, aya"
        ).fetchall()
    batches = [rows[i:i+BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    return batches


def build_prompt(batch: list[tuple]) -> str:
    lines = []
    for i, (sura, aya, arabic) in enumerate(batch, 1):
        lines.append(f"{i}. [{sura}:{aya}] {arabic}")
    return "Classify these Quran ayahs:\n\n" + "\n".join(lines)


async def classify_batch(session: aiohttp.ClientSession, batch: list[tuple]) -> dict[int, list[str]]:
    headers = {"Authorization": "Bearer " + OR_API_KEY, "Content-Type": "application/json"}
    data = {
        "model": MODEL,
        "max_tokens": 400,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": build_prompt(batch)},
        ],
    }
    for attempt in range(3):
        try:
            async with session.post(OR_URL, headers=headers, json=data,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
                if "error" in result:
                    print(f"  API error: {result['error']}")
                    await asyncio.sleep(3)
                    continue
                text = result["choices"][0]["message"]["content"].strip()
                # Парсим JSON ответ
                start = text.find("{")
                end   = text.rfind("}") + 1
                parsed = json.loads(text[start:end])
                out = {}
                for k, tags in parsed.items():
                    idx = int(k)
                    clean = [t.lower().strip() for t in tags if t.lower().strip() in VALID_TAGS]
                    out[idx] = clean if clean else ["other"]
                return out
        except Exception as e:
            print(f"  Попытка {attempt+1} ошибка: {e}")
            await asyncio.sleep(3)
    return {}


async def main(resume: bool):
    conn = sqlite3.connect(DB_PATH)
    batches = load_batches(conn, resume)
    total_ayahs = sum(len(b) for b in batches)
    print(f"Аятов для классификации: {total_ayahs}  |  Батчей: {len(batches)}  |  Модель: {MODEL}\n")

    tagged = 0
    async with aiohttp.ClientSession() as session:
        for bi, batch in enumerate(batches):
            result = await classify_batch(session, batch)
            if not result:
                print(f"  Батч {bi+1}/{len(batches)} — нет результата, пропускаем")
                continue

            for i, (sura, aya, _arabic) in enumerate(batch, 1):
                tags = result.get(i, ["other"])
                tags_str = ",".join(tags)
                conn.execute(
                    "UPDATE quran_ayahs SET topic_tags=? WHERE sura=? AND aya=?",
                    (tags_str, sura, aya)
                )
                tagged += 1

            conn.commit()
            pct = round((bi + 1) / len(batches) * 100)
            print(f"  [{bi+1:4d}/{len(batches)}]  {pct:3d}%  ({tagged} аятов помечено)", end="\r")
            await asyncio.sleep(0.15)  # вежливая пауза

    print(f"\n\nГотово. Помечено: {tagged} аятов.")

    # Итоговая статистика по тегам
    print("\n=== Распределение тегов ===")
    rows = conn.execute("SELECT topic_tags, COUNT(*) as n FROM quran_ayahs GROUP BY topic_tags ORDER BY n DESC LIMIT 20").fetchall()
    from collections import Counter
    tag_counts: Counter = Counter()
    for tags_str, n in conn.execute("SELECT topic_tags, COUNT(*) FROM quran_ayahs WHERE topic_tags IS NOT NULL GROUP BY topic_tags"):
        for t in (tags_str or "other").split(","):
            tag_counts[t.strip()] += n
    for tag, n in tag_counts.most_common():
        bar = "█" * (n // 50)
        print(f"  {tag:12s}  {n:5d}  {bar}")

    not_other = conn.execute(
        "SELECT COUNT(*) FROM quran_ayahs WHERE topic_tags IS NOT NULL AND topic_tags != 'other'"
    ).fetchone()[0]
    print(f"\nМотивационных аятов (не 'other'): {not_other}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Пропустить уже классифицированные")
    args = parser.parse_args()
    asyncio.run(main(args.resume))
