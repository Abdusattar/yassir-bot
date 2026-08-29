"""Генерация пословного кыргызского перевода Корана через Gemini (reasoning-модель
google/gemini-3.1-pro-preview via OpenRouter) - ОСОЗНАННОЕ ИСКЛЮЧЕНИЕ из правила
"никогда не выдумывать переводы Корана" (см. core/mufradat.py:SUPPORTED_LANGUAGES,
там же обоснование - готового пословного перевода на кыргызский нигде не нашлось,
проверены QuranWBW, api.quran.com, fawazahmed0/quran-api, QuranEnc, Quran Academy,
26.08.2026). Каждая сгенерированная страница ОБЯЗАНА быть сверена пользователем
(носитель кыргызского + знает пословный русский) перед тем, как доверять
следующей странице - решение пользователя 26.08.2026.

Источник арабского текста и разбивки на слова (включая "*"-склейку устойчивых
сочетаний, core/mufradat.py:_merge_glued_translations) - уже загруженные строки
language='ru' в mufradat_words (core/sampler.py) - НЕ гадаем сегментацию заново,
берём готовую проверенную у ru.

Промпт - вариант "без русской опоры" (только арабский + контекст аята), выбран
пользователем ПОСЛЕ прямого сравнения с вариантом "с русской опорой" на первой
странице (26.08.2026): русский текст как опора склонял модель калькировать
русский порядок слов вместо естественного кыргызского - пример لَا رَيْبَ
(категорическое отрицание "لا النافية للجنس"), где "эч бир" оказался точнее
"жок" именно по этой причине.

БЕЗ батчинга (несколько аятов в одном запросе на перевод) - проверено эмпирически
26.08.2026: reasoning-токены Pro растут с объёмом задачи внутри одного запроса,
и батч из 8 аятов (134 слова) оборвался на 10000 токенах (9596 - reasoning),
не пройдя и одного аята целиком - дороже и хуже, чем один аят на один запрос.
Один аят на запрос - реальный замер: 17-словный аят (сложный, с притчей) обошёлся
в $0.0776 (5943 reasoning-токена из 6385). MAX_TOKENS ниже взят с запасом от этого.

Стоимость - РЕАЛЬНАЯ, не оценочная: поле usage.cost в ответе OpenRouter,
суммируется и печатается по каждому аяту и в конце.

save_mufradat_word (core/sampler.py) сам создаёт progress_key для новых слов
(наследует представителя пары (arabic_text, перевод, язык), если такая пара уже
встречалась на этом языке, иначе становится сама себе представителем) - для
кыргызского это первый прогон, поэтому каждая уникальная пара станет новым
представителем, повторы внутри диапазона (если есть) схлопнутся сами.

Запускать вручную (нужен OPENROUTER_API_KEY в .env):
    python scripts/generate_kyrgyz_translation.py
"""
import json
import re
import sqlite3
import sys
import time

import requests

sys.path.insert(0, ".")
from config import OR_API_KEY, OR_URL
from core.sampler import HADITHS_DB, save_mufradat_word

# Диапазон задаётся списком (сура, аят_с, аят_по) - джуз 1 это сура 1
# целиком плюс сура 2 до аята 141 включительно (решение пользователя
# 30.08.2026 - "перевод доведём до конца первого джуза"). Аяты 2:1-2:69
# уже переведены 26.08.2026; save_mufradat_word идемпотентен (UPDATE на
# месте, progress_key не трогает), так что повторный прогон по ним
# безопасен, но по умолчанию их не гоняем - см. RANGES ниже.
RANGES = [
    (1, 1, 7),      # Аль-Фатиха
    (2, 70, 141),   # продолжение до конца джуза 1
]
SOURCE_LANGUAGE = "ru"
TARGET_LANGUAGE = "ky"
MODEL = "google/gemini-3.1-pro-preview"
MAX_TOKENS = 14000
MAX_RETRIES = 3

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def get_source_words(surah, ayah_number):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT position, arabic_text, translation FROM mufradat_words "
            "WHERE surah_number=? AND ayah_number=? AND language=? ORDER BY position",
            (surah, ayah_number, SOURCE_LANGUAGE)
        ).fetchall()
    return [dict(r) for r in rows]


