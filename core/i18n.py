import random
import re

from config import IS_FEMALE

LANG_NAMES = {
    "ru": "Russian",
    "ky": "Kyrgyz",
    "uz": "Uzbek",
    "kk": "Kazakh",
    "tr": "Turkish",
    "ar": "Arabic",
    "en": "English",
    "zh": "Chinese",
}

TR = {
    "present": {
        "ru": "📡 {name} присутствует! +5 баллов ✅",
        "ky": "📡 {name} катышып жатат! +5 упай ✅",
        "uz": "📡 {name} qatnashyapti! +5 ball ✅",
        "kk": "📡 {name} қатысып жатыр! +5 ұпай ✅",
        "tr": "📡 {name} katılıyor! +5 puan ✅",
        "ar": "📡 {name} حاضر! +5 نقاط ✅",
        "en": "📡 {name} is present! +5 points ✅",
        "zh": "📡 {name} 已出席！+5 分 ✅",
    },
    "lesson_marked": {
        "ru": "✅ Урок отмечен как проведённый",
        "ky": "✅ Сабак өтүлгөн деп белгиленди",
        "uz": "✅ Dars o'tkazilgan deb belgilandi",
        "kk": "✅ Сабақ өтті деп белгіленді",
        "tr": "✅ Ders yapıldı olarak işaretlendi",
        "ar": "✅ تم تسجيل أن الدرس قد أُقيم",
        "en": "✅ Lesson marked as held",
        "zh": "✅ 课程已标记为已进行",
    },
    "ask_words": {
        "ru": "🤖 {name}, напиши словами что именно ты сдал 📝\n\nНапример: «повторение, слова»\n\nЗадания группы:\n{legend}",
        "ky": "🤖 {name}, эмнени тапшырганыңды сөз менен жаз 📝\n\nМисалы: «кайталоо, сөздөр»\n\nТоптун тапшырмалары:\n{legend}",
        "uz": "🤖 {name}, nimani topshirganingni so'z bilan yoz 📝\n\nMasalan: «takror, so'zlar»\n\nGuruh vazifalari:\n{legend}",
        "kk": "🤖 {name}, нені тапсырғаныңды сөзбен жаз 📝\n\nМысалы: «қайталау, сөздер»\n\nТоп тапсырмалары:\n{legend}",
        "tr": "🤖 {name}, neyi teslim ettiğini kelimelerle yaz 📝\n\nÖrnek: «tekrar, kelimeler»\n\nGrup görevleri:\n{legend}",
        "ar": "🤖 {name}، اكتب بالكلمات ما الذي سلّمته 📝\n\nمثال: «مراجعة، كلمات»\n\nمهام المجموعة:\n{legend}",
        "en": "🤖 {name}, write in words what you submitted 📝\n\nExample: «review, words»\n\nGroup tasks:\n{legend}",
        "zh": "🤖 {name}，请用文字写明你完成了什么 📝\n\n例如：「复习、单词」\n\n小组任务：\n{legend}",
    },
    "not_understood": {
        "ru": "🤖 {name}, не понял что ты сдал 🤔\nНапиши задание словами 📝\n\nНапример: «повторение», «слова»\n\nЗадания группы:\n{legend}",
        "ky": "🤖 {name}, эмнени тапшырганыңды түшүнбөдүм 🤔\nТапшырманы сөз менен жаз 📝\n\nМисалы: «кайталоо», «сөздөр»\n\nТоптун тапшырмалары:\n{legend}",
        "uz": "🤖 {name}, nimani topshirganingni tushunmadim 🤔\nVazifani so'z bilan yoz 📝\n\nMasalan: «takror», «so'zlar»\n\nGuruh vazifalari:\n{legend}",
        "kk": "🤖 {name}, нені тапсырғаныңды түсінбедім 🤔\nТапсырманы сөзбен жаз 📝\n\nМысалы: «қайталау», «сөздер»\n\nТоп тапсырмалары:\n{legend}",
        "tr": "🤖 {name}, neyi teslim ettiğini anlamadım 🤔\nGörevi kelimelerle yaz 📝\n\nÖrnek: «tekrar», «kelimeler»\n\nGrup görevleri:\n{legend}",
        "ar": "🤖 {name}، لم أفهم ما الذي سلّمته 🤔\nاكتب المهمة بالكلمات 📝\n\nمثال: «مراجعة»، «كلمات»\n\nمهام المجموعة:\n{legend}",
        "en": "🤖 {name}, I didn't understand what you submitted 🤔\nWrite the task in words 📝\n\nExample: «review», «words»\n\nGroup tasks:\n{legend}",
        "zh": "🤖 {name}，我没明白你完成了什么 🤔\n请用文字写明任务 📝\n\n例如：「复习」、「单词」\n\n小组任务：\n{legend}",
    },
    "accepted": {
        "ru": "✅ {name}, принято!",
        "ky": "✅ {name}, кабыл алынды!",
        "uz": "✅ {name}, qabul qilindi!",
        "kk": "✅ {name}, қабылданды!",
        "tr": "✅ {name}, kabul edildi!",
        "ar": "✅ {name}، تم القبول!",
        "en": "✅ {name}, accepted!",
        "zh": "✅ {name}，已接收！",
    },
    "counted_today": {
        "ru": "Засчитано сегодня:",
        "ky": "Бүгүн эсептелди:",
        "uz": "Bugun hisoblandi:",
        "kk": "Бүгін есептелді:",
        "tr": "Bugün sayıldı:",
        "ar": "تم الاحتساب اليوم:",
        "en": "Counted today:",
        "zh": "今日已计入：",
    },
    "still_left": {
        "ru": "Ещё осталось сдать:",
        "ky": "Дагы тапшыруу керек:",
        "uz": "Yana topshirish kerak:",
        "kk": "Тағы тапсыру керек:",
        "tr": "Hâlâ teslim edilecek:",
        "ar": "ما زال يجب تسليم:",
        "en": "Still to submit:",
        "zh": "还需提交：",
    },
    "remaining": {
        "ru": "осталось:",
        "ky": "калды:",
        "uz": "qoldi:",
        "kk": "қалды:",
        "tr": "kaldı:",
        "ar": "تبقّى:",
        "en": "left:",
        "zh": "剩余：",
    },
    "all_done": {
        "ru": "🎉 МашаАллах! Все задания на сегодня выполнены!",
        "ky": "🎉 МашаАллах! Бүгүнкү бардык тапшырмалар аткарылды!",
        "uz": "🎉 MashaAlloh! Bugungi barcha vazifalar bajarildi!",
        "kk": "🎉 МашаАллах! Бүгінгі барлық тапсырмалар орындалды!",
        "tr": "🎉 MaşaAllah! Bugünkü tüm görevler tamamlandı!",
        "ar": "🎉 ما شاء الله! تم إنجاز جميع مهام اليوم!",
        "en": "🎉 MashaAllah! All today's tasks are done!",
        "zh": "🎉 MashaAllah！今天所有任务都完成了！",
    },
    "already_all": {
        "ru": "🌟 {name}, ты уже сдал ВСЕ задания сегодня, МашаАллах! Отдыхай, увидимся завтра 🤲",
        "ky": "🌟 {name}, бүгүн БАРДЫК тапшырманы тапшырдың, МашаАллах! Эс ал, эртең көрүшөбүз 🤲",
        "uz": "🌟 {name}, bugun BARCHA vazifani topshirding, MashaAlloh! Dam ol, ertaga ko'rishamiz 🤲",
        "kk": "🌟 {name}, бүгін БАРЛЫҚ тапсырманы тапсырдың, МашаАллах! Демал, ертең кездесеміз 🤲",
        "tr": "🌟 {name}, bugün TÜM görevleri teslim ettin, MaşaAllah! Dinlen, yarın görüşürüz 🤲",
        "ar": "🌟 {name}، لقد سلّمت جميع المهام اليوم، ما شاء الله! ارتح، نراك غداً 🤲",
        "en": "🌟 {name}, you've already submitted ALL tasks today, MashaAllah! Rest, see you tomorrow 🤲",
        "zh": "🌟 {name}，你今天已完成所有任务，MashaAllah！好好休息，明天见 🤲",
    },
    "already_counted": {
        "ru": "✅ {name}, зачёт!",
        "ky": "✅ {name}, зачёт!",
        "uz": "✅ {name}, zacht!",
        "kk": "✅ {name}, зачёт!",
        "tr": "✅ {name}, sayıldı!",
        "ar": "✅ {name}، أحسنت!",
        "en": "✅ {name}, noted!",
        "zh": "✅ {name}，已记录！",
    },
    "all_done_praise": {
        "ru": [
            "🌟 {name}, ты сдал ВСЕ задания сегодня, МашаАллах! Отдыхай, увидимся завтра 🤲",
            "🏆 {name}, все задания выполнены! Аллах да примет твой труд 🤲",
            "⭐ Браво, {name}! Полный день — все задания сданы! 💪",
            "🎉 {name}, МашаАллах! Сегодня ты завершил всё. Так держать! 📖",
            "✨ {name}, отлично! Все задания готовы. Пусть Аллах увеличит твоё знание 🤲",
        ],
        "ky": ["🌟 {name}, бүгүн БААРДЫК тапшырмаларды бүтүрдүң, МашаАллах! 🤲"],
        "uz": ["🌟 {name}, bugun BARCHA vazifalarni bajarding, MashaAlloh! 🤲"],
        "kk": ["🌟 {name}, бүгін БАРЛЫҚ тапсырмаларды орындадың, МашаАллах! 🤲"],
        "tr": ["🌟 {name}, bugün TÜM görevleri tamamladın, MaşaAllah! 🤲"],
        "ar": ["🌟 {name}، أكملت كل المهام اليوم، ما شاء الله! 🤲"],
        "en": ["🌟 {name}, you completed ALL tasks today, MashaAllah! 🤲"],
        "zh": ["🌟 {name}，你今天完成了所有任务，马沙安拉！🤲"],
    },
    "keep_going": {
        "ru": [
            "💪 Осталось немного — заверши, ин ша Аллах!",
            "🌟 Ты уже сдал часть — не останавливайся!",
            "📖 Каждое задание — шаг к Аллаху. Давай, ин ша Аллах!",
            "⚡ Почти всё! Заверши остальное сегодня.",
            "🤲 Пусть Аллах даст тебе силы завершить!",
            "🏃 Вперёд! Осталось чуть-чуть, ин ша Аллах!"
        ],
        "ky": [
            "💪 Аз калды — бүтүр, ин ша Аллах!",
            "🌟 Бир бөлүгүн сдал эттиң — токтобо!",
            "📖 Ар бир тапшырма — Аллахка бир кадам!",
            "⚡ Дээрлик бүттү! Бүгүн калганын бүтүр.",
            "🤲 Аллах күч берсин бүтүрүүгө!",
        ],
        "uz": [
            "💪 Oz qoldi — tugatgin, in sha Alloh!",
            "🌟 Bir qismini topshirding — to'xtama!",
            "📖 Har bir vazifa — Allohga bir qadam!",
            "⚡ Deyarli tugadi! Qolganini bugun tugatgin.",
            "🤲 Alloh kuch bersin tugatishga!",
        ],
        "kk": [
            "💪 Аз қалды — аяқта, ин ша Аллах!",
            "🌟 Бір бөлігін тапсырдың — тоқтама!",
            "📖 Әр тапсырма — Аллахқа бір қадам!",
            "🤲 Аллах күш берсін аяқтауға!",
        ],
        "tr": [
            "💪 Az kaldı — tamamla, inşaAllah!",
            "🌟 Bir kısmını teslim ettin — durma!",
            "📖 Her görev Allah'a bir adım!",
            "🤲 Allah tamamlaman için güç versin!",
        ],
        "ar": [
            "💪 قليل بقي — أكمله، إن شاء الله!",
            "🌟 أديت جزءاً — لا تتوقف!",
            "📖 كل مهمة خطوة إلى الله!",
            "🤲 أعانك الله على الإتمام!",
        ],
        "en": [
            "💪 Almost there — finish it, in sha Allah!",
            "🌟 You've done part — don't stop!",
            "📖 Every task is a step to Allah!",
            "🤲 May Allah give you strength to finish!",
        ],
        "zh": ["💪 快完成了——加油，因沙安拉！"],
    },
    "yassir_listening": {
        "ru": "🤖 Ясир: Слушаю! Задай вопрос 📖",
        "ky": "🤖 Ясир: Угуп жатам! Сурооңду бер 📖",
        "uz": "🤖 Yassir: Eshityapman! Savolingni ber 📖",
        "kk": "🤖 Ясир: Тыңдап тұрмын! Сұрағыңды қой 📖",
        "tr": "🤖 Yassir: Dinliyorum! Sorunu sor 📖",
        "ar": "🤖 ياسر: أستمع! اطرح سؤالك 📖",
        "en": "🤖 Yassir: Listening! Ask your question 📖",
        "zh": "🤖 亚西尔：我在听！请提问 📖",
    },
    "welcome_report": {
        "ru": "✅ {name}, добро пожаловать! Твой отчёт засчитан:",
        "ky": "✅ {name}, кош келдиң! Отчётуң эсептелди:",
        "uz": "✅ {name}, xush kelibsiz! Hisobotingiz qabul qilindi:",
        "kk": "✅ {name}, қош келдің! Есебің есептелді:",
        "tr": "✅ {name}, hoş geldin! Raporun sayıldı:",
        "ar": "✅ {name}، أهلاً بك! تم احتساب تقريرك:",
        "en": "✅ {name}, welcome! Your report is counted:",
        "zh": "✅ {name}，欢迎！你的报告已计入：",
    },
    "welcome": {
        "ru": "✅ {name}, рад знакомству! Теперь ты в группе.\nМожешь отправлять отчёты 📖",
        "ky": "✅ {name}, таанышканыма кубанычтамын! Эми сен топтосуң.\nОтчёт жөнөтсөң болот 📖",
        "uz": "✅ {name}, tanishganimdan xursandman! Endi guruhdasiz.\nHisobot yuborishingiz mumkin 📖",
        "kk": "✅ {name}, танысқаныма қуаныштымын! Енді топтасың.\nЕсеп жібере аласың 📖",
        "tr": "✅ {name}, tanıştığımıza memnun oldum! Artık gruptasın.\nRapor gönderebilirsin 📖",
        "ar": "✅ {name}، سعيد بمعرفتك! أنت الآن في المجموعة.\nيمكنك إرسال التقارير 📖",
        "en": "✅ {name}, nice to meet you! You're now in the group.\nYou can send reports 📖",
        "zh": "✅ {name}，很高兴认识你！你现在在小组里了。\n可以发送报告 📖",
    },
    "registered": {
        "ru": "✅ Зарегистрирован как {name}! 📖",
        "ky": "✅ {name} катары катталдың! 📖",
        "uz": "✅ {name} sifatida ro'yxatdan o'tdingiz! 📖",
        "kk": "✅ {name} ретінде тіркелдің! 📖",
        "tr": "✅ {name} olarak kaydoldun! 📖",
        "ar": "✅ تم تسجيلك باسم {name}! 📖",
        "en": "✅ Registered as {name}! 📖",
        "zh": "✅ 已注册为 {name}！📖",
    },
    "ask_name": {
        "ru": "👋 Ассаляму алейкум!\nКак тебя зовут? Напиши своё имя 📝\n(Твой отчёт сохранён — засчитаю после того как узнаю имя)",
        "ky": "👋 Ассаламу алейкум!\nАтың ким? Атыңды жаз 📝\n(Отчётуң сакталды — атыңды билгенден кийин эсептейм)",
        "uz": "👋 Assalomu alaykum!\nIsming nima? Ismingni yoz 📝\n(Hisobotingiz saqlandi — ismni bilganimdan keyin hisoblayman)",
        "kk": "👋 Ассалаумағалейкум!\nАтың кім? Атыңды жаз 📝\n(Есебің сақталды — атыңды білген соң есептеймін)",
        "tr": "👋 Esselamu aleykum!\nAdın ne? Adını yaz 📝\n(Raporun kaydedildi — adını öğrenince sayacağım)",
        "ar": "👋 السلام عليكم!\nما اسمك؟ اكتب اسمك 📝\n(تم حفظ تقريرك — سأحتسبه بعد معرفة اسمك)",
        "en": "👋 Assalamu alaikum!\nWhat's your name? Write your name 📝\n(Your report is saved — I'll count it once I know your name)",
        "zh": "👋 Assalamu alaikum！\n你叫什么名字？请写下你的名字 📝\n（你的报告已保存——知道名字后会计入）",
    },
    "name_only": {
        "ru": "Напиши только своё имя (например: Бакыт) 📝",
        "ky": "Жөн гана атыңды жаз (мисалы: Бакыт) 📝",
        "uz": "Faqat ismingni yoz (masalan: Baqyt) 📝",
        "kk": "Тек атыңды жаз (мысалы: Бақыт) 📝",
        "tr": "Sadece adını yaz (örnek: Bakıt) 📝",
        "ar": "اكتب اسمك فقط (مثال: باقيت) 📝",
        "en": "Write only your name (e.g., Bakyt) 📝",
        "zh": "只写你的名字（例如：巴克特）📝",
    },
    # ── Переводы для системы переводов между группами ──────────────────────────
    "transfer_to_tadabbur": {
        "ru": "📿 {name}, за период с {start} по {end} сдано только {submitted} из {total} дней — переведён в группу Тадаббур.\nПравило: {threshold} пропущенных дней без отчёта за месяц → перевод в Тадаббур.\nТам нет обязательных заданий — можешь читать, размышлять, возвращаться когда будешь готов 🤲",
        "ky": "📿 {name}, {start} — {end} аралыгында {total} күндүн ичинен {submitted} гана тапшырылды — Тадаббур тобуна которулдуң.\nЭреже: айга {threshold} күн отчётсуз болсо — Тадаббурга которуу.\nАнда милдеттүү тапшырмалар жок — окуй бер, ойлон, даяр болгондо кайт 🤲",
        "uz": "📿 {name}, {start} — {end} oralig'ida {total} kundan atigi {submitted} tasi topshirildi — Tadabbur guruhiga o'tkazilding.\nQoida: oyiga {threshold} kun hisobotsiz bo'lsa — Tadabburga o'tkazish.\nU yerda majburiy vazifalar yo'q — o'qi, fikr yurgiz, tayyor bo'lganda qait 🤲",
        "kk": "📿 {name}, {start} — {end} аралығында {total} күннің {submitted} ғана тапсырылды — Тадаббур тобына ауыстырылдың.\nЕреже: айына {threshold} күн есепсіз болса — Тадаббурға ауыстыру.\nОнда міндетті тапсырмалар жоқ — оқы, ойлан, дайын болғанда қайт 🤲",
        "en": "📿 {name}, from {start} to {end} you submitted reports on only {submitted} of {total} days — you've been moved to Tadabbur group.\nRule: {threshold} days without reports in a month → move to Tadabbur.\nNo mandatory tasks there — read, reflect, return when ready 🤲",
    },
    "return_needs_prep_group": {
        "ru": "👋 {name}, в постоянную группу можно вернуться только после подготовительной — таков общий порядок для всех, кто переведён в Тадаббур из-за пропусков сдачи заданий. Пройдите её условия — и сможете вернуться сюда. Сейчас выводим вас из этого чата, ссылку на подготовительную отправили в личные сообщения 🤲",
    },
    "return_needs_prep_group_dm_failed": {
        "ru": "👋 {name}, в постоянную группу можно вернуться только после подготовительной — таков общий порядок для всех, кто переведён в Тадаббур из-за пропусков сдачи заданий. Пройдите её условия — и сможете вернуться сюда. Сейчас выводим вас из этого чата. Личное сообщение отправить не получилось (сначала напишите боту /start в личные сообщения) — вот ссылка на подготовительную:\n👉 {prep_link}",
    },
    "return_needs_prep_dm": {
        "ru": "Ассаляму алейкум, {name}.\n\nВы состоите в группе Тадаббур, потому что раньше были переведены туда из-за пропусков сдачи заданий. Чтобы вернуться в постоянную учебную группу, правила требуют сначала пройти подготовительный период: минимум 5 дней сдачи отчётов за 14 дней в подготовительной группе.\n\nПожалуйста, вступите в подготовительную группу по ссылке ниже и начните сдавать отчёты — как только выполните условие, вы автоматически перейдёте в постоянную группу.\n\n👉 {prep_link}\n\nДа облегчит Аллах ваш путь 🤲",
    },
    "return_blocked_notify_admin": {
        "ru": "⚠️ {name} попытался вернуться в «{group}» напрямую, минуя подготовительную (сейчас в Тадаббуре/prep) — выведен из чата, отправлена ссылка на подготовительную в личку.",
    },
    "return_blocked_notify_admin_dm_failed": {
        "ru": "⚠️ {name} попытался вернуться в «{group}» напрямую, минуя подготовительную (сейчас в Тадаббуре/prep) — выведен из чата. Личное сообщение НЕ доставлено (не писал боту в личку) — ссылку показали прямо в группе.",
    },
    "transfer_to_tadabbur_lessons": {
        "ru": "📿 {name}, ты пропустил {misses} онлайн урока в этом месяце и переведён в группу Тадаббур.\nТам нет обязательных заданий — можешь читать, размышлять, возвращаться когда будешь готов 🤲",
        "ky": "📿 {name}, бул айда {misses} онлайн сабакты өткөрүп жибердиң жана Тадаббур тобуна которулдуң.\nАнда милдеттүү тапшырмалар жок — окуй бер, ойлон, даяр болгондо кайт 🤲",
        "uz": "📿 {name}, bu oyda {misses} ta onlayn darsni o'tkazib yubording va Tadabbur guruhiga o'tkazilding.\nU yerda majburiy vazifalar yo'q — o'qi, fikr yurgiz, tayyor bo'lganda qait 🤲",
        "kk": "📿 {name}, осы айда {misses} онлайн сабақты өткізіп жібердің және Тадаббур тобына ауыстырылдың.\nОнда міндетті тапсырмалар жоқ — оқы, ойлан, дайын болғанда қайт 🤲",
        "en": "📿 {name}, you missed {misses} online lessons this month and have been moved to Tadabbur group.\nNo mandatory tasks there — read, reflect, return when ready 🤲",
    },
    "upgrade_suggestion": {
        "ru": "🌟 {name}, МашаАллах! Ты 30 дней сдавал почти без пропусков.\nУстаз предлагает перейти в продвинутую (pro) группу — хочешь?",
        "ky": "🌟 {name}, МашаАллах! 30 күн дээрлик тынымсыз тапшырдың.\nУстаз сени pro-топко өтүүнү сунуштайт — каалайсыңбы?",
        "uz": "🌟 {name}, MashaAlloh! 30 kun deyarli uzluksiz topshirding.\nUstoz seni pro guruhga o'tishni tavsiya qiladi — xohlaysanmi?",
        "kk": "🌟 {name}, МашаАллах! 30 күн дерлік үздіксіз тапсырдың.\nҰстаз сені pro тобына ауысуды ұсынады — қалайсың ба?",
        "en": "🌟 {name}, MashaAllah! You've submitted almost every day for 30 days.\nUstaz suggests moving to a pro group — do you want to?",
    },
    "prep_congrats": {
        "ru": (
            "🎉 МашаАллах, {name}!\n\n"
            "Ты прошёл подготовительный период — {days} дней отчётов за 14 дней. Отличный старт!\n\n"
            "Теперь ты переходишь в основную учебную группу."
        ),
        "ky": (
            "🎉 МашаАллах, {name}!\n\n"
            "Сен даярдык мезгилин өттүң — 14 күндүн ичинде {days} күн тапшырдың. Мыкты башталыш!\n\n"
            "Эми негизги окуу тобуна которуласың."
        ),
    },
    "prep_failed": {
        "ru": (
            "Ассаляму алейкум, {name}.\n\n"
            "Подготовительный период завершился. За 14 дней ты сдавал отчёты {days} дней — "
            "этого недостаточно для перехода в учебную группу.\n\n"
            "Ты остаёшься в группе Тадаббур. Когда будешь готов начать регулярно — напиши устазу 🤲"
        ),
        "ky": (
            "Ассалааму алейкум, {name}.\n\n"
            "Даярдык мезгили аяктады. 14 күндүн ичинде {days} күн тапшырдың — "
            "бул окуу тобуна өтүү үчүн жетишсиз.\n\n"
            "Сен Тадаббур тобунда каласың. Туруктуу баштоого даяр болгондо — устазга жаз 🤲"
        ),
    },
    "prep_failed_group": {
        "ru": "📿 {name} — за 14 дней подготовительного периода сдал только {days} дн. из нужных 5, поэтому переведён в Тадаббур. Вернуться можно будет, когда будет готовность сдавать регулярно 🤲",
        "ky": "📿 {name} — даярдык мезгилинин 14 күнүндө талап кылынган 5дин ордуна {days} күн гана тапшырды, ошондуктан Тадаббур тобуна которулду. Туруктуу тапшырууга даяр болгондо кайра кошула алат 🤲",
    },
    "prep_success_group": {
        "ru": "🎉 МашаАллах! {name} сдал уже {days} дн. отчётов и выполнил условие перехода в постоянную группу — устаз определит, куда именно. Так держать, ещё есть время догнать! 🤲",
        "ky": "🎉 МашаАллах! {name} {days} күн тапшырды жана туруктуу топко өтүү шартын аткарды — устаз кайсы топко экенин чечет. Улантыңыздар, дагы үлгүрүү мүмкүнчүлүгү бар! 🤲",
    },
    "prep_graduate_notify_admin": {
        "ru": "🎓 {name} прошёл подготовительную ({days} дн. отчётов) — группа «{group}». Определите вручную в постоянную группу — бот сам кикнет его из подготовительной, как только увидит, что он стал активным в новой.",
    },
    "prep_graduate_announce_old": {
        "ru": "🎓 {name} успешно прошёл подготовительный период и переходит в группу «{title}».\nПусть Аллах облегчит его(её) путь в изучении Корана — дуа за брата/сестру! 🤲",
        "ky": "🎓 {name} даярдык мезгилин ийгиликтүү аяктап, «{title}» тобуна которулду.\nАллах анын Куран үйрөнүү жолун жеңилдетсин — ага дуба кылалы! 🤲",
    },
    "prep_graduate_announce_new": {
        "ru": "🎉 Ассаляму алейкум! Устаз, дорогие {addr} — встречайте {name}: успешно прошёл подготовительный период и присоединяется к нашей группе.\nПожелаем ему(ей) терпения и берекета на этом пути! 🤲",
        "ky": "🎉 Ассалааму алейкум! Устаз, урматтуу бир туугандар — {name} менен таанышыңыздар: даярдык мезгилин ийгиликтүү аяктап, биздин топко кошулду.\nАга сабырдуулук жана берекет каалайлы! 🤲",
    },
    "prep_reminder_active": {
        "ru": (
            "📖 {name}, МашаАллах! Ты уже сдал {days_done} из 14 дней — так держать! 💪\n"
            "Осталось {days_left} дней до конца подготовительного периода.\n"
            "Продолжай — и перейдёшь в основную группу 🤲"
        ),
        "ky": (
            "📖 {name}, МашаАллах! Сен буга чейин 14 күндүн ичинен {days_done} күн тапшырдың — ошондой уланта бер! 💪\n"
            "Даярдык мезгилине {days_left} күн калды.\n"
            "Улантсаң — негизги топко өтөсүң 🤲"
        ),
    },
    "prep_reminder_inactive": {
        "ru": (
            "📖 {name}, подготовительный период идёт — осталось {days_left} дней.\n"
            "Пока ты сдал только {days_done} из нужных 5 дней для перехода в учебную группу.\n"
            "Каждый день на счету — напиши отчёт сегодня 📝"
        ),
        "ky": (
            "📖 {name}, даярдык мезгили жүрүп жатат — {days_left} күн калды.\n"
            "Азыр сен окуу тобуна өтүү үчүн керектүү 5 күндүн ичинен {days_done} күн тапшырдың.\n"
            "Ар бир күн маанилүү — бүгүн отчёт тапшыр 📝"
        ),
    },
    "transfer_notify_admin": {
        "ru": "⚠️ Студент {name} (группа «{group}») переведён в Тадаббур (причина: {reason}, дней без отчётов: {days})",
        "en": "⚠️ Student {name} (group «{group}») transferred to Tadabbur (reason: {reason}, days absent: {days})",
    },
    "upgrade_notify_admin": {
        "ru": "⭐ Студент {name} (группа {group}) готов к переходу в pro-группу.\n30 дней с ≤3 пропусками. Выбери целевую группу и подтверди перевод командой /transfer {sid} [chat_id]",
        "en": "⭐ Student {name} (group {group}) is ready for pro group.\n30 days with ≤3 misses. Pick the target group and confirm with /transfer {sid} [chat_id]",
    },
    "ask_name": {
        "ru": "Как тебя зовут? Напиши своё имя 📝",
        "ky": "Атың ким? Атыңды жаз 📝",
        "uz": "Ismingiz nima? Ismingizni yozing 📝",
        "kk": "Атың кім? Атыңды жаз 📝",
        "ar": "ما اسمك؟ اكتب اسمك 📝",
        "en": "What is your name? Write your name 📝",
    },
    "ask_name_again": {
        "ru": "Напиши только своё имя (например: Бакыт) 📝",
        "ky": "Атыңды жаз (мисалы: Бакыт) 📝",
        "uz": "Faqat ismingizni yozing (masalan: Baxyt) 📝",
        "kk": "Тек атыңды жаз (мысалы: Бақыт) 📝",
        "ar": "اكتب اسمك فقط (مثلاً: باكيت) 📝",
        "en": "Write only your name (e.g. Bakyt) 📝",
    },
    "ask_name_confirm": {
        "ru": "Вас так и зовут — «{name}»? Напишите своё настоящее имя 🙂",
        "ky": "Атыңыз «{name}» деп жазылдыбы? Чыныгы атыңызды жазыңыз 🙂",
        "uz": "Ismingiz «{name}» deb yozilganmi? Haqiqiy ismingizni yozing 🙂",
        "kk": "Атыңыз «{name}» деп жазылды ма? Шын атыңызды жазыңыз 🙂",
        "ar": "هل اسمك «{name}»؟ اكتب اسمك الحقيقي 🙂",
        "en": "Is your name «{name}»? Please write your real name 🙂",
    },
    "registered_group": {
        "ru": "✅ Зарегистрирован как «{name}»!\nТеперь можешь сдавать отчёты 📖\nНапиши /help чтобы узнать как.",
        "ky": "✅ «{name}» катары катталдың!\nЭми отчёт бере аласың 📖\nКомандаларды билүү үчүн /help жаз.",
        "uz": "✅ «{name}» sifatida ro'yxatdan o'tdingiz!\nEndi hisobot topshirishingiz mumkin 📖\nBuyruqlar uchun /help yozing.",
        "kk": "✅ «{name}» ретінде тіркелдің!\nЕнді есеп тапсыра аласың 📖\nКомандаларды білу үшін /help жаз.",
        "ar": "✅ تم تسجيلك باسم «{name}»!\nيمكنك الآن تسليم التقارير 📖\nاكتب /help لمعرفة الأوامر.",
        "en": "✅ Registered as «{name}»!\nYou can now submit reports 📖\nWrite /help to see commands.",
    },
    "registered_group_dm": {
        "ru": "✅ Зарегистрирован как «{name}»!\nОтчёты сдавай прямо тут, в группе 📖\nА команды /help, /rating, /mystats и личные напоминания теперь приходят в личку — перейди по ссылке и нажми Start (один раз):\n{link}",
    },
    "dm_start_needed": {
        "ru": "Нажми Start в личке с ботом, чтобы получить ответ туда 👇\n{link}",
    },
    "dm_answered": {
        "ru": "📩 Ответил тебе в личку",
    },
    "dm_welcome": {
        "ru": "Ассаляму алейкум, {name}! 🌙\nТут в личке доступны: /help, /rating, /mystats.\nОтчёты по-прежнему сдавай в своей группе 📖",
    },
    "already_in_group": {
        "ru": "{name}, ты уже студент группы «{title}». Студент может быть только в одной учебной группе.",
        "ky": "{name}, сен «{title}» тобунун студентисиң. Студент бир гана окуу тобунда боло алат.",
        "uz": "{name}, siz «{title}» guruhining talabasisiz. Talaba faqat bitta o'quv guruhida bo'lishi mumkin.",
        "kk": "{name}, сен «{title}» тобының студентісің. Студент тек бір оқу тобында бола алады.",
        "ar": "{name}، أنت بالفعل طالب في مجموعة «{title}». يمكن أن يكون الطالب في مجموعة تعليمية واحدة فقط.",
        "en": "{name}, you're already a student of «{title}». A student can only be in one learning group.",
    },
    "not_registered": {
        "ru": "Ты ещё не зарегистрирован. Напиши любое сообщение в группе — бот попросит твоё имя 📝",
        "ky": "Сен дагы катталган эмессиң. Топто каалаган сөздү жаз — бот атыңды сурайт 📝",
        "uz": "Siz hali ro'yxatdan o'tmagansiz. Guruhda istalgan xabar yozing — bot ismingizni so'raydi 📝",
        "kk": "Сен әлі тіркелмегенсің. Топта кез келген хабар жаз — бот атыңды сұрайды 📝",
        "ar": "لم تسجل بعد. اكتب أي رسالة في المجموعة — سيطلب البوت اسمك 📝",
        "en": "You are not registered yet. Write any message in the group — the bot will ask your name 📝",
    },
    "help_redirect": {
        "ru": "Напиши мне в личку /help — покажу команды по твоей роли 👤",
        "ky": "Мага жеке /help жаз — ролуңа жараша буйруктарды көрсөтөм 👤",
        "uz": "Menga shaxsiy /help yozing — rolingizga mos buyruqlarni ko'rsataman 👤",
        "kk": "Маған жеке /help жаз — рөліңе сай командаларды көрсетемін 👤",
        "ar": "اكتب لي /help في الخاص — سأريك الأوامر حسب دورك 👤",
        "en": "Write me /help in DM — I'll show commands for your role 👤",
    },
    "mystats_title": {
        "ru": "📊 Моя статистика — {name}\n",
        "ky": "📊 Менин статистикам — {name}\n",
        "uz": "📊 Mening statistikam — {name}\n",
        "kk": "📊 Менің статистикам — {name}\n",
        "ar": "📊 إحصائياتي — {name}\n",
        "en": "📊 My stats — {name}\n",
    },
    "mystats_streak": {
        "ru": "🔥 Серия: {n} дней подряд",
        "ky": "🔥 Катар: {n} күн",
        "uz": "🔥 Ketma-ket: {n} kun",
        "kk": "🔥 Қатар: {n} күн",
        "ar": "🔥 التسلسل: {n} أيام متتالية",
        "en": "🔥 Streak: {n} days in a row",
    },
    "mystats_rank": {
        "ru": "🏆 Место в группе: #{n}",
        "ky": "🏆 Топтогу орун: #{n}",
        "uz": "🏆 Guruhda o'rin: #{n}",
        "kk": "🏆 Топтағы орын: #{n}",
        "ar": "🏆 المرتبة في المجموعة: #{n}",
        "en": "🏆 Rank in group: #{n}",
    },
    "mystats_points": {
        "ru": "💎 Всего баллов: {n}",
        "ky": "💎 Жалпы упай: {n}",
        "uz": "💎 Jami ball: {n}",
        "kk": "💎 Барлық ұпай: {n}",
        "ar": "💎 مجموع النقاط: {n}",
        "en": "💎 Total points: {n}",
    },
    "mystats_days": {
        "ru": "📅 Дней сдано: {n}",
        "ky": "📅 Тапшырылган күндөр: {n}",
        "uz": "📅 Topshirilgan kunlar: {n}",
        "kk": "📅 Тапсырылған күндер: {n}",
        "ar": "📅 أيام التسليم: {n}",
        "en": "📅 Days submitted: {n}",
    },
    "mystats_skips": {
        "ru": "⚠️ Пропусков в {month}: {n}/{limit}",
        "ky": "⚠️ {month} айдагы өткөрүп жиберүүлөр: {n}/{limit}",
        "uz": "⚠️ {month} oyda o'tkazib yuborishlar: {n}/{limit}",
        "kk": "⚠️ {month} айдағы өткізіп жіберулер: {n}/{limit}",
        "ar": "⚠️ الغيابات في {month}: {n}/{limit}",
        "en": "⚠️ Skips in {month}: {n}/{limit}",
    },
    "mystats_today": {
        "ru": "✅ Сегодня: {done}/{total} заданий",
        "ky": "✅ Бүгүн: {done}/{total} тапшырма",
        "uz": "✅ Bugun: {done}/{total} vazifa",
        "kk": "✅ Бүгін: {done}/{total} тапсырма",
        "ar": "✅ اليوم: {done}/{total} مهام",
        "en": "✅ Today: {done}/{total} tasks",
    },
    "rating_header": {
        "ru": "🏆 Рейтинг — {title} (7 дней):\n",
        "ky": "🏆 Рейтинг — {title} (7 күн):\n",
        "uz": "🏆 Reyting — {title} (7 kun):\n",
        "kk": "🏆 Рейтинг — {title} (7 күн):\n",
        "ar": "🏆 الترتيب — {title} (7 أيام):\n",
        "en": "🏆 Rating — {title} (7 days):\n",
    },
    "rating_points": {
        "ru": "очков",
        "ky": "упай",
        "uz": "ball",
        "kk": "ұпай",
        "ar": "نقاط",
        "en": "pts",
    },
    "rating_days": {
        "ru": "дней",
        "ky": "күн",
        "uz": "kun",
        "kk": "күн",
        "ar": "أيام",
        "en": "days",
    },
    "photo_needs_caption": {
        "ru": "📸 {name}, фото без подписи не засчитывается.\nПришли снова с caption — что прописывал:\n\n{legend}",
        "ky": "📸 {name}, сүрөт подписьсиз кабыл алынбайт.\nКайра жибер жана caption жаз — эмнени жаздыгыңды:\n\n{legend}",
        "uz": "📸 {name}, captionsiz rasm qabul qilinmaydi.\nQayta yubor va caption yoz — nima yozganingni:\n\n{legend}",
        "kk": "📸 {name}, подписьсіз сурет есептелмейді.\nҚайта жібер және caption жаз — нені жазғаныңды:\n\n{legend}",
        "tr": "📸 {name}, başlıksız fotoğraf sayılmaz.\nTekrar gönder ve caption ekle — neyi yazdığını:\n\n{legend}",
        "ar": "📸 {name}، الصورة بدون تعليق لا تُحتسب.\nأرسلها مجدداً مع caption — ماذا كتبت:\n\n{legend}",
        "en": "📸 {name}, photo without caption won't be counted.\nResend with a caption — what you wrote:\n\n{legend}",
        "zh": "📸 {name}，没有说明的照片不计入。\n请重新发送并加上 caption——你写的是什么：\n\n{legend}",
    },
}


