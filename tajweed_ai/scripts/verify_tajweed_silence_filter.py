# -*- coding: utf-8 -*-
"""
Тест фильтра "нарушения молчания" в таджвид-проверке (24.07.2026, пункт #2).

Проблема: когда в ответе есть реальная ошибка по ДРУГОЙ теме (нахв/муфрадат),
модель заодно пересказывает уже верные таджвид-пункты вместо молчания
(промпт прямо запрещает это: "ЗАПРЕЩЕНО упоминать верные слова/буквы").

Подход - НЕ семантическая классификация по зонам (слишком рискованно молча
спрятать настоящую ошибку устаза), а консервативное сравнение по словам:
если строка вердикта про букву X почти дословно повторяет то, что студент
сам написал про эту же букву, И в строке НЕТ слова-отрицания ("не",
"неверно" и т.п.) - считаем это пересказом верного, убираем. Если есть хоть
малейшее отличие в словах или есть отрицание - оставляем как есть (safe
default: лучше лишний шум, чем спрятанная ошибка).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Изолированная арабская буква (не часть более длинного слова), с
# опциональной цифрой (степень), которую некоторые студенты пишут (ق2, ك3).
LETTER_MENTION_RE = re.compile(
    r"(?<![؀-ۿ])([؀-ۿ])(?![؀-ۿ])\d*\s*[-–—:]?\s*([^\n]*)"
)

TAJWEED_VOCAB = [
    "горл", "язык", "губ", "нёб", "неб", "зуб", "нос", "гортан",
]

NEGATION_WORDS = ["не ", "неверно", "неточно", "неправильно", "не совсем", "не тот", "не та"]

STOPWORDS = {"и", "с", "в", "на", "к", "ко", "часть", "буква"}

# Слова степени/приближения - могут менять фонетический смысл (степень
# смыкания), поэтому НЕ считаются "шумом": если есть у студента, но
# бот их молча проглотил (не оспорив явно) - drop блокируется. Найдено
# на id=11 при ручной проверке 24.07.2026 (ي "ближе к нёбу" -> "+ нёбо" -
# бот мог как раз исправить реальную неточность про степень контакта).
DEGREE_WORDS = {"ближе", "почти", "слегка", "чуть"}


def has_tajweed_vocab(text):
    low = text.lower()
    return any(v in low for v in TAJWEED_VOCAB)


def has_negation(text):
    low = text.lower()
    return any(n in low for n in NEGATION_WORDS)


def words(text):
    text = text.lower().replace("+", " ")
    toks = re.findall(r"[а-яё]+", text)
    return {t for t in toks if t not in STOPWORDS and len(t) > 1}


def extract_letter_descriptions(text):
    """letter -> список описаний (может встречаться несколько раз)."""
    result = {}
    for line in text.split("\n"):
        for m in LETTER_MENTION_RE.finditer(line):
            letter, desc = m.group(1), m.group(2).strip(" ·.,;")
            if not desc or not has_tajweed_vocab(desc):
                continue
            result.setdefault(letter, []).append(desc)
    return result


def is_redundant(student_desc, bot_desc):
    if has_negation(bot_desc):
        return False
    sw, bw = words(student_desc), words(bot_desc)
    if not sw or not bw:
        return False
    # Слово степени, которое студент написал, а бот молча не упомянул -
    # блокируем drop (могло быть реальной, пусть и тихой, правкой).
    dropped_degree = (sw & DEGREE_WORDS) - bw
    if dropped_degree:
        return False
    # bot-описание должно быть подмножеством (или почти) того, что уже
    # сказал студент - иначе это может быть настоящая правка.
    overlap = len(sw & bw)
    return overlap >= 1 and bw.issubset(sw | {"нёбо", "небо"})


def filter_tajweed_silence(submitted_text, verdict):
    student_letters = extract_letter_descriptions(submitted_text)
    lines = verdict.split("\n")
    drop = [False] * len(lines)
    decisions = []
    for idx, line in enumerate(lines):
        for m in LETTER_MENTION_RE.finditer(line):
            letter, desc = m.group(1), m.group(2).strip(" ·.,;")
            if not desc or not has_tajweed_vocab(desc):
                continue
            if letter not in student_letters:
                continue
            for student_desc in student_letters[letter]:
                if is_redundant(student_desc, desc):
                    drop[idx] = True
                    decisions.append(("DROP", letter, student_desc, desc, line))
                    break
            else:
                decisions.append(("KEEP", letter, student_letters[letter], desc, line))
    new_verdict = "\n".join(l for i, l in enumerate(lines) if not drop[i]).strip()
    return new_verdict, decisions


def main():
    rows = json.loads((ROOT / "data" / "verify_log_all.json").read_text(encoding="utf-8"))
    taj = [r for r in rows if "tajweed" in r["checks"]]
    total_drops = 0
    for r in taj:
        new_verdict, decisions = filter_tajweed_silence(r["submitted_text"], r["verdict"])
        drops = [d for d in decisions if d[0] == "DROP"]
        if not decisions:
            continue
        print(f"=== id={r['id']} date={r['date']} flagged={r['flagged']} ===")
        for kind, letter, sdesc, bdesc, line in decisions:
            print(f"  [{kind}] буква={letter}")
            print(f"    студент: {sdesc if isinstance(sdesc, str) else sdesc}")
            print(f"    бот:     {bdesc}")
        if drops:
            print("  НОВЫЙ ВЕРДИКТ:")
            print("  " + (new_verdict.replace(chr(10), chr(10) + "  ") if new_verdict else "(пусто -> ВЕРНО)"))
        total_drops += len(drops)
        print()
    print(f"\nВсего убрано строк: {total_drops}")


if __name__ == "__main__":
    main()