def get_glossary(words):
    """Уже принятые кыргызские переводы для слов ЭТОГО аята (30.08.2026).

    Зачем: без такой опоры модель переводит одно и то же слово по-разному от
    аята к аяту - замер по готовым 2:1-2:69 показал 93 расхождения на 684
    арабских слова (13%), причём часть чисто косметические (регистр "бул"/
    "Бул"), а часть содержательные: رَبَّكُمُ в 2:21 стало "Раббиңерге", а
    رَّبِّهِمْ в 2:26 - "алардын Эгеси", то есть один и тот же термин то
    арабизмом, то кыргызским словом.

    Для тренажёра это не косметика: progress_key наследуется по паре
    (arabic_text, перевод, язык), поэтому каждый новый вариант перевода
    ПЛОДИТ ОТДЕЛЬНОЕ слово, и прогресс студента по нему размывается.

    Берём самый частый уже принятый вариант на каждое арабское слово -
    именно он и есть сложившаяся норма этого корпуса."""
    arabics = {w["arabic_text"] for w in words}
    if not arabics:
        return {}
    placeholders = ",".join("?" * len(arabics))
    with sqlite3.connect(HADITHS_DB) as conn:
        rows = conn.execute(
            f"SELECT arabic_text, translation, COUNT(*) AS n FROM mufradat_words "
            f"WHERE language=? AND arabic_text IN ({placeholders}) AND translation<>'*' "
            f"GROUP BY arabic_text, translation ORDER BY n DESC",
            (TARGET_LANGUAGE, *arabics)
        ).fetchall()
    best = {}
    for arabic, translation, _ in rows:
        best.setdefault(arabic, _normalize_case(translation))   # первый = самый частый
    return best


# Имена, которым заглавная буква положена и в середине фразы. Всё остальное
# в глоссарии приводится к строчной: глоссы показываются в тренажёре по
# одному и вперемешку, "начало аята" там не значит ничего, а разнобой
# "бул"/"Бул" плодил лишние progress_key (9 таких пар на 2:1-2:69).
_PROPER_PREFIXES = ("Аллах", "Рабби", "Куран", "Мухаммад", "Ибрахим", "Муса", "Иса", "Адам")


def _normalize_case(translation):
    text = translation.strip()
    if not text or text.startswith(_PROPER_PREFIXES):
        return text
    return text[0].lower() + text[1:]


def build_prompt(surah, ayah_number, words, glossary):
    full_arabic = " ".join(w["arabic_text"] for w in words)
    word_list = "\n".join(f"{w['position']}. {w['arabic_text']}" for w in words)
    star_positions = [w["position"] for w in words if w["translation"].strip() == "*"]
    star_note = (
        f'Positions {star_positions} are grammatically fused into the PRECEDING word '
        f'(a compound phrase) — output "*" for them.' if star_positions else ""
    )
    # Глоссарий уже принятых переводов - против расхождения одного и того же
    # слова от аята к аяту (см. get_glossary). Не жёсткий приказ: контекст
    # действительно может требовать другой падежной формы, кыргызский
    # агглютинативный - поэтому "unless the context genuinely requires".
    gloss_note = ""
    if glossary:
        pairs = "\n".join(f"- {a} → {t}" for a, t in glossary.items())
        gloss_note = (
            "\nALREADY-ESTABLISHED glossary (these exact Arabic words were glossed "
            "earlier in this same corpus). Reuse the established Kyrgyz wording unless "
            "the context genuinely requires a different case/form — consistency across "
            "ayat matters here:\n" + pairs + "\n"
        )
    return f'''You are a Quranic Arabic scholar producing a WORD-BY-WORD (interlinear) Kyrgyz gloss for Quran Surah {surah}, Ayah {ayah_number}.

Full ayah (Arabic): {full_arabic}

Words in order:
{word_list}

TASK: for each numbered position above, give the most accurate literal Kyrgyz word-by-word equivalent of that specific Arabic word, using the classical Quranic meaning (per standard tafsir), considering the whole ayah's meaning for grammatical/semantic context. Pay attention to natural KYRGYZ word order/morphology for quantifiers, negation, and demonstratives — do not force Arabic or Russian word order onto Kyrgyz. Do not drop or merge any word's meaning into another position — every position must carry its own full meaning.

{star_note}
{gloss_note}
RULES:
- Output EXACTLY one entry per position listed above, same count, same order.
- Kyrgyz text only (Cyrillic Kyrgyz letters and spaces only — no underscores, no hyphens joining words), no Russian, no explanations, no reasoning.
- Use lowercase, EXCEPT for proper nouns and the names of Allah (Аллах, Рабби, ...). Do not capitalise a word merely because it starts the ayah — these are isolated glosses shown out of order in a trainer.
- Output STRICT JSON ONLY: a list of objects {{"position": <int>, "translation": "<kyrgyz text>"}}. No markdown fences, no commentary, no reasoning text before or after.'''


