# -*- coding: utf-8 -*-
"""
Офлайн-проверка голосовых сдач студентов группы G2b (23.07.2026, пилот).

Архитектура (см. wiki/ai_tajweed_audio.md): боевой бот на сервере ТОЛЬКО
сохраняет file_id голосового (core/db.py, voice_submissions.file_id).
Весь тяжёлый пайплайн - здесь, локально, крутится циклом опроса (раз в
POLL_INTERVAL_SEC) пока запущен на компьютере пользователя:

    1. Забрать новые voice_submissions с file_id из БД на сервере (SSH,
       read-only) для группы G2b, которые ещё не проверялись (локальный
       трекер processed_ids.json - НЕ трогаем боевую БД лишними полями).
    2. Скачать аудио через Telegram Bot API (getFile + download).
    3. Whisper (tarteel-ai/whisper-base-ar-quran) - грубая транскрипция.
    4. Нечёткое сопоставление (rapidfuzz) с аятами в известном диапазоне
       группы (Аль-Бакара, примерно страницы 8-20 мусхафа) - НЕ через
       quran_transcript.search(), она требует точного посимвольного
       совпадения после нормализации и не годится для шумного ASR-вывода
       (проверено 23.07 - даже ignore_hamazat не спасает).
    5. obadx/quran-muaalem - фонемный+sifat разбор против найденного аята.
    6. Отчёт на русском в группу устазов (SCALING_CHAT_ID): имя студента,
       время сдачи, найденный аят + сырая транскрипция (чтобы устаз мог
       сам проверить, что аят определён верно, ПРЕЖДЕ чем доверять
       остальному) + сигналы по мадду/ихфе. Гунна НЕ репортится - её
       бинарный сигнал доказанно нечувствителен (Гейт QDAT, 23.07,
       1/6 на несовпадающих метках).

ВАЖНО: это ТЕНЕВАЯ проверка для оценки качества самими устазами
(Абдусаттар + Умар устаз в группе масштабирования), НЕ для студентов.
Ничего не отправляется студентам и не подменяет проверку
устазом/студентом-проверяющим.
"""
import asyncio
import json
import re
from pathlib import Path

import httpx
import librosa
import torch
from rapidfuzz import fuzz

import quran_transcript as qt
from quran_transcript import normalize_aya
from quran_muaalem import Muaalem
from quran_muaalem import explain as qm_explain
import diff_match_patch as dmp

ROOT = Path(__file__).resolve().parent.parent

# .env (не в git) - см. tajweed_ai/.env
_env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        _env[k.strip()] = v.strip()

BOT_TOKEN = _env["BOT_TOKEN"]
SCALING_CHAT_ID = _env["SCALING_CHAT_ID"]
G2B_GROUP_ID = int(_env["G2B_GROUP_ID"])
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TG_FILE_API = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

PROCESSED_PATH = ROOT / "data" / "check_voices_processed.json"
REPORT_LOG_PATH = ROOT / "data" / "check_voices_reports.jsonl"

# Пивот поиска аята: G2b читает примерно стр. 8-20 мусхафа (Аль-Бакара) -
# грубая оценка по словам пользователя, точность не критична для fuzzy-поиска.
SEARCH_SURA = 2
SEARCH_AYAH_FROM = 40
SEARCH_AYAH_TO = 140
FUZZY_MATCH_THRESHOLD = 55  # ниже - считаем "не удалось определить аят"

MOSHAF_GENERIC = qt.MoshafAttributes(
    rewaya="hafs", recitation_speed="murattal",
    madd_monfasel_len=4, madd_mottasel_len=4, madd_mottasel_waqf=4,
    madd_aared_len=4, madd_alleen_len=4, madd_yaa_alayn_alharfy=6,
)

SSH_CMD = [
    "ssh", "-i", str(Path.home() / ".ssh" / "claude_gcp"),
    "claude-access@34.51.213.67",
]


def load_processed():
    if PROCESSED_PATH.exists():
        return set(json.loads(PROCESSED_PATH.read_text(encoding="utf-8")))
    return set()


