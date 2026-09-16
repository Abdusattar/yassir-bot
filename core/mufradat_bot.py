"""Серверная часть тренажёров и сдач из YassirApp (движок муфрадата -
core/mufradat.py, HTTP-обвязка - core/mufradat_api.py).

До 15.09.2026 здесь жила Telegram-версия тренажёра муфрадата (фото-карточка
в личке с кнопками ответов, ➕/➖ закладки, меню языка, «Закончить», /muftop).
Тренажёр переехал в приложение 29.08.2026, чатовый путь убран целиком
решением пользователя 15.09.2026 ("он больше не нужен"). Остались вещи, у
которых транспорт - Telegram-сообщения, а вызов идёт из приложения: зачёт
заданий «Слова» и «Повторение», сдача записи хифза, вердикт и голосовой
комментарий устаза, гендерный фильтр и дивизионы рейтинга.
"""
import asyncio
import logging

from core.content import SHORT_TASKS
from core.db import (
    find_user_by_phone, get_learning_group, get_group_tasks, save_report, get_date,
    get_today_report, save_voice_submission, get_open_retakes, get_submission,
    set_submission_verdict, save_submission_review, get_dm_ok, VERDICT_ACCEPTED,
    VERDICT_RETAKE, is_retake_answered, revision_record_required, save_revision_recording,
    REVISION_FIRST_PAGE,
)
from core.mufradat import (
    get_leaderboard, DAILY_WORDS_FOR_TASK_CREDIT, DAILY_CORRECT_FOR_TASK_CREDIT,
    compute_overall_score,
)
from core.mushaf_words import get_hifz_pointer
from core.tg import send_message, send_photo_bytes, send_voice_bytes

log = logging.getLogger(__name__)


async def _credit_task_if_applicable(user_id, chat_id):
    """Дневная норма тренажёра выполнена (get_daily_words_status в
    core/mufradat.py: 40 разных слов и 20 из них верно, второй порог с
    15.09.2026) - засчитываем задание 't' ("Слова (или Перевод)",
    core/handlers.py), если оно вообще есть в группе студента.
    Вызывающий код зовёт нас на КАЖДЫЙ ответ после выполнения нормы, не
    только на первом: два тапа почти одновременно (без лока) могут оба
    увидеть порог - save_report идемпотентен (INSERT OR IGNORE), лишний
    вызов не страшен. Но чтобы не слать поздравление на каждый следующий
    тап, сверяемся с get_today_report - текст только при первой отметке
    (advisor 17.08.2026, поймал и гонку, и повторный спам).

    Обычные задания студент сдаёт ТЕКСТОМ прямо в группе - там же и видно
    подтверждение (core/handlers.py). Здесь сдача происходит в личке с
    ботом (тренажёр), поэтому группа иначе не узнала бы - дублируем
    короткое уведомление в group["chat_id"] с текущим весом (решение
    пользователя 17.08.2026)."""
    # include_prep - студент подготовительной сдаёт те же задания в свою
    # группу (04.09.2026, см. get_learning_group).
    group = get_learning_group(user_id, include_prep=True)
    if not group or "t" not in get_group_tasks(group):
        return
    user = find_user_by_phone(user_id)
    if not user:
        return
    already = get_today_report(user["id"], group["id"]) or {}
    if already.get("t"):
        return
    save_report(user["id"], group["id"], get_date(), {"t": True})
    await send_message(
        chat_id,
        f"🎉 Задание «Слова» на сегодня засчитано — {DAILY_WORDS_FOR_TASK_CREDIT} слов проработано, "
        f"{DAILY_CORRECT_FOR_TASK_CREDIT}+ из них верно!"
    )

    if group["chat_id"]:
        score = compute_overall_score(user_id)
        score_part = f", вес {score['score10']:.2f}/10" if score else ""
        # Тот же короткий формат "Имя, Слова +.", что и у обычной сдачи
        # текстом в группе (core/handlers.py, SHORT_TASKS) - раньше здесь
        # было длинное отдельное предложение, из которого не считывалось
        # "сдал дневное задание" (пользователь 18.08.2026). "через тренажёр"
        # поясняет, откуда взялось выполнение - обычно сдача идёт текстом
        # прямо в группе, здесь источник другой (личка с ботом).
        await send_message(
            group["chat_id"],
            f"{user['name']}, Слова + (через тренажёр{score_part})."
        )


