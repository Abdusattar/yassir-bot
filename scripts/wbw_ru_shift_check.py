# -*- coding: utf-8 -*-
"""Поиск сдвигов отрицания в пословном ru (14.11.2026, wiki/wbw_ru_method.md правило 8).

Сверяет подписи i18n/wbw_ru/<файл>.json с английским пословным из sources/wbw_ru_refs:
  A - в английском есть not/no/never, в русской подписи отрицания нет (могло уехать к соседу);
  B - в русской подписи «не/нет/ни/без», в английском отрицания нет (могло приехать от соседа).
  C - у слова есть корень (глагол/имя по Quranic Arabic Corpus), а в подписи только служебные
      слова («вы», «они», «было») - смысл слова уехал к соседу (так было у 2:239 تَعْلَمُونَ = «вы»);
  D - слово служебное (без корня, в английском только служебные), а в подписи есть полнозначное
      слово - смысл приехал от соседа (4:48 بِهِۦ = «сотоварищей»).
Это подсказка для глаз, не приговор: «ни» в «где бы ни», неверие (كفر) и т.п. - норма.

    python scripts/wbw_ru_shift_check.py i18n/wbw_ru/juz6.json
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEG_EN = re.compile(r"\b(not|no|never|nor|none|neither)\b", re.I)
NEG_RU = re.compile(r"(^|[^а-яё])(не|нет|ни|никогда|без|отнюдь|нельзя)([^а-яё]|$)", re.I)
SKIP_B = re.compile(r"disbeliev|reject|den(y|ied)|without|except|other than|unless|lest|nothing"
                    r"|until|any|nay|yes|ever|ignor|unjust|wrong|whatever|wherever|whoever", re.I)


RU_FUNC = set("""я ты он она оно мы вы они меня тебя его её ее нас вас их мне тебе ему ей нам вам им мной тобой
ним ней ними нём нем них него неё нее нему себя себе собой свой своя своё свои это этот эта эти то тот та те
что кто который которая которое которые которых которым которого чего кого чем кому ком том тем тех того тому
и а но да или же ли бы не ни нет вот ведь уже ещё еще лишь только даже так как когда если то чтобы пока
в во на с со к ко о об обо от до из за по под над для при у без про через между перед
был была было были будет будут быть есть является являются поистине воистину о
кроме разве неужели потом затем тогда среди после прежде помимо вместо почему вместе будто словно
этого этому этим этими этой этих такие таких таким такой тогда всякий каждый когда-то несомненно
которыми которой которому которую каком какой какие сколько столько также тоже однако напротив
ничего никого никто ничто нечто что-то кто-то чем-то кому-то либо иначе подобно подобный
согласно благодаря вопреки вокруг около возле позади впереди внутри снаружи наконец непременно
поэтому потому оттого затем зачем откуда куда где здесь там туда сюда оттуда отсюда
самих самого самой самим сами себя ними вами нами тобой мною""".split())
# Имена-«предлоги» с корнем: подпись-предлог у них - норма, если это ожидаемый предлог.
PREP_OK = {"بَيْن": "между среди", "عِند": "у перед при", "غَيْر": "без не кроме иного", "لَّدُن": "от себя тебя нас него",
           "نَفْس": "себя себе собой сам", "شَىْء": "что чем чего ничего ничем", "أَحَد": "кто кого кому никто никого один",
           "فَوْق": "над выше", "تَحْت": "под", "وَرآء": "за позади", "قَبْل": "до прежде", "بَعْد": "после",
           "دُون": "помимо кроме вместо ниже меньше", "مَعَ": "с вместе", "حَوْل": "вокруг", "بَعْض": "одни часть некотор"}


def prep_ok(qac, g):
    low = g.lower()
    for lem, ok in PREP_OK.items():
        if "LEM:" + lem in qac:
            return any(re.search(r"(^|[^а-яё])" + w, low) for w in ok.split())
    return False
EN_FUNC = set("""the a an of to in on at by for with from and or but if then that which who whom whose what when
while as is are was were be been it he she they them him her his their its you your we us our i me my this
these those so not no nor indeed surely verily certainly o [is] will would shall should may might can could
do does did has have had upon into over about than until unless except also even only there here how why
where whatever whoever whenever wherever yes nay then, thus therefore""".split())
_W = re.compile(r"[a-zа-яё]+", re.I)


def content_ru(g):
    return [w for w in _W.findall(g.lower()) if w not in RU_FUNC]


def content_en(e):
    e = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", e)
    return [w for w in _W.findall(e.lower()) if w not in EN_FUNC]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    caps = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    hits = 0
    for key, glosses in caps.items():
        s, a = key.split(":")
        ref_path = ROOT / "sources" / "wbw_ru_refs" / f"{s}_{a}.json"
        if not ref_path.exists():
            print(f"нет опоры {key}")
            continue
        words = {w["pos"]: w for w in json.loads(ref_path.read_text(encoding="utf-8"))["words"]}
        for p, g in enumerate(glosses, 1):
            if g == "*" or p not in words:
                continue
            en = words[p].get("en_wbw") or ""
            en_neg, ru_neg = bool(NEG_EN.search(en)), bool(NEG_RU.search(g))
            qac = words[p].get("qac") or ""
            has_root = "ROOT:" in qac
            is_kana = "LEM:كانَ" in qac or "LEM:لَيْسَ" in qac
            kinds = []
            if en_neg and not ru_neg:
                kinds.append("A")
            elif ru_neg and not en_neg and not SKIP_B.search(en):
                kinds.append("B")
            if has_root and not is_kana and not content_ru(g) and content_en(en) and not prep_ok(qac, g):
                kinds.append("C")
            nxt_star = p < len(glosses) and glosses[p] == "*"      # слито со следующим - смысл здесь законно
            if not has_root and not nxt_star and not content_en(en) and any(len(w) >= 5 for w in content_ru(g)):
                kinds.append("D")
            for kind in kinds:
                hits += 1
                print(f"{kind} {key}:{p} | {words[p].get('ar')} | en={en} | ru={g}")
    print(f"кандидатов: {hits}")


if __name__ == "__main__":
    main()