def save_processed(ids):
    PROCESSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_PATH.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def fetch_new_submissions():
    """Забрать новые (не обработанные локально) voice_submissions группы G2b
    с непустым file_id. Read-only SSH-запрос, боевую БД не трогаем."""
    import subprocess

    query = f"""
import sqlite3, json
c = sqlite3.connect('/home/stursunkul/yassir-bot/quran_male.db')
c.row_factory = sqlite3.Row
rows = c.execute('''
    SELECT vs.id, vs.student_id, vs.chat_id, vs.message_id, vs.file_id, vs.sent_at, u.name
    FROM voice_submissions vs JOIN users u ON u.id = vs.student_id
    WHERE vs.group_id={G2B_GROUP_ID} AND vs.file_id IS NOT NULL
    ORDER BY vs.id
''').fetchall()
print(json.dumps([dict(r) for r in rows], ensure_ascii=False))
"""
    result = subprocess.run(
        SSH_CMD + [f"sudo -u stursunkul /home/stursunkul/yassir-bot/venv/bin/python3 -c \"{query}\""],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH query failed: {result.stderr.decode('utf-8', errors='replace')}")
    stdout_text = result.stdout.decode("utf-8", errors="replace")
    return json.loads(stdout_text.strip().splitlines()[-1])


def download_voice(file_id):
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{TG_API}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]
        audio_resp = client.get(f"{TG_FILE_API}/{file_path}")
        audio_resp.raise_for_status()
        return audio_resp.content


_whisper_model = None
_whisper_processor = None


def transcribe(wave):
    global _whisper_model, _whisper_processor
    if _whisper_model is None:
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        _whisper_processor = WhisperProcessor.from_pretrained("tarteel-ai/whisper-base-ar-quran")
        _whisper_model = WhisperForConditionalGeneration.from_pretrained("tarteel-ai/whisper-base-ar-quran")
    inputs = _whisper_processor(wave, sampling_rate=16000, return_tensors="pt")
    ids = _whisper_model.generate(inputs["input_features"])
    return _whisper_processor.batch_decode(ids, skip_special_tokens=True)[0]


MIN_TRANSCRIPT_WORDS = 4  # короткие обрывки (напр. одна басмала) слишком
# похожи на много разных аятов - fuzzy-поиск даёт уверенно-неверные совпадения


def word_char_ranges(ayah_idx):
    """Для каждого слова аята - диапазон символов в нормализованной (без
    пробелов/ташкиля/хамзы) имлей-строке. Нужно чтобы понять, какую ИМЕННО
    часть длинного аята покрывает запись (студент часто читает не аят
    целиком, а строчку/фрагмент) - см. лог сессии 23.07, баг с Сатаром."""
    a = qt.Aya(SEARCH_SURA, ayah_idx).get()
    cum = 0
    ranges = []
    for imlaey_w, uthmani_w in zip(a.imlaey_words, a.uthmani_words):
        norm_w = normalize_aya(imlaey_w, remove_spaces=True,
                                remove_tashkeel=True, ignore_hamazat=True)
        ranges.append((cum, cum + len(norm_w), uthmani_w))
        cum += len(norm_w)
    return ranges


