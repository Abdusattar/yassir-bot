"""Звук ролика (style §7): отрезки чтения, края по огибающей, замер начала слова, room tone,
loudnorm в два прохода, 48 кГц, дорожка ровно до конца видео.

Источник декодируется один раз без перемотки (-ss до -i на mp3 не точен): замер и вырезка
идут по одному массиву отсчётов.
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from timeline import AUDIO, chapter_of, fetch

SR = 48000


def decode(path, seconds):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-t", str(seconds), "-ar", str(SR),
                          "-ac", "2", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def rms_db(x, t0, t1, win=0.010, hop=0.001):
    """RMS окнами 10 мс с шагом hop: (времена начала окон, дБFS)."""
    m = x.mean(1)
    w, h = int(win * SR), int(hop * SR)
    starts = np.arange(int(t0 * SR), int(t1 * SR) - w, h)
    r = np.array([np.sqrt(np.mean(m[s:s + w] ** 2)) for s in starts])
    return starts / SR, 20 * np.log10(r + 1e-12)


def measure_onset(x, qdc_start):
    """Начало первого слова отрезка (style §7): первое окно 10 мс RMS > −40 dBFS после ≥200 мс
    ниже −50. Запасные правила (у Аль-Афаси между аятами ~60 мс цифровой тишины, а слово внутри
    аята идёт слитно): тишина ≥40 мс; затем — скачок ≥15 дБ за 20 мс до уровня > −40.
    Возвращает (время в файле, правило)."""
    ts, db = rms_db(x, max(0, qdc_start - 0.6), qdc_start + 0.4)
    lo = 0.4  # искать начало не раньше qdc − 0,2 с
    # last[i] — длина (мс, шаг 1 мс) последнего отрезка ниже −50 dBFS до окна i
    run, best, last = 0, 0, []
    for d in db:
        if d < -50:
            run += 1
            best = run
        else:
            run = 0
        last.append(best)
        if d > -40:
            best = 0  # громкий звук обнуляет «тишину перед словом»
    for need, rule in ((200, "тишина ≥200 мс"), (40, "тишина ≥40 мс (запасное)")):
        for i in range(1, len(db)):
            if ts[i] >= qdc_start - 0.2 and db[i] > -40 and last[i - 1] >= need:
                return ts[i], rule
    lag = 20
    for i in range(lag, len(db)):
        if ts[i] >= qdc_start - 0.15 and ts[i] <= qdc_start + 0.15 + lo and db[i] > -40 \
                and db[i] - db[i - lag] >= 15:
            return ts[i], "скачок ≥15 дБ (запасное)"
    return qdc_start, "не замерено"


def check_edges(x, t_in, t_out):
    """Огибающая 10 мс в крайних 0,4 с: подъём >15 дБ после тишины в конце — хвост чужого аята
    или вдох (резать до него); тишина после звука в начале — остаток прошлого слова."""
    ts, db = rms_db(x, t_out - 0.4, t_out, hop=0.010)
    new_out, note = t_out, []
    for j in range(len(db)):
        quiet = [i for i in range(j) if db[i] < -50 and db[j] - db[i] > 15]
        if quiet:
            new_out = ts[quiet[0]] + 0.010
            note.append("хвост: подъём %.0f дБ в %.2f -> out %.3f" % (db[j] - db[quiet[0]], ts[j], new_out))
            break
    ts, db = rms_db(x, t_in, t_in + 0.4, hop=0.010)
    new_in = t_in
    for k in range(len(db)):
        if db[k] < -50 and max(db[:k], default=-200) > max(db[k] + 15, -50):
            new_in = ts[k]
            note.append("начало: остаток прошлого слова до %.2f -> in %.3f" % (ts[k], new_in))
            break
    return new_in, new_out, note


def fade(seg, fin, fout):
    n = len(seg)
    a, b = int(fin * SR), int(fout * SR)
    if a:
        seg[:a] *= np.linspace(0, 1, a)[:, None]
    if b:
        seg[n - b:] *= np.linspace(1, 0, b)[:, None]
    return seg


def write_wav(path, x):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_f32le", str(path)], input=x.astype(np.float32).tobytes(), check=True)


def loudnorm(src, dst, tp=-1.5):
    """loudnorm I=−16 TP LRA=11 в два прохода, линейно; затем 48 кГц."""
    base = "loudnorm=I=-16:TP=%s:LRA=11" % tp
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", base + ":print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8").stderr
    m = json.loads(re.findall(r"\{[^{}]+\}", err)[-1])
    f = (base + ":measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}"
         ":measured_thresh={input_thresh}:offset={target_offset}:linear=true:print_format=json").format(**m)
    err = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-i", str(src), "-af", f, "-ar", str(SR),
                          "-c:a", "pcm_f32le", str(dst)], capture_output=True, text=True, encoding="utf-8").stderr
    m2 = json.loads(re.findall(r"\{[^{}]+\}", err)[-1])
    return m, m2


def room_tone(n, level_dbfs, seed=1405):
    """Ровный фон комнаты: коричневатый шум (интеграл белого с утечкой), RMS = level_dbfs.
    Заглушка вместо своей записи комнаты (её пока нет)."""
    from scipy.signal import lfilter
    rng = np.random.default_rng(seed)
    y = lfilter([1.0], [1.0, -0.995], rng.normal(0, 1, (n, 2)), axis=0)
    y -= y.mean(0)
    y *= 10 ** (level_dbfs / 20) / np.sqrt(np.mean(y ** 2))
    return y


def prepare(sheet, cache):
    """Декодировать источники и замерить offset_measured для каждого отрезка чтения."""
    src = {}
    report = []
    for a in sheet["audio"]:
        if a["kind"] != "recitation":
            continue
        ch = chapter_of(a["src"])
        if ch not in src:
            mp3 = fetch(AUDIO % ch, Path(cache) / ("%d.mp3" % ch))
            need = max(b["out"] for b in sheet["audio"] if b.get("src") == a["src"]) + 2
            src[ch] = decode(mp3, need)
        x = src[ch]
        q0 = a["qdc"][a["words"][0]][0]
        onset, rule = measure_onset(x, q0)
        a["offset_measured"] = round(onset - q0, 3)
        a["_onset_rule"] = rule
        report.append("%s: qdc %.3f, замер %.3f (%s) -> offset_measured %+.3f" % (a["id"], q0, onset, rule,
                                                                                    a["offset_measured"]))
    return src, report


def build(sheet, src, total, work, out_wav):
    """Свести дорожку длиной ровно total секунд."""
    work = Path(work)
    n = int(round(total * SR))
    speech = np.zeros((n, 2), np.float32)
    notes = []
    for a in sheet["audio"]:
        if a["kind"] != "recitation":
            continue
        x = src[chapter_of(a["src"])]
        t_in, t_out, note = check_edges(x, a["in"], a["out"])
        notes += ["%s %s" % (a["id"], s) for s in note]
        fo = a["fade_out"] if t_out == a["out"] else 0.15
        seg = fade(x[int(round(t_in * SR)):int(round(t_out * SR))].copy(), a["fade_in"], fo)
        p = int(round((a["at"] + t_in - a["in"]) * SR))
        speech[p:p + len(seg)] += seg[:n - p]
    write_wav(work / "speech.wav", speech)
    m1, m2 = loudnorm(work / "speech.wav", work / "speech_norm.wav")
    notes.append("loudnorm: вход I %s LUFS TP %s; выход I %s TP %s, режим %s" % (
        m1["input_i"], m1["input_tp"], m2["output_i"], m2["output_tp"], m2["normalization_type"]))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(work / "speech_norm.wav"), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    mix = np.zeros((n, 2), np.float32)
    s = np.frombuffer(raw, np.float32).reshape(-1, 2)[:n]
    mix[:len(s)] = s
    for a in sheet["audio"]:
        if a["kind"] == "room_tone":
            p = int(a["at"] * SR)
            rt = room_tone(n - p, a["level_dbfs"])
            k = int(a["fade_in"] * SR)
            rt[:k] *= np.linspace(0, 1, k)[:, None]
            mix[p:] += rt.astype(np.float32)
    write_wav(out_wav, mix)  # длина = total: это и есть apad до конца видео
    return notes
