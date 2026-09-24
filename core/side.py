"""Брат или сестра - вопрос тому, чью половину бот не знает (20.09.2026).

Откуда взялось. 19.09 Бурулсун пришла с сайта в мужского бота (кнопка на
сайте одна и ведёт в мужской), тот не нашёл её ни у себя, ни у соседа и
как любому незнакомцу дал ссылку на СВОЮ подготовительную - мужскую.
Новичка бот отличить не может ни по имени, ни по базам; единственный, кто
знает половину, - сам человек. Решение пользователя: первым вопросом
незнакомцу - «ты брат или сестра», и оттуда вести в правильную сторону.

Когда половина известна и без вопроса:
  - человек ответил раньше (общая таблица user_side, один ответ на оба бота);
  - хоть раз был студентом pro/relaxed этой базы - его пропустил устаз;
  - хоть раз был студентом pro/relaxed у соседа - то же, но там.
Подготовительная в обе стороны НЕ считается: запись туда никто не
проверял, Бурулсун сутки числилась активной студенткой мужской prep.

Куда вести. Своей половине - ссылка на свою подготовительную, как раньше.
Другой половине - ссылка на ЛИЧКУ бота соседа, не на его группу (решение
пользователя 20.09): ссылку на группу выдаёт только свой бот и только в
личке, а ссылка на бота безопасна даже нажатой по ошибке - сосед развернёт
чужого обратно. Перед этим, если человек по ошибке уже записан в НАШУ
подготовительную, снимаем его у себя (иначе сосед увидит его активным у
нас и отправит назад - пинг-понг, найден 20.09 до выкладки).

Где спрашиваем: холодная личка, отказ после входа с сайта, рассылка
«вернись» тем, чья половина неизвестна, и заявка в подготовительную.

Вход в подготовительную - только через бота (23.09.2026, решение
пользователя). Ссылка на неё - с заявкой: неизвестного бот не впускает, а
спрашивает в личке (пересланная ссылка, случай Каната 20.09). Кнопки «мне
не сюда» в группе больше нет: ошибся уже внутри - поправляет устаз
реплаем (/сестра, /брат, /нетуда), это единственная правка в группе.
"""
import logging

import config
from core.bots import _connect, other_bot, other_profile, JAMAAT_IN
from core.db import (
    get_now, get_prep_group, ever_learning_student, other_bot_known,
    deactivate_student, get_groups_by_type, find_by_phone,
    get_dm_ok_by_phone, remove_unregistered, other_bot_member, other_bot_prep_only,
    get_prep_students_active, get_group, is_any_group_admin,
)
from config import SUPER_ADMIN_IDS
from core.i18n import T
from core.tg import (send_message, send_message_with_buttons, ban_member, unban_member, get_dm_start_link,
                     approve_join_request, decline_join_request)

log = logging.getLogger(__name__)

SIDES = ("male", "female")

# Как назвать половину в приветствии подготовительной: «группа братьев».
HALF_OF = {"male": "братьев", "female": "сестёр"}


def half_word():
    return HALF_OF.get(config.PROFILE, "братьев")


def answered_side(uid):
    """Что человек ответил сам, любому из ботов. None - не отвечал."""
    try:
        with _connect() as c:
            row = c.execute("SELECT side FROM user_side WHERE user_id=?", (str(uid),)).fetchone()
    except Exception as e:
        log.error("user_side: не прочитался (%s)", e)
        return None
    return row["side"] if row and row["side"] in SIDES else None


def remember_side(uid, side):
    if side not in SIDES:
        return
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO user_side(user_id, side, answered_at, via_profile) VALUES(?,?,?,?)"
                " ON CONFLICT(user_id) DO UPDATE SET side=excluded.side,"
                " answered_at=excluded.answered_at, via_profile=excluded.via_profile",
                (str(uid), side, get_now().strftime("%Y-%m-%d %H:%M:%S"), config.PROFILE),
            )
    except Exception as e:
        log.error("user_side: не записался (%s)", e)


