import random

LANG_NAMES = {
    "ru": "русский",
    "ky": "кыргызский",
    "uz": "узбекский",
    "kk": "казахский",
    "tr": "турецкий",
    "ar": "арабский",
    "en": "английский",
    "zh": "китайский",
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
        "ru": "✅ {name}, это уже засчитано раньше 🌟",
        "ky": "✅ {name}, бул мурда эсептелген 🌟",
        "uz": "✅ {name}, bu avval hisoblangan 🌟",
        "kk": "✅ {name}, бұл бұрын есептелген 🌟",
        "tr": "✅ {name}, bu daha önce sayıldı 🌟",
        "ar": "✅ {name}، هذا تم احتسابه سابقاً 🌟",
        "en": "✅ {name}, this was already counted 🌟",
        "zh": "✅ {name}，这个之前已经计入 🌟",
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
        "ru": "📿 {name}, за {days} дней без отчётов ты переведён в группу Тадаббур.\nТам нет обязательных заданий — можешь читать, размышлять, возвращаться когда будешь готов 🤲",
        "ky": "📿 {name}, {days} күн отчёт жок болгондуктан Тадаббур тобуна которулдуң.\nАнда милдеттүү тапшырмалар жок — окуй бер, ойлон, даяр болгондо кайт 🤲",
        "uz": "📿 {name}, {days} kun hibobotsiz Tadabbur guruhiga o'tkazilding.\nU yerda majburiy vazifalar yo'q — o'qi, fikr yurgiz, tayyor bo'lganda qait 🤲",
        "kk": "📿 {name}, {days} күн есеп жоқтан Тадаббур тобына ауыстырылдың.\nОнда міндетті тапсырмалар жоқ — оқы, ойлан, дайын болғанда қайт 🤲",
        "en": "📿 {name}, after {days} days without reports you've been moved to Tadabbur group.\nNo mandatory tasks there — read, reflect, return when ready 🤲",
    },
    "upgrade_suggestion": {
        "ru": "🌟 {name}, МашаАллах! Ты 30 дней сдавал почти без пропусков.\nУстаз предлагает перейти в продвинутую (pro) группу — хочешь?",
        "ky": "🌟 {name}, МашаАллах! 30 күн дээрлик тынымсыз тапшырдың.\nУстаз сени pro-топко өтүүнү сунуштайт — каалайсыңбы?",
        "uz": "🌟 {name}, MashaAlloh! 30 kun deyarli uzluksiz topshirding.\nUstoz seni pro guruhga o'tishni tavsiya qiladi — xohlaysanmi?",
        "kk": "🌟 {name}, МашаАллах! 30 күн дерлік үздіксіз тапсырдың.\nҰстаз сені pro тобына ауысуды ұсынады — қалайсың ба?",
        "en": "🌟 {name}, MashaAllah! You've submitted almost every day for 30 days.\nUstaz suggests moving to a pro group — do you want to?",
    },
    "transfer_notify_admin": {
        "ru": "⚠️ Студент {name} переведён в Тадаббур (причина: {reason}, дней без отчётов: {days})",
        "en": "⚠️ Student {name} transferred to Tadabbur (reason: {reason}, days absent: {days})",
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
    "registered_group": {
        "ru": "✅ Зарегистрирован как «{name}»!\nТеперь можешь сдавать отчёты 📖\nНапиши /help чтобы узнать как.",
        "ky": "✅ «{name}» катары катталдың!\nЭми отчёт бере аласың 📖\nКомандаларды билүү үчүн /help жаз.",
        "uz": "✅ «{name}» sifatida ro'yxatdan o'tdingiz!\nEndi hisobot topshirishingiz mumkin 📖\nBuyruqlar uchun /help yozing.",
        "kk": "✅ «{name}» ретінде тіркелдің!\nЕнді есеп тапсыра аласың 📖\nКомандаларды білу үшін /help жаз.",
        "ar": "✅ تم تسجيلك باسم «{name}»!\nيمكنك الآن تسليم التقارير 📖\nاكتب /help لمعرفة الأوامر.",
        "en": "✅ Registered as «{name}»!\nYou can now submit reports 📖\nWrite /help to see commands.",
    },
    "not_registered": {
        "ru": "Ты ещё не зарегистрирован. Напиши боту в личку /start 👤",
        "ky": "Сен дагы катталган эмессиң. Ботко жеке /start жаз 👤",
        "uz": "Siz hali ro'yxatdan o'tmagansiz. Botga shaxsiy /start yozing 👤",
        "kk": "Сен әлі тіркелмегенсің. Ботқа жеке /start жаз 👤",
        "ar": "لم تسجل بعد. اكتب /start للبوت في الخاص 👤",
        "en": "You are not registered yet. Write /start to the bot in DM 👤",
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
        "ru": "⚠️ Пропусков в месяце: {n}/{limit}",
        "ky": "⚠️ Айдагы өткөрүп жиберүүлөр: {n}/{limit}",
        "uz": "⚠️ Oyda o'tkazib yuborishlar: {n}/{limit}",
        "kk": "⚠️ Айдағы өткізіп жіберулер: {n}/{limit}",
        "ar": "⚠️ الغيابات في الشهر: {n}/{limit}",
        "en": "⚠️ Skips this month: {n}/{limit}",
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
}


def T(key, lang="ru", **kwargs):
    """Перевод сообщения для студента на язык группы."""
    table = TR.get(key, {})
    text = table.get(lang) or table.get("ru") or ""
    if isinstance(text, list):
        text = random.choice(text)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def get_group_lang(group):
    try:
        return group["lang"] or "ru"
    except (IndexError, KeyError):
        return "ru"


def lang_instruction(lang):
    name = LANG_NAMES.get(lang, "русский")
    return "ВАЖНО: пиши ВЕСЬ ответ на языке: " + name + " (" + lang + ")."