def identify_ayah(transcript_text):
    """Нечёткий поиск лучшего совпадения по диапазону аятов (не
    quran_transcript.search() - см. заголовок файла почему).

    Возвращает (score, ayah_idx, word_start_idx, word_end_idx) - последние
    два: какой диапазон СЛОВ аята реально покрывает запись (по индексу в
    uthmani_words), не обязательно весь аят целиком."""
    if len(transcript_text.split()) < MIN_TRANSCRIPT_WORDS:
        return (0, None, None, None)

    query_norm = normalize_aya(transcript_text, remove_spaces=True,
                                remove_tashkeel=True, ignore_hamazat=True)
    best = None
    for ayah_i in range(SEARCH_AYAH_FROM, SEARCH_AYAH_TO + 1):
        a = qt.Aya(SEARCH_SURA, ayah_i).get()
        ref_norm = normalize_aya(a.imlaey, remove_spaces=True,
                                  remove_tashkeel=True, ignore_hamazat=True)
        score = fuzz.partial_ratio(query_norm, ref_norm)
        if best is None or score > best[0]:
            best = (score, ayah_i)

    score, ayah_idx = best
    if score < FUZZY_MATCH_THRESHOLD:
        return (score, ayah_idx, None, None)

    winner_ref_norm = normalize_aya(qt.Aya(SEARCH_SURA, ayah_idx).get().imlaey, remove_spaces=True,
                                     remove_tashkeel=True, ignore_hamazat=True)
    alignment = fuzz.partial_ratio_alignment(query_norm, winner_ref_norm)
    ranges = word_char_ranges(ayah_idx)
    covered_idx = [i for i, (s, e, _) in enumerate(ranges)
                   if e > alignment.dest_start and s < alignment.dest_end]
    if not covered_idx:
        return (score, ayah_idx, 0, len(ranges) - 1)
    return (score, ayah_idx, covered_idx[0], covered_idx[-1])


def word_ranges_for_ayah(ayah_idx, moshaf):
    """(индекс слова, диапазон фонемных групп, слово) для аята. Считается
    безопасно (без IndexError phonetizer'а) через фонетизацию нарастающих
    префиксов слов, а не отдельного слова - phonetizer падает на
    произвольных подстроках."""
    words = qt.Aya(SEARCH_SURA, ayah_idx).get().uthmani_words
    ranges = []
    prev_n = 0
    for i in range(1, len(words) + 1):
        prefix = " ".join(words[:i])
        ref = qt.quran_phonetizer(prefix, moshaf, remove_spaces=True)
        n = len(ref.sifat)
        ranges.append((i - 1, prev_n, n - 1, words[i - 1]))
        prev_n = n
    return ranges


MADD_CHARS = set("اۦۥں")  # символы растяжки/назализации - если группа состоит
# из повтора одного из них, разница длины = разница в харакятах растяжки


def rule_hint(g, ref_out, predicted):
    """Проверка по САМОЙ модели (не ASR-догадка) - только то, что реально
    проверено на Гейте №0/QDAT: длина растяжки (мадд) и калькаля. Гунну
    намеренно не трогаем - её сигнал доказанно нечувствителен."""
    hints = []
    if g.ref and len(set(g.ref)) == 1 and g.ref[0] in MADD_CHARS:
        ref_len, out_len = len(g.ref), len(g.out or "")
        if out_len < ref_len:
            hints.append(f"растяжка короче нужного (ожидалось примерно {ref_len} харакята, "
                          f"услышано около {out_len})")
        elif out_len > ref_len:
            hints.append(f"растяжка длиннее нужного (ожидалось примерно {ref_len} харакята, "
                          f"услышано около {out_len})")

    if g.ref_idx is not None and g.out_idx is not None and g.out_idx < len(predicted.sifat):
        exp_qalqla = ref_out.sifat[g.ref_idx].qalqla
        pred_qalqla = predicted.sifat[g.out_idx].qalqla
        pred_qalqla_text = pred_qalqla.text if pred_qalqla is not None else None
        if exp_qalqla == "moqalqal" and pred_qalqla_text == "not_moqalqal":
            hints.append("не хватает калькали (характерного «отскока» звука)")
        elif exp_qalqla == "not_moqalqal" and pred_qalqla_text == "moqalqal":
            hints.append("лишняя калькаля там, где её быть не должно")

    return "; ".join(hints) if hints else None