# Тексты в TR написаны в мужском роде по умолчанию. Для женского профиля
# (config.IS_FEMALE) правим здесь, в одном месте — не дублируем каждую
# строку на два рода. \b — чтобы не задеть однокоренные слова с другим
# смыслом (например "готовность").
_GENDER_FIXES = [
    (r"\bсдал\b", "сдала"),
    (r"\bсдавал\b", "сдавала"),
    (r"\bзавершил\b", "завершила"),
    (r"\bпропустил\b", "пропустила"),
    (r"\bпереведён\b", "переведена"),
    (r"\bпопытался\b", "попыталась"),
    (r"\bвыведен\b", "выведена"),
    (r"\bвыполнил\b", "выполнила"),
    (r"\bготов\b", "готова"),
    (r"\bпрошёл\b", "прошла"),
    (r"\bЗарегистрирован\b", "Зарегистрирована"),
    (r"\bзарегистрирован\b", "зарегистрирована"),
    (r"\bСтудент\b", "Студентка"),
    (r"\bстудент\b", "студентка"),
]


def _apply_gender(text):
    if not IS_FEMALE or not text:
        return text
    for pattern, repl in _GENDER_FIXES:
        text = re.sub(pattern, repl, text)
    return text


def T(key, lang="ru", **kwargs):
    """Перевод сообщения для студента на язык группы."""
    table = TR.get(key, {})
    text = table.get(lang) or table.get("ru") or ""
    if isinstance(text, list):
        text = random.choice(text)
    text = _apply_gender(text)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


