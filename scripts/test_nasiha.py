"""Тест ежедневной насыхи. Запуск: python scripts/test_nasiha.py"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import core.sampler as sampler
import core.ai as ai


async def main():
    hadith = sampler.sample_hadith()
    ayah   = sampler.sample_ayah()

    print("--- Источники ---")
    if ayah:
        print(f"Аят: {ayah['ref']}  теги: {ayah.get('topic_tags','')}")
    if hadith:
        print(f"Хадис: {hadith['label']} №{hadith['hadith_number']}")
        print(f"  EN: {hadith['english_text'][:120]}...")
    print()

    print("--- Насыха ---")
    text = await ai.daily_nasiha(hadith=hadith, ayah=ayah)
    if text:
        print(text)
    else:
        print("ERROR: модель не вернула ответ")


asyncio.run(main())
