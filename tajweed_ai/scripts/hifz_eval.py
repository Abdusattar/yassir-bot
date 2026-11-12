# -*- coding: utf-8 -*-
"""
Шаг 1 (14.09.2026): чувствительность/специфичность obadx/quran-muaalem на
РЕАЛЬНЫХ сдачах хифза из YassirApp, размеченных устазами (verdict
accepted/retake + пометки слов error_words). До этого модель проверялась
только на заведомо верном чтении (Хусари/Афаси, Гейт №0) и на чужом QDAT.

Вход: data/umar_corpus/<id>/{student.ogg, meta.json} (см. fetch_umar_corpus.py
--only verdict). Единица чтения восстанавливается по hifz_page/hifz_line/
hifz_stage теми же правилами, что в приложении (mushaf_data/index.html:
hifzSubmitLines/hifzHalfRange/hifzTailTokens), текст слов - из
quran_transcript по (surah, ayah, position) токена страницы.

Выход: data/hifz_eval_results.jsonl (по сдаче) + сводка метрик в stdout
(--summary пересчитывает сводку из jsonl без инференса).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT.parent
MUSHAF_DIR = PROJECT / "mushaf_data"
CORPUS_DIR = ROOT / "data" / "umar_corpus"
import os
# HIFZ_RESULTS (11.11.2026): прогон на арендованном GPU пишет/читает свой файл,
# чтобы не смешивать с домашним CPU-прогоном.
RESULTS_PATH = Path(os.environ["HIFZ_RESULTS"]) if os.environ.get("HIFZ_RESULTS") else ROOT / "data" / "hifz_eval_results.jsonl"

sys.path.insert(0, str(ROOT / "scripts"))

_ARABIC_LETTER = re.compile(r"[ء-يٱ]")
_TAG = re.compile(r"<[^>]+>")


# ---------- единица чтения: те же правила, что в приложении ----------

_page_cache = {}


# Раскладка текущей сдачи (11.11.2026): 17% сдач Умар устаза - в Дар
# аль-Маариф (voice_submissions.hifz_layout='dm'), их строки и пометки - по
# страницам mushaf_data/dm/. Раньше всё бралось из мединских - чужой текст.
_LAYOUT = None


def text_lines(page):
    key = (_LAYOUT, page)
    if key not in _page_cache:
        base = MUSHAF_DIR / "dm" if _LAYOUT == "dm" else MUSHAF_DIR
        data = json.loads((base / f"page{page}.json").read_text(encoding="utf-8"))
        _page_cache[key] = [l for l in data["lines"] if l["type"] == "text"]
    return _page_cache[key]


def base_len(html):
    return len(_ARABIC_LETTER.findall(_TAG.sub("", html)))


def tail_token_count(next_tokens):
    """Порт hifzTailTokens: сколько первых токенов следующей строки входят в
    переход (1-3 слова, до конца аята, если слово короткое)."""
    taken, last = 0, -1
    for i, t in enumerate(next_tokens):
        if taken >= 3:
            break
        if t["type"] != "word":
            continue
        taken += 1
        last = i
        after = next_tokens[i + 1] if i + 1 < len(next_tokens) else None
        if taken == 1 and base_len(t["html"]) > 3:
            if not after or after["type"] != "ayah_end":
                break
        elif taken >= 2:
            if not after or after["type"] != "ayah_end":
                break
    return last + 1


def unit_line_idxs(page, line, stage):
    lines = text_lines(page)
    n = len(lines)
    if stage == 1:
        return [line]
    if stage == 2:
        mid = n // 2
        return list(range(0, mid)) if line < mid else list(range(mid, n))
    return list(range(n))


def unit_words(page, line, stage):
    """[(line_idx, token_idx, surah, ayah, position, in_tail, foreign)] по
    словам единицы + переход. line_idx/token_idx - координаты пометок устаза
    (data-line строки, индекс токена в строке)."""
    lines = text_lines(page)
    idxs = unit_line_idxs(page, line, stage)
    words = []
    for li in idxs:
        for ti, t in enumerate(lines[li]["tokens"]):
            if t["type"] == "word":
                words.append((li, ti, t["surah"], t["ayah"], t["position"], False, False))
    last = idxs[-1]
    if last + 1 < len(lines):
        nxt, nli, foreign = lines[last + 1], last + 1, False
    else:
        try:
            nxt, nli, foreign = text_lines(page + 1)[0], 0, True
        except (FileNotFoundError, IndexError):
            nxt = None
    if nxt:
        for ti, t in enumerate(nxt["tokens"][:tail_token_count(nxt["tokens"])]):
            if t["type"] == "word":
                words.append((nli, ti, t["surah"], t["ayah"], t["position"], True, foreign))
    return words


# ---------- эталон и разбиение фонем по словам ----------

def build_reference(words, qt, moshaf):
    """Текст единицы из quran_transcript (слова по позиции в аяте), его
    фонетизация и диапазон sifat-групп каждого слова (через mappings:
    символ исходного текста -> позиция в строке фонем)."""
    ayah_words = {}
    texts, spans, pos = [], [], 0
    for (_, _, s, a, p, _, _) in words:
        if (s, a) not in ayah_words:
            ayah_words[(s, a)] = qt.Aya(s, a).get().uthmani_words
        w = ayah_words[(s, a)][p - 1]
        if texts:
            pos += 1
        spans.append((pos, pos + len(w)))
        texts.append(w)
        pos += len(w)
    text = " ".join(texts)
    ref = qt.quran_phonetizer(text, moshaf, remove_spaces=True)

    # индекс фонемы -> индекс sifat-группы
    ph2group, gi = [], 0
    for gi, s in enumerate(ref.sifat):
        ph2group.extend([gi] * len(s.phonemes))
    word_groups = []
    for (cs, ce) in spans:
        lo, hi = None, None
        for c in range(cs, ce):
            if c >= len(ref.mappings):
                break
            p0, p1 = ref.mappings[c].pos
            if p1 > p0:
                lo = p0 if lo is None else min(lo, p0)
                hi = p1 - 1 if hi is None else max(hi, p1 - 1)
        if lo is None or lo >= len(ph2group):
            word_groups.append((None, None))
        else:
            word_groups.append((ph2group[lo], ph2group[min(hi, len(ph2group) - 1)]))
    return text, ref, word_groups


CHUNK_SEC = 45.0  # длиннее - модель на CPU не влезает в память (страница 160 с убила процесс дважды)


def split_wave(wave, sr=16000, chunk_sec=CHUNK_SEC, top_db=35):
    """Режем запись по паузам на куски <= chunk_sec: сначала интервалы речи
    (librosa.effects.split), затем жадно склеиваем соседние, пока влезает;
    речевой интервал длиннее лимита режем жёстко. Возвращает [(start, end)]
    в сэмплах."""
    import librosa
    n = len(wave)
    limit = int(chunk_sec * sr)
    if n <= limit:
        return [(0, n)]
    intervals = librosa.effects.split(wave, top_db=top_db)
    chunks, cur_s, cur_e = [], None, None
    for s, e in intervals:
        while e - s > limit:  # один длинный кусок речи без пауз
            if cur_s is not None:
                chunks.append((cur_s, cur_e)); cur_s = cur_e = None
            chunks.append((s, s + limit)); s += limit
        if cur_s is None:
            cur_s, cur_e = s, e
        elif e - cur_s <= limit:
            cur_e = e
        else:
            chunks.append((cur_s, cur_e)); cur_s, cur_e = s, e
    if cur_s is not None:
        chunks.append((cur_s, cur_e))
    return chunks


def _as_list(x):
    return [float(v) for v in (x.tolist() if hasattr(x, "tolist") else x)]


def _probs_no_pad(text, probs):
    """Вероятности по символам text без вставок "[PAD]" (см. evaluate_one).
    None, если длины всё равно не сошлись - лучше пусто, чем сдвиг."""
    out, i, k = [], 0, 0
    while i < len(text) and k < len(probs):
        if text.startswith("[PAD]", i):
            i += 5
        else:
            out.append(round(probs[k], 3)); i += 1
        k += 1
    if i != len(text) or k != len(probs):
        return None
    return out


def _p(unit):
    return round(unit.prob, 3) if unit is not None else None


# ---------- ветка «слух» (12.11.2026): внутренние представления по словам ----------
# Фильтр по готовым флагам упёрся в потолок (wiki/ai_tajweed_audio.md, 12.11), поэтому
# сохраняем то, что модель «слышит» до решения о фонеме: скрытые состояния нескольких
# слоёв, усреднённые по кадрам каждого слова. Включается флагом --emb <папка>.
EMB_LAYERS = (8, 16, 20, 24)   # средние слои хранят больше акустики, последний - ближе к фонемам
EMB_DIR = None
_CAP = {}                       # последний вызов модели: скрытые состояния и id фонем по кадрам


def install_capture(muaalem):
    """Оборачиваем forward модели: библиотека сама hidden_states не просит."""
    orig = muaalem.model.forward

    def forward(*a, **k):
        k["output_hidden_states"] = True
        out = orig(*a, **k)
        _CAP["hs"] = out[1]
        _CAP["ids"] = out[0]["phonemes"].argmax(-1)[0].cpu()
        return out
    muaalem.model.forward = forward


def _ctc_spans(ids, blank):
    """Кадры [start, end) каждого токена - ровно по логике quran_muaalem.decode.ctc_decode
    (включая её хвостовой случай), чтобы токены совпали с pred.phonemes.text."""
    seq = [int(x) for x in ids]
    out, start = [], 0
    if len(seq) == 1 and seq[0] != blank:
        out.append((seq[0], 0, 1))
    for i in range(len(seq) - 1):
        cur, nxt = seq[i], seq[i + 1]
        if i == len(seq) - 2 and cur != blank:
            if cur == nxt:
                out.append((cur, start, i + 2))
            else:
                out.append((cur, start, i + 1))
                out.append((nxt, i + 1, i + 2))
        elif cur != nxt and cur != blank:
            out.append((cur, start, i + 1)); start = i + 1
        elif cur == blank:
            start = i + 1
    return out


def _take_capture(offset):
    """-> (H [слои, кадры, 1024] float16, [(start, end)] по токенам без [PAD], кадры со сдвигом)."""
    import numpy as np
    from quran_muaalem.decode import PAD_TOKEN_IDX
    hs = _CAP["hs"]
    H = np.stack([hs[l][0].float().cpu().numpy() for l in EMB_LAYERS]).astype(np.float16)
    spans = [(s + offset, e + offset) for t, s, e in _ctc_spans(_CAP["ids"], PAD_TOKEN_IDX)
             if t != PAD_TOKEN_IDX]
    return H, spans


def word_embeddings(cap, ref, word_groups, diffs, tok_off):
    """Усреднение скрытых состояний по кадрам слова. Токен модели -> символ эталона (diff)
    -> sifat-группа -> слово. Вставки относим к предыдущему символу эталона: лишняя
    растяжка после слова - самый частый вид замечаний Умар устаза."""
    import numpy as np
    H, spans = cap
    ph2group = []
    for gi, s in enumerate(ref.sifat):
        ph2group.extend([gi] * len(s.phonemes))
    g2w = {}
    for wi, (lo, hi) in enumerate(word_groups):
        if lo is not None:
            for g in range(lo, hi + 1):
                g2w.setdefault(g, wi)
    n = len(word_groups)
    lo_f, hi_f = [None] * n, [None] * n
    r, t = 0, tok_off
    for op, txt in diffs:
        for _ in txt:
            if op == -1:
                r += 1
                continue
            ri = r if op == 0 else max(r - 1, 0)
            # вставка до первого символа эталона (истиаза, басмала, фальстарт) - ничья
            wi = g2w.get(ph2group[ri]) if ri < len(ph2group) and not (op == 1 and r == 0) else None
            if wi is not None and t < len(spans):
                s, e = spans[t]
                lo_f[wi] = s if lo_f[wi] is None else min(lo_f[wi], s)
                hi_f[wi] = e if hi_f[wi] is None else max(hi_f[wi], e)
            t += 1
            if op == 0:
                r += 1
    emb = np.zeros((n, H.shape[0], H.shape[2]), dtype=np.float16)
    span = np.full((n, 2), -1, dtype=np.int32)
    for wi in range(n):
        if lo_f[wi] is not None and hi_f[wi] > lo_f[wi]:
            emb[wi] = H[:, lo_f[wi]:hi_f[wi]].astype(np.float32).mean(1)
            span[wi] = (lo_f[wi], hi_f[wi])
    return emb, span


def run_muaalem(muaalem, wave, ref):
    """Инференс кусками с последующей склейкой фонем/сифатов в один
    объект того же вида, что MuaalemOutput (нужны только .phonemes.text и
    .sifat). Эталон каждому куску передаётся целиком - фонемы от него не
    зависят, сифаты выравниваются приближённо. Третьим возвращаем захват
    внутренних слоёв (или None, если --emb не задан)."""
    chunks = split_wave(wave)
    if len(chunks) == 1:
        out = muaalem([wave], [ref], sampling_rate=16000)[0]
        return out, 1, (_take_capture(0) if EMB_DIR else None)
    text, sifat, probs = "", [], []
    Hs, spans, off = [], [], 0
    for s, e in chunks:
        out = muaalem([wave[s:e]], [ref], sampling_rate=16000)[0]
        text += out.phonemes.text
        probs.extend(_as_list(out.phonemes.probs))
        sifat.extend(out.sifat)
        if EMB_DIR:
            H, sp = _take_capture(off)
            Hs.append(H); spans.extend(sp); off += H.shape[1]

    class _Ph:
        pass
    ph = _Ph(); ph.text = text; ph.probs = probs
    merged = _Ph(); merged.phonemes = ph; merged.sifat = sifat
    cap = None
    if EMB_DIR:
        import numpy as np
        cap = (np.concatenate(Hs, axis=1), spans)
    return merged, len(chunks), cap


def evaluate_one(muaalem, qt, qm_explain, dmp, rule_hint, moshaf, meta, wave):
    global _LAYOUT
    _LAYOUT = meta.get("hifz_layout")
    words = unit_words(meta["hifz_page"], meta["hifz_line"] or 0, meta["hifz_stage"] or 1)
    text, ref, word_groups = build_reference(words, qt, moshaf)
    t0 = time.time()
    pred, n_chunks, cap = run_muaalem(muaalem, wave, ref)
    infer_sec = time.time() - t0

    # Студенты часто начинают заново / читают строку дважды / открывают
    # басмалой - тогда предсказание заметно длиннее эталона, а прямой diff
    # размазывает эталон по двум попыткам и плодит ложные "пропуски".
    # Берём окно предсказания, лучше всего совпадающее с эталоном
    # (rapidfuzz partial_ratio_alignment), и сравниваем только его.
    pred_text, pred_sifat, window, tok_off = pred.phonemes.text, pred.sifat, None, 0
    if len(pred_text) > len(ref.phonemes) * 1.15:
        al = fuzz.partial_ratio_alignment(ref.phonemes, pred_text)
        if al is not None and al.dest_end > al.dest_start:
            starts, off = [], 0
            for s in pred_sifat:
                starts.append(off)
                off += len(s.phonemes_group)
            keep = [i for i, st in enumerate(starts)
                    if st + len(pred_sifat[i].phonemes_group) > al.dest_start and st < al.dest_end]
            if keep:
                pred_sifat = [pred_sifat[i] for i in keep]
                pred_text = "".join(s.phonemes_group for s in pred_sifat)
                window = (al.dest_start, al.dest_end, round(al.score, 1))
                tok_off = starts[keep[0]]

    class _Pred:  # тот же интерфейс, что ждёт rule_hint (predicted.sifat)
        sifat = pred_sifat

    dmp_obj = dmp.diff_match_patch()
    diffs = dmp_obj.diff_main(ref.phonemes, pred_text)
    groups = qm_explain.segment_groups([s.phonemes for s in ref.sifat],
                                       [s.phonemes_group for s in pred_sifat], diffs)
    bad = {}  # word_idx -> {"tags": set, "hint": str|None}
    n_groups_bad = 0
    for g in groups:
        if g.ref_idx is None:
            continue
        tag = g.get_tag()
        if tag == "exact":
            continue
        n_groups_bad += 1
        hint = rule_hint(g, ref, _Pred)
        for wi, (lo, hi) in enumerate(word_groups):
            if lo is not None and lo <= g.ref_idx <= hi:
                d = bad.setdefault(wi, {"tags": set(), "hint": None})
                d["tags"].add(tag)
                if hint and not d["hint"]:
                    d["hint"] = hint
                break

    # ветка «слух»: представления слов в файл <id>.npz. Пишем только если токены модели
    # сходятся с её же текстом без "[PAD]" - иначе кадры привязались бы не к тем словам.
    emb_ok = None
    if cap is not None:
        import numpy as np
        flat = pred.phonemes.text.replace("[PAD]", "")
        emb_ok = (len(cap[1]) == len(flat)
                  and "".join(s.phonemes_group for s in pred.sifat) == flat)
        if emb_ok:
            emb, span = word_embeddings(cap, ref, word_groups, diffs, tok_off)
            np.savez_compressed(EMB_DIR / f"{meta['submission_id']}.npz", emb=emb, span=span,
                                layers=np.array(EMB_LAYERS), n_frames=cap[0].shape[1])

    coords = {(li, ti): wi for wi, (li, ti, *_rest) in enumerate(words)}
    marks_in, marks_out = [], []
    for m in (meta.get("error_words") or []):
        wi = coords.get((m["line"], m["word"]))
        (marks_in if wi is not None else marks_out).append(wi if wi is not None else m)

    word_texts = text.split(" ")
    return {
        "id": meta["submission_id"],
        "student": meta["student_name"],
        "page": meta["hifz_page"], "line": meta["hifz_line"], "stage": meta["hifz_stage"],
        "layout": meta.get("hifz_layout"),
        "verdict": meta["verdict"], "verdict_by": meta.get("verdict_by_name"),
        "has_voice_review": meta.get("review_type") == "voice",
        "audio_sec": round(len(wave) / 16000, 1),
        "infer_sec": round(infer_sec, 1), "n_chunks": n_chunks,
        "n_words": len(words),
        "n_tail": sum(1 for w in words if w[5]),
        "ref_len": len(ref.phonemes), "pred_len": len(pred.phonemes.text),
        "window": window, "pred_len_window": len(pred_text),
        "n_groups_bad": n_groups_bad,
        "flag_any": sorted(bad),
        "flag_rule": sorted(wi for wi, d in bad.items() if d["hint"]),
        "flag_detail": {str(wi): {"word": word_texts[wi], "tags": sorted(d["tags"]), "hint": d["hint"]}
                        for wi, d in sorted(bad.items())},
        "marks": sorted(set(marks_in)),
        "marks_words": [word_texts[wi] for wi in sorted(set(marks_in))],
        "marks_outside": marks_out,
        "pred_phonemes": pred.phonemes.text,
        # группы модели целиком - чтобы пересчитывать правила офлайн (другие
        # длины мадда, без гунны и т.п.) без повторного инференса
        "pred_groups": [{"g": s.phonemes_group,
                         "q": s.qalqla.text if s.qalqla is not None else None,
                         "n": s.ghonna.text if s.ghonna is not None else None,
                         # уверенность модели по сифатам (11.11.2026, признак
                         # фильтра этапа 3)
                         "qp": _p(s.qalqla), "np": _p(s.ghonna)}
                        for s in pred.sifat],
        # уверенность по каждой фонеме pred_phonemes (11.11.2026): признак
        # «насколько модель сама уверена» для фильтра этапа 3. Длина должна
        # совпасть с pred_phonemes - иначе поле не пишем, чтобы не врать.
        # 12.11.2026: библиотека (ctc_decode, ветка «последний элемент») иногда
        # дописывает в конец куска пустой токен - в тексте это буквально "[PAD]"
        # (5 символов, одна вероятность). Из-за этого у ~четверти длинных сдач
        # длины не сходились и поле было пустым. pred_probs идёт по тексту БЕЗ
        # "[PAD]": pred_phonemes.replace("[PAD]", "") <-> pred_probs.
        "pred_probs": _probs_no_pad(pred.phonemes.text, _as_list(pred.phonemes.probs)),
        "ref_groups": [s.phonemes for s in ref.sifat],
        "word_groups": word_groups,
        "emb": emb_ok,
        "word_texts": word_texts,
        "student_id": meta.get("student_id"),
    }


# ---------- сводка ----------

def summarize(rows, ustaz=None):
    if ustaz:
        rows = [r for r in rows if r.get("verdict_by") == ustaz]
        print(f"\n[только вердикты: {ustaz}]")

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        return f"precision {p:.0%} ({tp}/{tp + fp}), recall {r:.0%} ({tp}/{tp + fn})"

    # Записи, физически слишком короткие для своей единицы (например 9 с на
    # целую страницу) - не чтение, а обрывок/ошибка отправки; их устаз мог
    # принять "по-человечески", но для модели это чистый шум - отдельно.
    too_short = [r for r in rows if r["audio_sec"] / max(1, r["n_words"]) < 0.3]
    rows = [r for r in rows if r not in too_short]
    print(f"\nСдач в оценке: {len(rows)} (исключено как слишком короткие для единицы: {len(too_short)}"
          f"{' - id ' + ','.join(str(r['id']) for r in too_short) if too_short else ''})")
    by_stage = {}
    for r in rows:
        by_stage.setdefault(r["stage"], []).append(r)
    for st, rs in sorted(by_stage.items()):
        print(f"  этап {st}: {len(rs)} (accepted {sum(r['verdict'] == 'accepted' for r in rs)}, "
              f"retake {sum(r['verdict'] == 'retake' for r in rs)}), "
              f"аудио в среднем {sum(r['audio_sec'] for r in rs) / len(rs):.0f} с, "
              f"инференс {sum(r['infer_sec'] for r in rs) / len(rs):.0f} с")

    # (a) Специфичность на уровне сдачи: accepted без пометок - сколько слов модель тронула
    clean = [r for r in rows if r["verdict"] == "accepted" and not r["marks"]]
    if clean:
        tot_w = sum(r["n_words"] for r in clean)
        fa = sum(len(r["flag_any"]) for r in clean)
        fr = sum(len(r["flag_rule"]) for r in clean)
        zero_any = sum(1 for r in clean if not r["flag_any"])
        zero_rule = sum(1 for r in clean if not r["flag_rule"])
        print(f"\n(a) accepted БЕЗ пометок: {len(clean)} сдач, {tot_w} слов")
        print(f"    любое расхождение фонем: {fa} слов ({fa / tot_w:.1%}); сдач без единого флага: {zero_any}/{len(clean)}")
        print(f"    с правило-диагнозом (мадд/калькаля): {fr} слов ({fr / tot_w:.1%}); сдач без флага: {zero_rule}/{len(clean)}")

    # (b) Пословная точность/полнота против пометок устаза (все сдачи с пометками внутри единицы)
    marked = [r for r in rows if r["marks"]]
    if marked:
        tp_a = fp_a = fn_a = tp_r = fp_r = fn_r = 0
        hit_subs_any = hit_subs_rule = 0
        for r in marked:
            m, fa, fr = set(r["marks"]), set(r["flag_any"]), set(r["flag_rule"])
            tp_a += len(m & fa); fp_a += len(fa - m); fn_a += len(m - fa)
            tp_r += len(m & fr); fp_r += len(fr - m); fn_r += len(m - fr)
            hit_subs_any += bool(m & fa)
            hit_subs_rule += bool(m & fr)
        n_marks = sum(len(r["marks"]) for r in marked)
        print(f"\n(b) сдачи с пометками устаза внутри единицы: {len(marked)}, пометок {n_marks}")
        print(f"    любое расхождение: {prf(tp_a, fp_a, fn_a)}; хотя бы одна пометка поймана в {hit_subs_any}/{len(marked)} сдачах")
        print(f"    правило-диагноз:   {prf(tp_r, fp_r, fn_r)}; хотя бы одна пометка поймана в {hit_subs_rule}/{len(marked)} сдачах")
        outside = sum(len(r["marks_outside"]) for r in rows)
        print(f"    пометок вне восстановленной единицы (не сопоставлены): {outside}")

    # (c) Разделяет ли модель accepted/retake на уровне сдачи
    acc = [r for r in rows if r["verdict"] == "accepted"]
    ret = [r for r in rows if r["verdict"] == "retake"]
    if acc and ret:
        def share(rs, key):
            return sum(len(r[key]) for r in rs) / max(1, sum(r["n_words"] for r in rs))
        print(f"\n(c) доля флагов на слово: accepted {share(acc, 'flag_any'):.1%} / retake {share(ret, 'flag_any'):.1%} (любое); "
              f"accepted {share(acc, 'flag_rule'):.1%} / retake {share(ret, 'flag_rule'):.1%} (правило)")
        def cov(rs):
            return sum(r["pred_len"] / max(1, r["ref_len"]) for r in rs) / len(rs)
        print(f"    длина предсказания/эталона: accepted {cov(acc):.2f}, retake {cov(ret):.2f} "
              f"(≈1 - прочитано всё; <<1 - недочитано/не распознано)")


def load_results():
    if not RESULTS_PATH.exists():
        return []
    return [json.loads(l) for l in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="только сводка из jsonl")
    ap.add_argument("--stage", type=int, choices=[1, 2, 3])
    ap.add_argument("--max-sec", type=float, default=420.0, help="пропускать аудио длиннее (с)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", help="через запятую")
    ap.add_argument("--ustaz", default="Умар", help="сводка только по вердиктам этого устаза ('' - все)")
    ap.add_argument("--device", default="cpu", help="cpu | cuda (арендованный GPU, modal_eval.py)")
    ap.add_argument("--emb", help="папка для представлений слов (ветка «слух», 12.11.2026)")
    args = ap.parse_args()
    global EMB_DIR
    if args.emb:
        EMB_DIR = Path(args.emb)
        EMB_DIR.mkdir(parents=True, exist_ok=True)

    done = load_results()
    if args.summary:
        summarize([r for r in done if not args.stage or r["stage"] == args.stage], args.ustaz or None)
        return

    import librosa
    import torch
    from rapidfuzz import fuzz as _fuzz
    global fuzz
    fuzz = _fuzz
    from diff_match_patch import diff_match_patch as _dmp_cls
    import quran_transcript as qt
    from quran_muaalem import Muaalem, explain as qm_explain
    from check_voices import rule_hint, MOSHAF_GENERIC

    class _dmp:  # тот же интерфейс, что в check_voices (модуль с классом)
        diff_match_patch = _dmp_cls

    done_ids = {r["id"] for r in done}
    metas = []
    for d in sorted(CORPUS_DIR.iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else 0):
        mp = d / "meta.json"
        if not mp.exists() or not (d / "student.ogg").exists():
            continue
        m = json.loads(mp.read_text(encoding="utf-8"))
        if not m.get("verdict") or m.get("hifz_page") is None:
            continue
        if args.stage and (m.get("hifz_stage") or 1) != args.stage:
            continue
        if args.ids and str(m["submission_id"]) not in args.ids.split(","):
            continue
        if m["submission_id"] in done_ids:
            continue
        metas.append((d, m))
    if args.limit:
        metas = metas[:args.limit]
    print(f"К оценке: {len(metas)} сдач (уже сделано {len(done)})", flush=True)
    if not metas:
        summarize(done, args.ustaz or None)
        return

    muaalem = Muaalem(device=args.device, dtype=torch.float32)
    if EMB_DIR:
        install_capture(muaalem)
    for d, m in metas:
        wave, _ = librosa.load(str(d / "student.ogg"), sr=16000, mono=True)
        sec = len(wave) / 16000
        if sec > args.max_sec:
            print(f"  [{m['submission_id']}] пропуск: {sec:.0f} с > {args.max_sec:.0f}", flush=True)
            continue
        try:
            row = evaluate_one(muaalem, qt, qm_explain, _dmp, rule_hint, MOSHAF_GENERIC, m, wave)
        except Exception as e:  # noqa: BLE001 - одна битая сдача не должна ронять прогон
            print(f"  [{m['submission_id']}] ОШИБКА {type(e).__name__}: {e}", flush=True)
            continue
        with open(RESULTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        done.append(row)
        print(f"  [{row['id']}] {row['student']} стр.{row['page']} эт.{row['stage']} {row['verdict']}: "
              f"{row['audio_sec']:.0f}с, слов {row['n_words']}, флаги any={len(row['flag_any'])} "
              f"rule={len(row['flag_rule'])}, пометки={row['marks']} ({row['infer_sec']:.0f}с)", flush=True)
    summarize(done, args.ustaz or None)


if __name__ == "__main__":
    main()