# ── Названия заданий (для help, легенд, отчётов) ──────────────────────────────

TASK_NAMES_I18N = {
    "m": {"ru": "Заучивание (или 40+40)", "ky": "Жаттоо (же 40+40)", "uz": "Yodlash (yoki 40+40)", "kk": "Жаттау (немесе 40+40)", "en": "Memorization (or 40+40)"},
    "r": {"ru": "Повторение",             "ky": "Кайталоо",           "uz": "Takrorlash",          "kk": "Қайталау",              "en": "Revision"},
    "t": {"ru": "Слова (или Перевод)",    "ky": "Сөздөр (же Котормо)","uz": "So'zlar (yoki Tarjima)","kk": "Сөздер (немесе Аударма)","en": "Words (or Translation)"},
    "j": {"ru": "Таджвид",               "ky": "Таджвид",            "uz": "Tajvid",              "kk": "Тәжуид",                "en": "Tajweed"},
    "n": {"ru": "Грамматика (или Нахв)", "ky": "Грамматика (же Нахв)","uz": "Grammatika (yoki Nahv)","kk": "Грамматика (немесе Нахв)","en": "Grammar (or Nahw)"},
    "h": {"ru": "Хадис",                 "ky": "Хадис",              "uz": "Hadis",               "kk": "Хадис",                 "en": "Hadith"},
}