def known_side(uid):
    """'male' / 'female' / None. Порядок: свой ответ человека, потом
    устаз этой базы, потом устаз соседа."""
    side = answered_side(uid)
    if side:
        return side
    if ever_learning_student(uid):
        return config.PROFILE
    if other_bot_known(uid):
        return other_profile()
    return None


def claimed_by_neighbour(uid):
    """Считать ли человека человеком СОСЕДА на всех дверях (личка, сайт,
    группы): учится/устаз там (other_bot_member) или проходил через его
    устаза (other_bot_known). Исключение (20.09.2026, зеркало Бурулсун): у
    соседа только подготовительная - никем не проверенная запись, - а сам
    человек ответил НАШУ половину. Тогда он наш: разворачивать его назад
    было бы пинг-понгом, а снять его у соседа может только сосед (см.
    sweep_misplaced_in_prep)."""
    if not (other_bot_member(uid) or other_bot_known(uid)):
        return False
    if other_bot_prep_only(uid) and answered_side(uid) == config.PROFILE:
        return False
    return True


async def sweep_misplaced_in_prep():
    """Уборщик (дважды в день вместе с check_prep_students): снять из НАШЕЙ
    подготовительной тех, кто любому боту ответил другую половину. Ответ
    общий (user_side), а базу правит только её хозяин - так ответ, данный
    где угодно, за полдня чинит обе базы."""
    for s in get_prep_students_active():
        uid = s["phone"]
        if not uid:
            continue
        side = answered_side(uid)
        if side is None or side == config.PROFILE:
            continue
        await _leave_own_prep(uid)
        await send_to_neighbour(uid)
        log.info("side sweep: %s снят с подготовительной - ответил другую половину", uid)


def invite_buttons():
    return [("Ссылка для брата", "inv:male"), ("Ссылка для сестры", "inv:female")]


async def send_invite_menu(chat_id, lang="ru"):
    # Есть общий бот (22.09.2026) - ссылка одна, выбирать «брату/сестре»
    # незачем: @YassirAppBot спросит новичка сам.
    from core.bots import app_invite_link
    link = app_invite_link()
    if link:
        await send_message(chat_id, T("invite_forward_one", lang, link=link))
        return
    await send_message_with_buttons(chat_id, T("invite_menu", lang), invite_buttons())


async def handle_invite_pick(uid, side, lang="ru"):
    """Тап «ссылка для брата/сестры»: текст для пересылки со ссылкой на
    ЛИЧКУ нужного бота (20.09.2026, решение пользователя: в рассылке
    ссылок нет, их берут здесь). Ссылка на бота безопасна в пересылке -
    незнакомца там спросят половину, чужого развернут."""
    if side not in SIDES:
        return
    # Кнопки в уже разосланных сообщениях (24.09.2026) тоже ведут в одну
    # дверь @YassirAppBot, как и настройки.
    from core.bots import app_invite_link
    one = app_invite_link()
    if one:
        await send_message(uid, T("invite_forward_one", lang, link=one))
        return
    if side == config.PROFILE:
        link = await get_dm_start_link()
    else:
        other = other_bot()
        link = other["start_link"] if other else None
    if not link:
        await send_message(uid, T("invite_no_link", lang))
        return
    who = "брата" if side == "male" else "сестры"
    await send_message(uid, T("invite_forward_text", lang, who=who, link=link))


def side_buttons(uid):
    return [("Я брат", "side:male:" + str(uid)), ("Я сестра", "side:female:" + str(uid))]


def own_prep_link():
    prep = get_prep_group()
    return prep["invite_link"] if prep and prep["invite_link"] else ""


async def offer_way_in(chat_id, uid, lang="ru"):
    """Незнакомцу в личке: если половина известна - сразу дорога, иначе
    вопрос. Строку users у себя не заводит (ответ живёт в общей базе)."""
    side = known_side(uid)
    if side == config.PROFILE:
        await send_message(chat_id, T("dm_cold_message_explain", lang, link=own_prep_link()))
    elif side:
        await send_to_neighbour(chat_id, lang)
    else:
        await send_message_with_buttons(chat_id, T("side_question", lang), side_buttons(uid))


