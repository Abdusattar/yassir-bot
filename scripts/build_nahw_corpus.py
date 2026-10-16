"""Сборка core/nahw_corpus.db.gz — грамматическая разметка слов Корана для
тренажёра нахва (17.09.2026).

Источник: Quranic Arabic Corpus v0.4 (corpus.quran.com, GNU GPL) в арабской
редакции mustafa0x/quran-morphology. Сами ответы тренажёра НЕ генерируются —
берутся из этой разметки как есть; ссылка на источник показывается в
приложении (условие лицензии).

Что делает: привязывает каждое слово корпуса к НАШЕЙ позиции слова
(mufradat_words.position), потому что тренажёр показывает слово в аяте из
нашей базы. Сверка 17.09.2026: 6232 аята из 6236 совпали по числу слов,
77381 слово из 77383 — по буквам. Четыре аята, где корпус пишет بَعْدَمَا /
إِلْ يَاسِينَ одним словом, а мы двумя, раскладываются по буквам; что не
разложилось — в файл не попадает, тренажёр такое слово просто не спросит.

Запуск (локально, нужен sources/):
    python scripts/build_nahw_corpus.py
"""
import collections
import gzip
import json
import os
import sqlite3
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources", "quranic_corpus", "quran-morphology.txt")
TERMS = os.path.join(ROOT, "sources", "quranic_corpus", "morphology-terms-ar.json")
HADITHS_DB = os.path.join(ROOT, "sources", "hadiths.db")
OUT = os.path.join(ROOT, "core", "nahw_corpus.db.gz")
# Весь Коран (16.10.2026): страницы приложения с 15.10 идут до 604. До того
# было 10 - пул не выходил за Юнус. В памяти это стоило ~80 МБ на бота и
# повесило сервер в тот же день - с тех пор корпус в SQLite на диске.
MAX_SURAH = 114


def skel(text):
    """Буквенный скелет без харакатов и знаков — только для сопоставления
    нашего написания с написанием корпуса (хамза на подставке, малые و ي)."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) == "Lo")
    for a, b in (("ٱ", "ا"), ("ى", "ي"), ("ء", ""), ("ۦ", ""), ("ۥ", ""), ("ـ", "")):
        text = text.replace(a, b)
    return text


def load_corpus():
    words = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            loc, form, tag, feats = line.rstrip("\n").split("\t")
            s, a, w, _seg = (int(x) for x in loc.split(":"))
            words[(s, a)][w].append([form, tag, feats])
    return words


def load_ours():
    ours = collections.defaultdict(dict)
    with sqlite3.connect(HADITHS_DB) as conn:
        for s, a, p, text in conn.execute(
                "SELECT surah_number, ayah_number, position, arabic_text"
                " FROM mufradat_words WHERE language='ru'"):
            ours[(s, a)][p] = text
    return ours


def align_by_letters(our_words, corpus_words):
    """Аят с разным числом слов: идём по сегментам корпуса и раздаём их нашим
    словам, пока буквы сходятся. Возвращает {position: [segments]} только для
    слов, которые сошлись целиком."""
    segs = [seg for w in sorted(corpus_words) for seg in corpus_words[w]]
    out, i = {}, 0
    for pos in sorted(our_words):
        want, got, taken = skel(our_words[pos]), "", []
        while i < len(segs) and len(got) < len(want):
            got += skel(segs[i][0])
            taken.append(segs[i])
            i += 1
        if got == want:
            out[pos] = taken
        else:
            return out          # дальше выравнивание ненадёжно - бросаем хвост аята
    return out


def main():
    corpus, ours = load_corpus(), load_ours()
    result, skipped, mismatched = {}, 0, 0
    for key in sorted(k for k in corpus if k[0] <= MAX_SURAH):
        cw, ow = corpus[key], ours.get(key, {})
        if len(cw) == len(ow):
            aligned = {}
            for pos, w in zip(sorted(ow), sorted(cw)):
                if skel("".join(seg[0] for seg in cw[w])) == skel(ow[pos]):
                    aligned[pos] = cw[w]
                else:
                    mismatched += 1
        else:
            aligned = align_by_letters(ow, cw)
            skipped += len(ow) - len(aligned)
        if aligned:
            result["%d:%d" % key] = {str(p): segs for p, segs in aligned.items()}
    # Индекс «тип случая -> слова» по правилам тренажёра (core/nahw_trainer.py):
    # правила поменялись - пересобрать файл.
    sys.path.insert(0, ROOT)
    from core import nahw_trainer
    ords, index = nahw_trainer.build_index(result)
    write_db(result, ords, index, json.load(open(TERMS, encoding="utf-8")))
    total = sum(len(v) for v in result.values())
    for sk, types in index.items():
        print("  %-7s %s" % (sk, ", ".join("%s %d" % (t, len(v)) for t, v in types.items())))
    print("аятов: %d, слов: %d, не сошлось по буквам: %d, не разложилось: %d, файл: %.1f МБ"
          % (len(result), total, mismatched, skipped, os.path.getsize(OUT) / 1e6))


def write_db(ayat, ords, index, terms):
    """SQLite, сжатый gzip: на сервере распаковывается на диск и читается
    запросами (core/nahw_trainer.py, _Corpus) - в память не грузится."""
    tmp = OUT[:-len(".gz")] + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    conn.executescript("""
        CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE ayat(ord INTEGER PRIMARY KEY, key TEXT NOT NULL UNIQUE, words TEXT NOT NULL);
        CREATE TABLE items(skill TEXT, ctype TEXT, n INTEGER, ord INTEGER, item TEXT,
                           PRIMARY KEY(skill, ctype, n)) WITHOUT ROWID;
        CREATE INDEX idx_items_ord ON items(skill, ctype, ord);
    """)
    conn.executemany("INSERT INTO meta VALUES(?,?)", [
        ("source", "Quranic Arabic Corpus v0.4, corpus.quran.com (GNU GPL);"
                   " арабская редакция mustafa0x/quran-morphology"),
        ("terms", json.dumps(terms, ensure_ascii=False))])
    conn.executemany("INSERT INTO ayat VALUES(?,?,?)",
                     ((o, k, json.dumps(ayat[k], ensure_ascii=False, separators=(",", ":")))
                      for k, o in ords.items()))
    conn.executemany("INSERT INTO items VALUES(?,?,?,?,?)",
                     ((sk, t, n, o, item) for sk, types in index.items()
                      for t, rows in types.items() for n, (o, item) in enumerate(rows)))
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    with open(tmp, "rb") as src, gzip.open(OUT, "wb", compresslevel=9) as dst:
        dst.write(src.read())
    os.remove(tmp)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
