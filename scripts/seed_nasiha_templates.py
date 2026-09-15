"""Засев банка насых шаблонами (15.09.2026).

Зачем: типовые тексты (напоминание молчащему, предупреждение о пропусках,
похвала победителю и за серию, комментарий к /mystats) бот сочинял на каждого
студента заново - около 85 вызовов ИИ в сутки на два бота. Теперь их выдаёт
core/nasiha_bank.pick() из шаблонов с подстановками; этот скрипт эти шаблоны
один раз генерирует (см. core/ai.py: TEMPLATE_KINDS, generate_template).

Запускать НА СЕРВЕРЕ под окружением бота - профиль (брат/сестра) берётся из
.env, банк общий (sources/hadiths.db), профиль пишется в строку:

    sudo -u stursunkul bash -c "set -a; . .env;        set +a; venv/bin/python3 scripts/seed_nasiha_templates.py"
    sudo -u stursunkul bash -c "set -a; . .env.female; set +a; venv/bin/python3 scripts/seed_nasiha_templates.py"

    --per N        сколько шаблонов на (тип, корзина) держать в банке (по умолчанию 12)
    --kinds a,b    только эти типы (по умолчанию все из TEMPLATE_KINDS)
    --lang ru      язык шаблонов

Идемпотентен: догенерирует только недостающее до --per. Каждый шаблон
опирается на свой случайный аят или хадис - тексты не похожи друг на друга.
"""
import argparse
import asyncio
import logging
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import core.ai as ai                    # noqa: E402
import core.nasiha_bank as bank         # noqa: E402
import core.sampler as sampler          # noqa: E402
from config import PROFILE              # noqa: E402

log = logging.getLogger("seed")


async def seed(kinds, per, lang):
    made = failed = 0
    for kind in kinds:
        for bucket in ai.TEMPLATE_KINDS[kind]["buckets"]:
            have = bank.count_templates(kind, lang, bucket)
            need = max(0, per - have)
            print(f"{kind:8} {str(bucket):10} есть {have:2}, нужно ещё {need}")
            attempts = 0
            while need > 0 and attempts < need * 3 + 3:
                attempts += 1
                if random.random() < 0.5:
                    hadith, ayah = sampler.sample_hadith(), None
                else:
                    hadith, ayah = None, sampler.sample_ayah()
                text = await ai.generate_template(kind, bucket, lang, hadith=hadith, ayah=ayah)
                if text and bank.count_templates(kind, lang, bucket) > have:
                    have += 1
                    need -= 1
                    made += 1
                    print("   +", text[:90].replace("\n", " "))
                else:
                    failed += 1
                    print("   - не годится (плейсхолдеры) или повтор")
                await asyncio.sleep(0.4)
    print(f"профиль {PROFILE}: добавлено {made}, отбраковано {failed}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--per", type=int, default=12)
    p.add_argument("--kinds", default=",".join(ai.TEMPLATE_KINDS))
    p.add_argument("--lang", default="ru")
    a = p.parse_args()
    kinds = [k.strip() for k in a.kinds.split(",") if k.strip()]
    unknown = [k for k in kinds if k not in ai.TEMPLATE_KINDS]
    if unknown:
        sys.exit("нет таких типов: " + ", ".join(unknown))
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(seed(kinds, a.per, a.lang))


if __name__ == "__main__":
    main()