async def send_to_neighbour(chat_id, lang="ru"):
    other = other_bot()
    if other:
        return await send_message(chat_id, T("side_other_link", lang, jamaat=other["jamaat"], link=other["start_link"]))
    return await send_message(chat_id, T("side_other_nolink", lang, jamaat=JAMAAT_IN[other_profile()]))


async def _leave_own_prep(uid):
    """Человек по ошибке уже записан активным в НАШУ подготовительную
    (Бурулсун 19.09): снимаем у себя и убираем из чата, иначе сосед увидит
    его активным здесь и отправит назад."""
    for prep in get_groups_by_type("prep"):
        s = find_by_phone(uid, prep["id"])
        if not s:
            continue
        deactivate_student(s["id"], prep["id"])
        try:
            await ban_member(prep["chat_id"], uid)
            await unban_member(prep["chat_id"], uid)
        except Exception as e:
            log.error("side: не убрал %s из подготовительной %s: %s", uid, prep["chat_id"], e)
        log.info("side: %s снят с нашей подготовительной %s - половина другая", uid, prep["id"])


# Слова устаза в реплае → половина. `/сестра` и `/брат` называют, кого
# устаз видит (в тоне проекта: не «ты ошибся», а «это сестра»); `/нетуда` -
# просто «другая половина». Своя половина - подтверждение, чужая - снятие.
USTAZ_SIDE_WORDS = {"/сестра": "female", "/брат": "male", "/нетуда": None, "/notme": None}


async def mark_side_by_ustaz(chat_id, group_info, uid, word, lang="ru"):
    """Устаз реплаем отметил половину человека (20.09.2026, решение
    пользователя). Возвращает текст подтверждения устазу."""
    target = USTAZ_SIDE_WORDS.get(word)
    if target is None:
        target = other_profile()
    if target == config.PROFILE:
        remember_side(uid, target)
        s = find_by_phone(uid, group_info["id"])
        who = (s["name"] if s and s["name"] else "id " + str(uid))
        log.info("side: %s подтверждён устазом как свой в %s", uid, chat_id)
        return "✅ Принято: " + who + " — " + ("брат" if target == "male" else "сестра") + ", половина своя."
    return await mark_not_here(chat_id, group_info, uid, lang)


async def mark_not_here(chat_id, group_info, uid, lang="ru"):
    """Устаз отметил, что человек с другой половины. Запоминаем половину
    как другую, снимаем из этой группы и из наших подготовительных,
    убираем из чата. Личка открыта - мягко пишем туда дорогу к боту
    соседа; закрыта - не пишем никуда: после кика чат человеку недоступен,
    строка в группе бессмысленна. Возвращает текст подтверждения устазу."""
    other = other_profile()
    remember_side(uid, other)
    s = find_by_phone(uid, group_info["id"])
    if s:
        deactivate_student(s["id"], group_info["id"])
    await _leave_own_prep(uid)
    remove_unregistered(uid, chat_id)
    try:
        await ban_member(chat_id, uid)
        await unban_member(chat_id, uid)
    except Exception as e:
        log.error("side: не убрал %s из %s по отметке устаза: %s", uid, chat_id, e)
    who = (s["name"] if s and s["name"] else "id " + str(uid))
    jamaat = JAMAAT_IN[other]
    told = False
    if get_dm_ok_by_phone(uid):
        ob = other_bot()
        if ob:
            resp = await send_message(uid, T("side_moved_by_ustaz", lang, jamaat=jamaat, link=ob["start_link"]))
        else:
            resp = await send_message(uid, T("side_moved_by_ustaz_nolink", lang, jamaat=jamaat))
        told = bool(resp and resp.get("ok"))
    title = group_info["title"] or str(chat_id)
    for ap in SUPER_ADMIN_IDS:
        await send_message(ap, "⚠️ Устаз отметил в «" + title + "»: " + who + " (id " + str(uid)
                           + ") - половина другая (" + jamaat + " джамаат). Снят из группы"
                           + (", дорога к своему боту ушла в личку." if told else ", личка закрыта - написать не смог."))
    log.info("side: %s отмечен устазом как чужой в %s (told=%s)", uid, chat_id, told)
    return ("✅ " + who + " снят: половина другая. "
            + ("Написал в личку, куда идти." if told else "Личка у меня с ним закрыта — сказать не смог, подскажите сами."))