def call_gemini(prompt):
    resp = requests.post(
        OR_URL,
        headers={"Authorization": "Bearer " + OR_API_KEY, "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=150,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    usage = data.get("usage", {}) or {}
    content = data["choices"][0]["message"]["content"].strip()
    return content, usage.get("cost", 0.0)


def parse_translations(content, expected_positions, star_positions):
    match = _JSON_ARRAY_RE.search(content)
    if not match:
        raise ValueError("no JSON array found in response")
    items = json.loads(match.group(0))
    by_position = {int(item["position"]): item["translation"] for item in items}
    if set(by_position) != set(expected_positions):
        raise ValueError(f"position mismatch: expected {expected_positions}, got {sorted(by_position)}")
    # "*"-позиции (склейка с предыдущим словом) принудительно нормализуем -
    # неважно, что там ответила модель, эти строки не несут собственного
    # перевода и поглощаются в get_words_in_range (core/mufradat.py), как и у ru.
    for pos in star_positions:
        by_position[pos] = "*"
    return by_position


def translate_ayah(surah, ayah_number, words):
    expected_positions = [w["position"] for w in words]
    star_positions = [w["position"] for w in words if w["translation"].strip() == "*"]
    # Глоссарий берётся ПЕРЕД каждым аятом заново - в него попадают и слова,
    # переведённые только что, в этом же прогоне (корпус растёт по ходу).
    glossary = get_glossary(words)
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            content, cost = call_gemini(build_prompt(surah, ayah_number, words, glossary))
            translations = parse_translations(content, expected_positions, star_positions)
            return translations, cost
        except Exception as e:
            last_error = e
            time.sleep(3)
    raise RuntimeError(f"не удалось после {MAX_RETRIES} попыток ({last_error})")


def main():
    if not OR_API_KEY:
        print("OPENROUTER_API_KEY не задан (проверь .env)")
        return

    total_cost = 0.0
    failed_ayat = []
    saved_words = 0

    for surah, start_ayah, end_ayah in RANGES:
        print(f"=== сура {surah}, аяты {start_ayah}-{end_ayah} ===")
        for ayah_number in range(start_ayah, end_ayah + 1):
            words = get_source_words(surah, ayah_number)
            if not words:
                print(f"  {surah}:{ayah_number}: нет исходных ({SOURCE_LANGUAGE}) слов, пропуск")
                continue

            try:
                translations, cost = translate_ayah(surah, ayah_number, words)
            except Exception as e:
                print(f"  {surah}:{ayah_number}: ОШИБКА - {e}")
                failed_ayat.append(f"{surah}:{ayah_number}")
                continue

            total_cost += cost
            for w in words:
                save_mufradat_word(
                    surah, ayah_number, w["position"], w["arabic_text"],
                    translations[w["position"]], TARGET_LANGUAGE
                )
                saved_words += 1

            print(f"  {surah}:{ayah_number}: готово (${cost:.4f}, всего ${total_cost:.4f})")
            time.sleep(1)

    print()
    print(f"Сохранено слов (язык {TARGET_LANGUAGE}): {saved_words}")
    print(f"Не удалось перевести аятов: {len(failed_ayat)} {failed_ayat}")
    print(f"Итоговая стоимость: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