def find_mismatched_words(predicted, ref_out, word_ranges, word_start_idx, word_end_idx):
    """Возвращает список (word_idx, word, rule_hint) аята (в пределах
    [word_start_idx, word_end_idx] - той части аята, которую реально
    покрывает запись, см. identify_ayah), где есть расхождение звучания с
    эталоном. Группы без ref_idx (басмала/приветствие в начале записи)
    молча пропускаются. rule_hint - см. rule_hint(), может быть None."""
    dmp_obj = dmp.diff_match_patch()
    diffs = dmp_obj.diff_main(ref_out.phonemes, predicted.phonemes.text)
    ref_chunks = [s.phonemes for s in ref_out.sifat]
    pred_chunks = [s.phonemes_group for s in predicted.sifat]
    groups = qm_explain.segment_groups(ref_chunks, pred_chunks, diffs)

    bad_words = []
    seen = set()
    for g in groups:
        if g.ref_idx is None or g.get_tag() == "exact":
            continue
        hint = rule_hint(g, ref_out, predicted)
        for word_idx, start, end, word in word_ranges:
            if not (word_start_idx <= word_idx <= word_end_idx):
                continue
            if start <= g.ref_idx <= end:
                if word_idx not in seen:
                    seen.add(word_idx)
                    bad_words.append((word_idx, word, hint))
                elif hint:
                    # дополним уже добавленное слово, если раньше подсказки не было
                    for i, (wi, w, h) in enumerate(bad_words):
                        if wi == word_idx and h is None:
                            bad_words[i] = (wi, w, hint)
                break
    return bad_words


def format_report(name, sent_at, ayah_idx, match_score, word_start_idx, word_end_idx,
                   transcript, predicted, ref_out, moshaf):
    if ayah_idx is None:
        return (
            "🎙 Теневая проверка таджвида (пилот, R&D)\n"
            f"Студент: {name} ({sent_at})\n"
            f"Сырая ASR-транскрипция: {transcript}\n\n"
            "⚠️ Запись слишком короткая/малосодержательная — аят не определялся, "
            "результата нет."
        )

    all_words = qt.Aya(SEARCH_SURA, ayah_idx).get().uthmani_words
    covered_text = " ".join(all_words[word_start_idx:word_end_idx + 1]) if word_start_idx is not None else " ".join(all_words)
    lines = [
        "🎙 Теневая проверка таджвида (пилот, R&D)",
        f"Студент: {name} ({sent_at})",
        f"Найденный аят: 2:{ayah_idx}, распознанный фрагмент: {covered_text}",
        f"Уверенность определения: {match_score:.0f}%",
        f"Сырая ASR-транскрипция (для сверки, могут быть свои ошибки распознавания): {transcript}",
        "",
    ]
    if match_score < FUZZY_MATCH_THRESHOLD:
        lines.append("⚠️ Низкая уверенность в определении аята — дальнейший результат НЕ показателен, "
                      "аят мог быть определён неверно.")
        return "\n".join(lines)

    word_ranges = word_ranges_for_ayah(ayah_idx, moshaf)
    bad_words = find_mismatched_words(predicted, ref_out, word_ranges, word_start_idx, word_end_idx)

    lines.append("— — —")
    lines.append("Черновик поправки студенту (проверить перед отправкой):")
    lines.append("")

    if not bad_words:
        lines.append(f"Ассаляму алейкум! Прослушал(а) твоё чтение — «{covered_text}».")
        lines.append("Явных расхождений не найдено, машаллах. Так держать 🤲")
        lines.append("")
        lines.append("(экспериментальная проверка, не замена устаза/проверяющего)")
        return "\n".join(lines)

    # Показываем только слова с конкретным правило-диагнозом (мадд/калькаля -
    # проверено Гейтом №0). Слова, где модель заметила расхождение, но без
    # диагноза, молча отбрасываем - "стоит перепроверить" ни на что не
    # указывает и не помогает устазу.
    rule_words = [(idx, w, rhint) for idx, w, rhint in bad_words if rhint]

    if not rule_words:
        lines.append(f"Ассаляму алейкум! Прослушал(а) твоё чтение — «{covered_text}».")
        lines.append("По проверенным правилам (мадд, калькаля) явных нарушений не найдено. "
                      "Модель заметила лёгкие расхождения звучания в некоторых словах, но не "
                      "смогла назвать конкретную причину — окончательное слово за устазом на слух.")
        lines.append("")
        lines.append("(экспериментальная проверка, не замена устаза/проверяющего)")
        return "\n".join(lines)

    student_lines = [f"Ассаляму алейкум! Прослушал(а) твоё чтение — «{covered_text}».", ""]
    student_lines.append("В целом хорошо, но обрати внимание на:")
    student_lines.append("")

    for _, w, rhint in rule_words:
        student_lines.append(f"  {w} — {rhint}")

    student_lines.append("")
    student_lines.append("Прочитай эти слова ещё раз медленно, вслушиваясь в каждую букву, "
                          "а потом повтори весь аят целиком. Если сомневаешься — пришли новую "
                          "запись, разберём вместе.")
    student_lines.append("")
    student_lines.append("Баракаллаху фик 🤲")

    lines.extend(student_lines)
    lines.append("")
    lines.append("(экспериментальная проверка, гунна и буквенные замены не проверяются — "
                  "их сигнал ненадёжен; показаны только слова с проверенным правило-диагнозом "
                  "(мадд/калькаля); не замена устаза/проверяющего)")
    return "\n".join(lines)


