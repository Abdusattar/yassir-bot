#!/usr/bin/env python3
"""
Сравнение 3 моделей на мотивационном сообщении.
Фиксированный вход: Бухари #4820 + Аят 20:114
"""
import sys, os, asyncio, aiohttp, time
sys.stdout.reconfigure(encoding='utf-8')

OR_API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
OR_URL     = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    ("google/gemini-2.5-flash-lite",         "Gemini 2.5 Flash-Lite"),
    ("deepseek/deepseek-chat-v3-0324",        "DeepSeek V3 0324"),
    ("qwen/qwen3-235b-a22b",                 "Qwen3-235B"),
]

# Фиксированный хадис: Бухари #4820
HADITH = {
    "id": 4820,
    "collection": "bukhari",
    "hadith_number": 4820,
    "arabic": "حَدَّثَنَا حَجَّاجُ بْنُ مِنْهَالٍ، حَدَّثَنَا شُعْبَةُ",
    "english_text": 'The Prophet said, "The best among you (Muslims) are those who learn the Qur\'an and teach it."',
    "label": "Бухари",
}

# Фиксированный аят: 20:114
AYAH = {
    "sura": "20",
    "aya": "114",
    "arabic": "",
    "meaning_en": "Say: My Lord, increase me in knowledge",
}

MISSING_NAMES = ["Акмал", "Зафар"]
GROUP_TITLE   = "Тест группа"

SYSTEM = (
    "Ты пишешь насыха (наставление) для студентов, заучивающих Коран, "
    "в стиле учёных и таалибуль-'ильм: искренне, мягко, опираясь ТОЛЬКО "
    "на смысл переданного аята и хадиса. "
    "Строго запрещено: придумывать образы и метафоры, которых нет в тексте; "
    "приписывать Аллаху или Пророку ﷺ ничего сверх приведённого; "
    "использовать выражения вроде «небо открыто», «день благословлён на аяты» "
    "и подобную отсебятину. "
    "Арабский и английский текст в сообщении не писать — только перевод смысла."
)

_HUMAN_STYLE = (
    "СТИЛЬ: пиши как настоящий человек в Telegram, не как ИИ. "
    "Только простой текст — без маркеров (- • *), без нумерованных списков, без заголовков, "
    "без **жирного** и _курсива_. "
    "Не более 1-2 эмодзи, только если уместно. "
    "Короткие естественные предложения, как учитель пишет с телефона."
)

def build_prompt():
    names_str = ", ".join(MISSING_NAMES)
    source_block = (
        "АЯТ (используй только смысл — арабский текст в сообщении не писать):\n"
        "Смысл: " + AYAH["meaning_en"] + "\n"
        "Ссылка в сообщении: (Сура " + AYAH["sura"] + ", аят " + AYAH["aya"] + ")\n\n"
        "ХАДИС (используй только смысл — арабский и английский текст не писать):\n"
        "Смысл: " + HADITH["english_text"] + "\n"
        "Ссылка в сообщении: (" + HADITH["label"] + ", №" + str(HADITH["hadith_number"]) + ")\n\n"
    )
    return (
        _HUMAN_STYLE + "\n\n"
        "Напиши утреннее мотивационное сообщение для группы «" + GROUP_TITLE + "».\n"
        "Студенты, не сдавшие сегодня: " + names_str + ".\n\n"
        + source_block
        + "Тон: тёплый, мягкий, вдохновляющий. Акцент на милости Аллаха к тем, кто занимается Его Книгой.\n\n"
        "ПРАВИЛА ОФОРМЛЕНИЯ:\n"
        "- После упоминания смысла аята сразу в скобках: (Сура N, аят M)\n"
        "- После упоминания смысла хадиса сразу в скобках: (Сборник, №N)\n"
        "- Арабский и английский текст не включать.\n"
        "- Только то, что есть в переданном смысле — никаких добавлений от себя.\n"
        "- Обратиться к студентам по именам и призвать сдать сегодня.\n"
        "Язык ответа: русский. Длина: 5-7 строк."
    )


async def call_model(session, model_id, model_name, prompt):
    headers = {
        "Authorization": "Bearer " + OR_API_KEY,
        "Content-Type": "application/json",
    }
    data = {
        "model": model_id,
        "max_tokens": 600,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": prompt},
        ],
    }
    t0 = time.time()
    try:
        async with session.post(OR_URL, headers=headers, json=data,
                                timeout=aiohttp.ClientTimeout(total=60)) as resp:
            result = await resp.json()
            elapsed = round(time.time() - t0, 1)
            if "error" in result:
                return model_name, None, elapsed, str(result["error"])
            text = result["choices"][0]["message"]["content"]
            return model_name, text, elapsed, None
    except Exception as e:
        return model_name, None, round(time.time() - t0, 1), str(e)


async def main():
    prompt = build_prompt()
    print("=" * 60)
    print("ПРОМПТ (системный):")
    print(SYSTEM)
    print("\nПРОМПТ (user):")
    print(prompt)
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        tasks = [call_model(session, mid, mname, prompt) for mid, mname in MODELS]
        results = await asyncio.gather(*tasks)

    for model_name, text, elapsed, error in results:
        print(f"\n{'=' * 60}")
        print(f"[{model_name}]  ({elapsed}s)")
        print('-' * 60)
        if error:
            print(f"ОШИБКА: {error}")
        else:
            print(text)

    print(f"\n{'=' * 60}")
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
