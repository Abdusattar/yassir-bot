"""Тест тадаббур-поста 14:00. Запуск: python scripts/test_tadabbur_post.py"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

import core.ai as ai


async def main():
    print("--- Тадаббур-пост (14:00) ---\n")
    text = await ai.daily_tadabbur_post()
    if text:
        print(text)
    else:
        print("ERROR: модель не вернула ответ")


asyncio.run(main())