async def send_to_scaling(text):
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(f"{TG_API}/sendMessage", data={"chat_id": SCALING_CHAT_ID, "text": text})


POLL_INTERVAL_SEC = 300  # 5 минут


def process_batch(muaalem, processed):
    print("Забираю новые сдачи с сервера...")
    submissions = fetch_new_submissions()
    new_subs = [s for s in submissions if s["id"] not in processed]
    print(f"Всего сдач с file_id: {len(submissions)}, новых: {len(new_subs)}")

    for sub in new_subs:
        print(f"\n=== id={sub['id']} студент={sub['name']} ===")
        audio_bytes = download_voice(sub["file_id"])
        tmp_path = ROOT / "data" / f"_tmp_voice_{sub['id']}.ogg"
        tmp_path.write_bytes(audio_bytes)
        wave, _ = librosa.load(str(tmp_path), sr=16000, mono=True)
        tmp_path.unlink()

        transcript = transcribe(wave)
        print("Транскрипция:", transcript)

        score, ayah_idx, word_start_idx, word_end_idx = identify_ayah(transcript)
        print(f"Определён аят: 2:{ayah_idx} (уверенность {score:.0f}%), "
              f"слова [{word_start_idx}:{word_end_idx}]")

        pred = ref_out = None
        if score >= FUZZY_MATCH_THRESHOLD:
            ref_out = qt.quran_phonetizer(qt.Aya(SEARCH_SURA, ayah_idx).get().uthmani,
                                           MOSHAF_GENERIC, remove_spaces=True)
            pred = muaalem([wave], [ref_out], sampling_rate=16000)[0]

        report = format_report(sub["name"], sub["sent_at"], ayah_idx, score,
                                word_start_idx, word_end_idx, transcript,
                                pred, ref_out, MOSHAF_GENERIC)
        print(report)

        asyncio.run(send_to_scaling(report))

        with open(REPORT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({**sub, "transcript": transcript, "ayah": ayah_idx,
                                 "score": score, "report": report}, ensure_ascii=False) + "\n")

        processed.add(sub["id"])
        save_processed(processed)

    if new_subs:
        print(f"\nОбработано {len(new_subs)} новых сдач.")


def main_loop():
    import time

    processed = load_processed()
    print("Загрузка Muaalem (один раз, дальше просто ждём новых сдач)...")
    muaalem = Muaalem(device="cpu", dtype=torch.float32)
    print(f"Готово. Опрашиваю сервер каждые {POLL_INTERVAL_SEC // 60} мин. Ctrl+C для остановки.")

    while True:
        try:
            process_batch(muaalem, processed)
        except Exception as e:
            print(f"[ошибка в цикле опроса, продолжаю через {POLL_INTERVAL_SEC}с]: {e}")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main_loop()