def task_name(key, lang="ru"):
    return TASK_NAMES_I18N.get(key, {}).get(lang) or TASK_NAMES_I18N.get(key, {}).get("ru", key)


# ── Help-секции ───────────────────────────────────────────────────────────────

_HELP_STUDENT = {
    "ru": {
        "header": "📚 КАК СДАВАТЬ ОТЧЁТ\nПиши что выполнил:\n{tasks}\nЗа каждое задание +1 балл 💎\n\n"
                  "⛔ Уважительная причина:\nболею / уважительная / узр / причина есть\n"
                  "📡 Онлайн урок: напиши у\n\n"
                  "/mystats — твоя статистика\n/rating — рейтинг группы\nЯсир, ...? — задай вопрос боту",
        "pro":     "\n⚠️ Pro-группа: пропуск 10 дней → Тадаббур",
        "relaxed": "\n📅 Расслабленная: пропуск 20 дней → Тадаббур",
        "prep":    "\n🔰 Подготовительная: 14 дней. Сдай ≥5 дней — перейдёшь в основную группу.",
    },
    "ky": {
        "header": "📚 ОТЧЁТ КАНТИП ТАПШЫРЫЛАТ\nЭмнени аткаргандыгыңды жаз:\n{tasks}\nАр бир тапшырма үчүн +1 упай 💎\n\n"
                  "⛔ Узактуу себеп:\nооруп жатам / себебим бар / узр\n"
                  "📡 Онлайн сабак: у деп жаз\n\n"
                  "/mystats — сенин статистикаң\n/rating — топтун рейтинги\nЯсир, ...? — боттон суроо бер",
        "pro":     "\n⚠️ Pro-топ: 10 күн өткөрүп жиберсең → Тадаббурга",
        "relaxed": "\n📅 Жеңил топ: 20 күн өткөрүп жиберсең → Тадаббурга",
        "prep":    "\n🔰 Даярдык топ: 14 күн. ≥5 күн тапшырсаң — негизги топко өтөсүң.",
    },
    "uz": {
        "header": "📚 HISOBOT QANDAY TOPSHIRILADI\nNimani bajarganingni yoz:\n{tasks}\nHar bir topshiriq uchun +1 ball 💎\n\n"
                  "⛔ Uzrli sabab:\nkasalman / sabab bor / uzr\n"
                  "📡 Onlayn dars: u deb yoz\n\n"
                  "/mystats — sening statistikang\n/rating — guruh reytingi\nYassir, ...? — botdan so'ra",
        "pro":     "\n⚠️ Pro-guruh: 10 kun o'tkazib yuborsang → Tadabbur",
        "relaxed": "\n📅 Yengil guruh: 20 kun o'tkazib yuborsang → Tadabbur",
        "prep":    "\n🔰 Tayyorlov guruhi: 14 kun. ≥5 kun topshirsang — asosiy guruhga o'tasan.",
    },
    "kk": {
        "header": "📚 ЕСЕПТІ ҚАЛАЙ ТАПСЫРУ КЕРЕК\nНені орындағаныңды жаз:\n{tasks}\nӘр тапсырма үшін +1 ұпай 💎\n\n"
                  "⛔ Дәлелді себеп:\nауырып жатырмын / себебім бар / узр\n"
                  "📡 Онлайн сабақ: у деп жаз\n\n"
                  "/mystats — сенің статистикаң\n/rating — топ рейтингі\nЯсир, ...? — боттан сұра",
        "pro":     "\n⚠️ Pro-топ: 10 күн өткізіп жіберсең → Тадаббур",
        "relaxed": "\n📅 Жеңіл топ: 20 күн өткізіп жіберсең → Тадаббур",
        "prep":    "\n🔰 Дайындық тобы: 14 күн. ≥5 күн тапсырсаң — негізгі топқа өтесің.",
    },
    "en": {
        "header": "📚 HOW TO SUBMIT A REPORT\nWrite what you completed:\n{tasks}\n+1 point per task 💎\n\n"
                  "⛔ Valid excuse:\nI'm sick / valid reason / uzr\n"
                  "📡 Online lesson: write u\n\n"
                  "/mystats — your stats\n/rating — group rating\nYassir, ...? — ask the bot",
        "pro":     "\n⚠️ Pro group: 10 days missed → Tadabbur",
        "relaxed": "\n📅 Relaxed group: 20 days missed → Tadabbur",
        "prep":    "\n🔰 Prep group: 14 days. Submit ≥5 days — move to main group.",
    },
}