async def credit_revision_task(user_id):
    """Кнопка "🔁" на странице чтения мусхафа (30.08.2026, решение
    пользователя) - студент сам отмечает, что перечитал (сделал повторение)
    от начала суры Аль-Бакара до места, где остановился, подтвердив во
    всплывающем окне на фронтенде ("Вы сделали повторение...?" -> "Да").
    На доверии, без проверки самого факта прочтения - как и обычная
    текстовая сдача "повторение" в группе (core/handlers.py), эта кнопка -
    просто альтернативный способ сдать ТО ЖЕ САМОЕ задание "r", без набора
    текста и ИИ-классификации.

    Возвращает True, если засчитано сейчас; False - если сегодня уже было
    (тихо, без сообщения в группу - тот же принцип, что у
    _credit_task_if_applicable выше, не спамим группу на повторный тап) или
    если "r" не входит в задания группы студента / студент не найден."""
    group = get_learning_group(user_id, include_prep=True)
    if not group or "r" not in get_group_tasks(group):
        return False
    user = find_user_by_phone(user_id)
    if not user:
        return False
    # Несовершеннолетним тап не засчитывается (16.09.2026): только запись
    # чтения, см. submit_revision_recording. API отвечает record_required.
    if revision_record_required(user_id):
        return False
    already = get_today_report(user["id"], group["id"]) or {}
    if already.get("r"):
        return False
    save_report(user["id"], group["id"], get_date(), {"r": True})
    if group["chat_id"]:
        # "(через YassirApp, Мусхаф)" - решение пользователя 30.08.2026,
        # тот же принцип, что у _credit_task_if_applicable выше ("через
        # тренажёр") - явно поясняет источник сдачи, раз она не текстом.
        await send_message(
            group["chat_id"],
            f"{user['name']}, {SHORT_TASKS['r'].lower()} + (через YassirApp, Мусхаф)."
        )
    return True


async def submit_revision_recording(user_id, audio_bytes, client_ms=None, page_to=None):
    """Повторение записью (16.09.2026, несовершеннолетние): студент читает с
    начала Аль-Бакары до своего места, приложение пишет звук, запись уходит
    в группу голосовым с подписью «Имя, повторение + (запись 12:40,
    стр. 2–17)», ложится в revision_recordings для строки «Повторения» в
    кабинете устаза и засчитывает дневное задание «r». Охват страниц берётся
    из указателя заучивания (до какой страницы дошёл), page_to с фронта -
    только подстраховка, если указателя нет.

    Тон подписи в группе - как у обычной сдачи, без «коротко»: пометка
    короткой записи (REVISION_MIN_SEC_PER_PAGE) видна только устазу."""
    group = get_learning_group(user_id, include_prep=True)
    if not group or "r" not in get_group_tasks(group):
        return {"ok": False, "error": "no_group"}
    user = find_user_by_phone(user_id)
    if not user:
        return {"ok": False, "error": "no_group"}
    pointer = get_hifz_pointer(user_id)
    if pointer and pointer.get("page"):
        page_to = int(pointer["page"])
    page_to = max(REVISION_FIRST_PAGE, int(page_to or REVISION_FIRST_PAGE))

    ogg = await transcode_to_ogg(audio_bytes)
    if not ogg:
        return {"ok": False, "error": "bad_audio"}

    already = get_today_report(user["id"], group["id"]) or {}
    credited = not already.get("r")
    sec = client_ms and round(client_ms / 1000)
    span = (f"стр. {REVISION_FIRST_PAGE}" if page_to <= REVISION_FIRST_PAGE
            else f"стр. {REVISION_FIRST_PAGE}–{page_to}")
    caption = (f"{user['name']}, {SHORT_TASKS['r'].lower()}"
               + (" +" if credited else "")
               + f" (запись{' ' + _mmss(sec) if sec else ''}, {span}).")
    res = await send_voice_bytes(group["chat_id"], ogg, caption=caption)
    if not (res and res.get("ok")):
        return {"ok": False, "error": "send_failed"}
    voice_obj = res["result"].get("voice") or {}
    duration = voice_obj.get("duration") or sec or None
    rec_id = save_revision_recording(
        user["id"], group["id"], group["chat_id"], res["result"]["message_id"], get_date(),
        voice_obj.get("file_id"), duration, page_to)
    if credited:
        save_report(user["id"], group["id"], get_date(), {"r": True})
    return {"ok": True, "credited": credited, "id": rec_id, "page_to": page_to}