async def _answer_join_requests(uid, approve):
    """Заявки человека в наши подготовительные: принять или отклонить. Нет
    заявки - Telegram отвечает ошибкой, это не беда. True - хоть одну приняли."""
    done = False
    for prep in get_groups_by_type("prep"):
        call = approve_join_request if approve else decline_join_request
        resp = await call(prep["chat_id"], uid)
        if resp and resp.get("ok"):
            done = True
            log.info("side: заявка %s в %s %s", uid, prep["chat_id"], "принята" if approve else "отклонена")
    return done


async def handle_side_answer(uid, side, lang="ru"):
    """Тап по кнопке в личке. uid уже сверен с нажавшим в bot.py. Висит
    заявка в подготовительную - своя половина входит сразу, чужая получает
    отказ и дорогу к соседу."""
    if side not in SIDES:
        return
    remember_side(uid, side)
    if side == config.PROFILE:
        if await _answer_join_requests(uid, approve=True):
            await send_message(uid, T("join_request_approved", lang))
            return
        link = own_prep_link()
        if link:
            await send_message(uid, T("side_own_link", lang, link=link))
        else:
            log.error("side: у подготовительной нет invite_link, дорогу дать нечем")
        return
    await _answer_join_requests(uid, approve=False)
    await _leave_own_prep(uid)
    await send_to_neighbour(uid, lang)


async def handle_join_request(chat_id, uid, name="", lang="ru"):
    """Заявка на вступление (23.09.2026). Решает бот и сразу: ждать
    человека никто не заставляет. Касается только подготовительной -
    заявки в другие группы оставляем людям, как было.

    Свой (ответил боту / учился у нас) - впускаем. Чужой - отказ и дорога к
    соседу. Неизвестный - вопрос в личку: Telegram разрешает написать тому,
    кто подал заявку, даже если он бота не запускал. Не дошло - говорим
    суперадминам, заявку можно принять руками."""
    group = get_group(chat_id)
    if not group or (group["group_type"] or "") != "prep":
        return
    uid = str(uid)
    if uid in SUPER_ADMIN_IDS or is_any_group_admin(uid):
        await approve_join_request(chat_id, uid)
        return
    side = known_side(uid)
    if side == config.PROFILE:
        resp = await approve_join_request(chat_id, uid)
        if not (resp and resp.get("ok")):
            await _tell_admins("⚠️ Не смог впустить " + (name or "") + " (id " + uid
                               + ") в подготовительную по заявке: " + str(resp and resp.get("description"))
                               + ". Примите заявку вручную.")
        log.info("side: заявка %s в %s - своя половина, %s", uid, chat_id,
                 "принята" if resp and resp.get("ok") else "НЕ принята")
        return
    if side:
        await decline_join_request(chat_id, uid)
        await send_to_neighbour(uid, lang)
        log.info("side: заявка %s в %s - другая половина, отказ и дорога к соседу", uid, chat_id)
        return
    resp = await send_message_with_buttons(uid, T("join_request_question", lang), side_buttons(uid))
    if not (resp and resp.get("ok")):
        await _tell_admins("⚠️ " + (name or "Кто-то") + " (id " + uid + ") подал заявку в подготовительную, "
                           "а написать ему я не смог. Если это свой - примите заявку вручную.")
    log.info("side: заявка %s в %s - половина неизвестна, вопрос в личку (%s)", uid, chat_id,
             "ушёл" if resp and resp.get("ok") else "НЕ дошёл")


async def _tell_admins(text):
    for ap in SUPER_ADMIN_IDS:
        await send_message(ap, text)