_HELP_ADMIN = {
    "ru": (
        "👤 КОМАНДЫ УСТАЗА (пиши в группе)\n"
        "/remove Имя — убрать студента\n"
        "/rename Имя | Новое имя — переименовать\n"
        "/students — список студентов\n\n"
        "/report — отчёт за сегодня\n"
        "/week — за 7 дней\n"
        "/month — за 30 дней\n"
        "/year — за год\n"
        "/rating — рейтинг\n\n"
        "/bonus Имя 5 причина — начислить баллы\n"
        "/groupinfo — настройки группы\n"
        "/settasks m,r,t,j,n,h — задания\n"
        "  m-заучивание r-повторение t-слова\n"
        "  j-таджвид n-грамматика h-хадис\n"
        "/setlang ru — язык (ru/ky/uz/kk/ar)\n"
        "/settype pro/relaxed/tadabbur/prep — тип группы\n"
        "/setlink https://t.me/+xxx — ссылка-приглашение группы"
    ),
    "ky": (
        "👤 УСТАЗДЫН БУЙРУКТАРЫ (топто жаз)\n"
        "/remove Аты — студентти алып салуу\n"
        "/rename Аты | Жаңы аты — атын өзгөртүү\n"
        "/students — студенттердин тизмеси\n\n"
        "/report — бүгүнкү отчёт\n"
        "/week — 7 күн\n"
        "/month — 30 күн\n"
        "/year — жыл үчүн\n"
        "/rating — рейтинг\n\n"
        "/bonus Аты 5 себеп — упай кошуу\n"
        "/groupinfo — топтун жөндөөлөрү\n"
        "/settasks m,r,t,j,n,h — тапшырмалар\n"
        "  m-жаттоо r-кайталоо t-сөздөр\n"
        "  j-таджвид n-грамматика h-хадис\n"
        "/setlang ky — тил (ru/ky/uz/kk/ar)\n"
        "/settype pro/relaxed/tadabbur/prep — топ түрү\n"
        "/setlink https://t.me/+xxx — топтун чакыруу шилтемеси"
    ),
    "uz": (
        "👤 USTOZ BUYRUQLARI (guruhda yoz)\n"
        "/remove Ism — talabani o'chirish\n"
        "/rename Ism | Yangi ism — ismni o'zgartirish\n"
        "/students — talabalar ro'yxati\n\n"
        "/report — bugungi hisobot\n"
        "/week — 7 kun\n"
        "/month — 30 kun\n"
        "/year — yil uchun\n"
        "/rating — reyting\n\n"
        "/bonus Ism 5 sabab — ball qo'shish\n"
        "/groupinfo — guruh sozlamalari\n"
        "/settasks m,r,t,j,n,h — topshiriqlar\n"
        "  m-yodlash r-takrorlash t-so'zlar\n"
        "  j-tajvid n-grammatika h-hadis\n"
        "/setlang uz — til (ru/ky/uz/kk/ar)\n"
        "/settype pro/relaxed/tadabbur — guruh turi"
    ),
    "kk": (
        "👤 ҰСТАЗ КОМАНДАЛАРЫ (топта жаз)\n"
        "/remove Аты — студентті алу\n"
        "/rename Аты | Жаңа аты — атын өзгерту\n"
        "/students — студенттер тізімі\n\n"
        "/report — бүгінгі есеп\n"
        "/week — 7 күн\n"
        "/month — 30 күн\n"
        "/year — жыл үшін\n"
        "/rating — рейтинг\n\n"
        "/bonus Аты 5 себеп — ұпай қосу\n"
        "/groupinfo — топ баптаулары\n"
        "/settasks m,r,t,j,n,h — тапсырмалар\n"
        "  m-жаттау r-қайталау t-сөздер\n"
        "  j-тәжуид n-грамматика h-хадис\n"
        "/setlang kk — тіл (ru/ky/uz/kk/ar)\n"
        "/settype pro/relaxed/tadabbur — топ түрі"
    ),
    "en": (
        "👤 USTAZ COMMANDS (write in group)\n"
        "/remove Name — remove student\n"
        "/rename Name | New name — rename\n"
        "/students — student list\n\n"
        "/report — today's report\n"
        "/week — 7 days\n"
        "/month — 30 days\n"
        "/year — yearly\n"
        "/rating — rating\n\n"
        "/bonus Name 5 reason — add points\n"
        "/groupinfo — group settings\n"
        "/settasks m,r,t,j,n,h — tasks\n"
        "  m-memorization r-revision t-words\n"
        "  j-tajweed n-grammar h-hadith\n"
        "/setlang en — language (ru/ky/uz/kk/ar)\n"
        "/settype pro/relaxed/tadabbur — group type"
    ),
}

def help_student(group_tasks, gtype, lang="ru"):
    """Возвращает help-текст для студента на нужном языке."""
    block = _HELP_STUDENT.get(lang) or _HELP_STUDENT["ru"]
    from core.i18n import task_name as _tn
    task_lines = "\n".join(
        str(i + 1) + ". " + _tn(k, lang)
        for i, k in enumerate(group_tasks)
    )
    text = block["header"].format(tasks=task_lines)
    if gtype == "pro":
        text += block.get("pro", "")
    elif gtype == "relaxed":
        text += block.get("relaxed", "")
    elif gtype == "prep":
        text += block.get("prep", "")
    return text

def help_admin(lang="ru"):
    """Возвращает help-текст для устаза на нужном языке."""
    return _HELP_ADMIN.get(lang) or _HELP_ADMIN["ru"]


def get_group_lang(group):
    try:
        return group["lang"] or "ru"
    except (IndexError, KeyError):
        return "ru"


def lang_instruction(lang):
    name = LANG_NAMES.get(lang, "Russian")
    return "IMPORTANT: write the ENTIRE response in " + name + " language (code: " + lang + "). Do not mix languages."