def _mmss(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


# 40 МБ (16.09.2026): предел записи поднят до двух часов - это ~29 МБ при
# нашем битрейте. Потолок Telegram для файла от бота - 50 МБ.
HIFZ_MAX_UPLOAD_BYTES = 40 * 1024 * 1024
# 60 секунд не хватало (замерено на сервере 06.09.2026): полная перекодировка
# 30-минутной записи занимает 58.3 сек - впритык. Это путь Safari/iOS, где
# вход mp4/aac и перекодировка неизбежна. Chrome-путь теперь идёт
# перепаковкой за ~3 сек (см. transcode_to_ogg).
# 600 сек (16.09.2026): путь Safari/iOS перекодирует целиком, 30 минут занимали
# 58 сек - двухчасовая запись укладывается в ~4 минуты, но впритык к 180.
_FFMPEG_TIMEOUT = 600


async def transcode_to_ogg(audio_bytes):
    """Запись из браузера -> ogg/opus, единственный формат, который Telegram
    принимает в sendVoice. Браузеры дают РАЗНОЕ: Chrome/Android - webm/opus,
    Safari/iOS - mp4/aac, поэтому формат входа не фиксируем (ffmpeg
    определяет сам по содержимому), фиксируем только выход.

    Возвращает None, если ffmpeg недоступен или запись битая - вызывающий
    код тогда отвечает студенту ошибкой, а не шлёт в группу мусор."""
    # Chrome/Android пишет УЖЕ в opus - его достаточно переложить в ogg, не
    # трогая звук. Это ~3 сек на 30 минут против 58 сек полной перекодировки
    # (замерено на сервере 06.09.2026), то есть разница между "работает" и
    # "падает по таймауту". Safari/iOS даёт mp4/aac - там copy не сработает,
    # и мы честно перекодируем вторым заходом.
    out = await _run_ffmpeg(["-c:a", "copy"], audio_bytes)
    if out:
        return out
    return await _run_ffmpeg(
        ["-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-ar", "48000"], audio_bytes)


async def _run_ffmpeg(codec_args, audio_bytes):
    """Один прогон ffmpeg с заданными аргументами кодека. None - не вышло
    (вызывающий решает, пробовать ли иначе)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0", *codec_args, "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError) as e:
        log.error("ffmpeg недоступен: %s: %s", type(e).__name__, e)
        return None
    try:
        out, err = await asyncio.wait_for(proc.communicate(audio_bytes), timeout=_FFMPEG_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        log.error("ffmpeg не уложился в %s сек (%s)", _FFMPEG_TIMEOUT, codec_args)
        return None
    if proc.returncode != 0 or not out:
        log.info("ffmpeg %s вернул %s: %s", codec_args, proc.returncode, (err or b"")[:200])
        return None
    return out


def _hifz_place(page, line, stage, page_lines=15):
    """Что именно читал студент - подпись под картинкой строки. Этап решает
    единицу сдачи: 1 - строчка, 2 - половина листа, 3 - вся страница.

    page_lines приходит с фронтенда: строк на листе не всегда 15 (страницы
    с названием суры/басмалой короче), а граница половины должна совпасть
    с той, по которой подсвечивает сам мусхаф (hifzHalf в index.html:
    line < floor(n/2) - верхняя половина)."""
    if stage == 1:
        return f"стр. {page}, строка {line + 1}"
    if stage == 2:
        half = "верхняя" if line < page_lines // 2 else "нижняя"
        return f"стр. {page}, {half} половина"
    return f"стр. {page}, вся страница"


async def submit_hifz_recording(user_id, audio_bytes, image_bytes, page, line, stage, page_lines=15,
                                client_ms=None):
    """Сдача 40+40, записанная прямо в YassirApp (02.09.2026).

    Идёт тем же путём, что обычная голосовая сдача в группе: аудио уходит
    в группу голосовым сообщением, запись кладётся в voice_submissions -
    значит устаз принимает её ПРИВЫЧНЫМ реплаем (core/handlers.py уже
    зовёт mark_voice_reviewed на любой реплай устаза), отдельному кабинету
    учиться не нужно. Перед голосовым уходит картинка со строчкой,
    которую студент читал - без неё устазу не видно, что именно проверять
    (решение пользователя: "аудио в группу с указанием студента + маленький
    скриншот этого текста").

    Дневное задание "m" засчитывается один раз в день (как у обычной
    сдачи), но САМА запись уходит в группу каждый раз - каждая сдача это
    отдельный материал для устаза, а не повторный тап по кнопке.

    Возвращает dict со статусом - фронтенду нужно отличать "нет группы"
    от "не смогли сконвертировать"."""
    group = get_learning_group(user_id, include_prep=True)
    if not group or not group["chat_id"]:
        return {"ok": False, "error": "no_group"}
    if "m" not in get_group_tasks(group):
        return {"ok": False, "error": "task_off"}
    user = find_user_by_phone(user_id)
    if not user:
        return {"ok": False, "error": "no_user"}

    # Гейт пересдачи. 13.09.2026, решение пользователя: стена переехала с
    # ОТПРАВКИ на ПРОДВИЖЕНИЕ. Долг больше не запирает всё подряд - этап, в
    # котором студент стоит, он доделывает и сдаёт ("внутри первого этапа 7
    # или 8 строк сдаёшь, даже если долги не закрыты"). Закрыт вход в
    # СЛЕДУЮЩИЙ этап, и держит его handle_hifz_set, куда пишется указатель.
    #
    # Здесь остаётся страховка на случай устаревшей страницы: принимаем
    # только то, что стоит на указателе (та же страница и тот же этап; строка
    # внутри этапа гуляет - hifzSave мог не долететь), либо сам долг.
    # Пересдать долг можно всегда, для того стена и стоит.
    #
    # Проверяем ЗДЕСЬ, а не только в интерфейсе: локальное состояние можно
    # перезагрузить, сдачу - нет.
    retakes = get_open_retakes(user["id"], group["id"])
    if retakes:
        pointer = get_hifz_pointer(user_id) or {}
        on_pointer = (pointer.get("page"), pointer.get("stage")) == (page, stage)
        is_retake = any((r["hifz_page"], r["hifz_line"], r["hifz_stage"])
                        == (page, line, stage) for r in retakes)
        if not (on_pointer or is_retake):
            first = retakes[0]
            return {
                "ok": False, "error": "retake_pending",
                "place": _hifz_place(first["hifz_page"], first["hifz_line"],
                                     first["hifz_stage"], page_lines),
                "retake": {"page": first["hifz_page"], "line": first["hifz_line"],
                           "stage": first["hifz_stage"]},
            }

    ogg = await transcode_to_ogg(audio_bytes)
    if not ogg:
        return {"ok": False, "error": "bad_audio"}

    place = _hifz_place(page, line, stage, page_lines)
    photo_msg_id = None
    if image_bytes:
        res = await send_photo_bytes(
            group["chat_id"], image_bytes, "hifz.png",
            caption=f"{user['name']} — {place}"
        )
        if res and res.get("ok"):
            photo_msg_id = res["result"]["message_id"]

    already = get_today_report(user["id"], group["id"]) or {}
    credited = not already.get("m")
    caption = f"{user['name']}, {SHORT_TASKS['m'].lower()} + (через YassirApp, 40+40)."
    if not credited:
        # Задание уже засчитано сегодня - "+" в подписи означал бы второй
        # зачёт, которого нет. Устазу запись всё равно нужна: он слушает
        # каждую сдачу, а не только первую за день.
        caption = f"{user['name']}, {place} (через YassirApp, 40+40)."
    res = await send_voice_bytes(
        group["chat_id"], ogg, caption=caption, reply_to_message_id=photo_msg_id
    )
    if not (res and res.get("ok")):
        return {"ok": False, "error": "send_failed"}

    voice_msg_id = res["result"]["message_id"]
    voice_obj = res["result"].get("voice") or {}
    file_id = voice_obj.get("file_id")
    # Длину записи Telegram считает сам при приёме файла (14.09.2026), но для
    # части браузерных файлов отдаёт 0 (16.09.2026: 36 нулей из 475 сдач за
    # три дня, все - из приложения). Приложение свою длину знает точно
    # (таймер записи, client_ms) - она и подстраховывает ноль Telegram.
    duration = voice_obj.get("duration")
    if not duration and client_ms:
        duration = round(client_ms / 1000)
    # Место сдачи кладём в саму запись (04.09.2026): кабинету устаза нужно
    # показать, ЧТО именно проверять, а из подписи в Telegram это не достать.
    save_voice_submission(user["id"], group["id"], group["chat_id"],
                          voice_msg_id, get_date(), file_id,
                          hifz_page=page, hifz_line=line, hifz_stage=stage,
                          photo_message_id=photo_msg_id, duration=duration)
    if credited:
        save_report(user["id"], group["id"], get_date(), {"m": True})
    return {"ok": True, "credited": credited, "place": place}


async def _notify_student(sub, text):
    """Извещение о вердикте идёт И в группу реплаем на саму сдачу, И в личку
    (решение пользователя 04.09.2026). В группе - потому что там вся жизнь
    сдачи и видно, что работа идёт; в личку - потому что в группе сообщение
    легко пролистать. Личка только тем, кто открывал бота (get_dm_ok):
    иначе Telegram вернёт ошибку, а студент всё равно ничего не получит."""
    await send_message(sub["group_chat_id"], text,
                       reply_to_message_id=sub["message_id"])
    if get_dm_ok(sub["student_id"]):
        await send_message(sub["student_phone"], text)


async def submit_ustaz_verdict(ustaz_id, submission_id, verdict, words=None):
    """Вердикт устаза по сдаче. Права проверяет вызывающий (кабинет знает
    группы устаза), здесь - сама запись и извещение студента."""
    sub = get_submission(submission_id)
    if not sub:
        return {"ok": False, "error": "not_found"}
    if verdict not in (VERDICT_ACCEPTED, VERDICT_RETAKE):
        return {"ok": False, "error": "bad_verdict"}

    # На пересдачу - только с голосовым разбором (07.09.2026, решение
    # пользователя). Вернуть работу, не сказав почему, значит оставить
    # студента в тупике: он знает, что не принято, и не знает, что править.
    # Пометки слов остаются делом добровольным - они дополняют голос, а не
    # заменяют его.
    #
    # Проверяем ЗДЕСЬ, а не только в кнопке: интерфейс можно открыть старой
    # версией страницы, а правило должно держаться в одном месте. Голосовой
    # реплай в группе тоже засчитывается - он пишется в ту же колонку.
    if verdict == VERDICT_RETAKE and not sub["review_file_id"]:
        return {"ok": False, "error": "needs_comment"}

    # Студент уже пересдал - эта запись отработана (07.09.2026). Повторный
    # вердикт по ней заново закрыл бы гейт перед тем, кто на замечание уже
    # ответил (см. is_retake_answered). Разбирать надо новую запись.
    if is_retake_answered(sub):
        return {"ok": False, "error": "already_redone"}

    set_submission_verdict(submission_id, verdict, ustaz_id, words)
    place = _hifz_place(sub["hifz_page"], sub["hifz_line"] or 0, sub["hifz_stage"] or 1) \
        if sub["hifz_page"] is not None else ""
    marked = len(words or [])
    if verdict == VERDICT_ACCEPTED:
        text = f"{sub['student_name']}, принято ✅"
        if place:
            text += f" — {place}"
    else:
        text = f"{sub['student_name']}, нужно пересдать"
        if place:
            text += f" — {place}"
        if marked:
            text += f"\nОтмечено слов: {marked} — они подсвечены в приложении"
        text += "\nПослушай замечание устаза и начитай заново 🤲"
    await _notify_student(sub, text)
    return {"ok": True, "verdict": verdict, "place": place}


async def send_ustaz_comment(ustaz_id, submission_id, audio_bytes):
    """Голосовое замечание, записанное ПРЯМО В КАБИНЕТЕ (04.09.2026). Уходит
    реплаем на сдачу в группу - привычный путь не расходится с новым, устаз в
    группе видит то же, что и раньше, - и сохраняется в самой сдаче, чтобы
    студент слушал его в приложении.

    Доступно и при "принято" (уточнение пользователя): похвала и уточнение
    тоже нужны, вердикт этому не мешает."""
    sub = get_submission(submission_id)
    if not sub:
        return {"ok": False, "error": "not_found"}
    # То же правило, что у вердикта: новое замечание на уже пересданную
    # работу переписало бы то, которое студент послушал и по которому
    # начитал заново.
    if is_retake_answered(sub):
        return {"ok": False, "error": "already_redone"}
    ogg = await transcode_to_ogg(audio_bytes)
    if not ogg:
        return {"ok": False, "error": "bad_audio"}
    res = await send_voice_bytes(
        sub["group_chat_id"], ogg,
        caption=f"Замечание устаза — {sub['student_name']}",
        reply_to_message_id=sub["message_id"]
    )
    if not (res and res.get("ok")):
        return {"ok": False, "error": "send_failed"}
    file_id = (res["result"].get("voice") or {}).get("file_id")
    # Пишем разбор в САМУ сдачу (по её message_id), а не в новое сообщение -
    # студент открывает сдачу и слышит замечание рядом с ней.
    save_submission_review(sub["chat_id"], sub["message_id"], "voice",
                           review_file_id=file_id, review_by=ustaz_id, overwrite=True)
    return {"ok": True}


def _leaderboard_for_this_bot():
    """core/mufradat.py:get_leaderboard читает ОБЩУЮ sources/hadiths.db -
    мужской и женский бот пишут в один файл, движок намеренно не знает о
    поле (разделение полов - забота Telegram-обвязки, не движка). Рейтинг
    ВСЕГДА раздельный по полу, никогда не смешивается (жёсткое правило
    пользователя 17.08.2026, найдено advisor'ом как утечка "Студент XXXX
    (—)" из другого бота). Фильтруем по тому, существует ли студент в БД
    ИМЕННО ЭТОГО бота (users - per-profile, quran_male.db/quran_female.db,
    см. config.DB) - явного поля "пол" в mufradat_* таблицах нет и не
    нужно, разделение уже есть на уровне БД пользователей.

    Плоский, отсортированный, БЕЗ разбивки на дивизионы (см. _split_by_division
    ниже) - движок (core/mufradat.py) остаётся дивизион-слепым, разбивка
    только в этой Telegram-обвязке. Порядок важен: гендерный фильтр здесь
    выполняется ДО разбивки на дивизионы - если бы разбивали раньше,
    фильтр пришлось бы дублировать в обоих дивизионах (advisor 18.08.2026,
    четвёртый заход).

    ВКЛЮЧАЕТ студентов без группы (find_user_by_phone требует только
    запись в users, не членство в группе) - это НЕ то же самое, что
    ПУБЛИЧНЫЙ групповой рейтинг (см. _group_leaderboard_for_this_bot) -
    тренажёр группу не проверяет, кто-то тренируется, ни разу не вступив
    в группу. Список нужен как есть (гендер-фильтр, группа не важна) для
    личной статистики таких студентов (handle_leaderboard в
    core/mufradat_api.py, ветка in_group=False) - решение пользователя
    18.08.2026, пятый заход: "пусть тренируется, нет ничего плохого... в
    рейтинг не включать, но ему лично рейтинг отправлять... и показывать
    его место" - место среди ВСЕХ тренирующихся этого бота, не только
    группы."""
    return [(uid, score) for uid, score in get_leaderboard() if find_user_by_phone(uid)]


def _group_leaderboard_for_this_bot():
    """ПУБЛИЧНЫЙ групповой рейтинг (то, что видят все в приложении) - сужает
    _leaderboard_for_this_bot до студентов, состоящих хоть в какой-то
    группе (get_learning_group). Студент без группы тренируется наравне
    со всеми (см. _leaderboard_for_this_bot), но сравнивать его с группой
    в общем топе не имеет смысла - решение пользователя 18.08.2026."""
    return [(uid, score) for uid, score in _leaderboard_for_this_bot() if get_learning_group(uid)]


# Порог дивизиона - решение пользователя 18.08.2026, четвёртый заход про
# рейтинг за один день: "они на той странице где учат Коран, кто-то раньше
# начал, поэтому больше страниц" - группировка по РЕАЛЬНОМУ прогрессу
# заучивания, не про честность вычислений (та уже решена depth-множителем
# в самой формуле сортировки, см. core/mufradat.py:get_leaderboard).
# Порог 10 - предложение пользователя, проверено на живых данных: 8
# студентов на <=10, 7 на >10 - почти ровный сплит (не пирамида "3-10
# большинство", как предполагал пользователь, но для двух дивизионов
# ровный сплит даже лучше).
_DIVISION_THRESHOLD = 10
_DIVISION_LABELS = ("🥇 Дивизион 1 (стр. 11+)", "🥈 Дивизион 2 (стр. 2-10)")


def _split_by_division(leaderboard):
    """leaderboard - уже отсортированный ПЛОСКИЙ список (_leaderboard_for_this_bot).
    Разбивка чисто на уровне отображения - каждый дивизион сохраняет
    относительный порядок (уже отсортирован по единой формуле, глубина
    внутри дивизиона ПРОДОЛЖАЕТ работать - Дивизион 1 охватывает стр.11-221,
    это 20-кратный разброс размера пула, без depth-множителя внутри самого
    дивизиона повторилась бы та же проблема Муслим/Сатар, только на его
    масштабе, advisor 18.08.2026). Возвращает [(label, entries), ...]."""
    div1 = [(uid, score) for uid, score in leaderboard if score["page"] > _DIVISION_THRESHOLD]
    div2 = [(uid, score) for uid, score in leaderboard if score["page"] <= _DIVISION_THRESHOLD]
    return list(zip(_DIVISION_LABELS, (div1, div2)))


def _find_rank(divisions, user_id):
    for label, entries in divisions:
        for i, (uid, score) in enumerate(entries, start=1):
            if uid == user_id:
                return label, i, len(entries), score
    return None


def _display_name(user_id):
    user = find_user_by_phone(user_id)
    return user["name"] if user else f"Студент {user_id[-4:]}"


def _group_name(user_id):
    group = get_learning_group(user_id)
    return group["title"] if group and group["title"] else "—"
