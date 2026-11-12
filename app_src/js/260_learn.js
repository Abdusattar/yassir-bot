  /* --- «Как работаем» (08.09.2026) -------------------------------------
     Онбординг на снимках самого приложения: каждый шаг - реальный экран, на
     нём обведено то, на что нажимаешь. Снимки делает scripts/shoot_onboarding.py
     (кликает по НАСТОЯЩИМ кнопкам в локальной копии приложения), лежат в
     mushaf_data/onboarding/. Переименуют кнопку - съёмка упадёт, а не соврёт.

     Тексты держим здесь, рядом с шагами, а не в общем словаре I18N: это
     связный рассказ, и править его надо целиком, видя порядок. Пока только
     по-русски (правило проекта: локализация одним проходом, когда отшлифуется).

     Разделов четыре, готовы два: сдача заучивания и работа с устазом. Они
     разведены намеренно - это разные места и разные моменты: сдают в Мусхафе,
     а разбор ждёт за своей дверью. «Повторение» и «Слова» показываем как
     «скоро»: обещание честнее пустой двери.

     Внутри раздела - один шаг на экран (решение пользователя 08.09.2026):
     онбординг читают один раз и тогда, когда растерялись, - там важнее
     довести до конца, чем дать быстрый доступ; за возврат отвечает оглавление. */
  var LEARN = [
    {
      id: 'hifz', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M12 21V7\" /><path d=\"m16 12 2 2 4-4\" /><path d=\"M22 6V4a1 1 0 0 0-1-1h-5a4 4 0 0 0-4 4 4 4 0 0 0-4-4H3a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h6a3 3 0 0 1 3 3 3 3 0 0 1 3-3h6a1 1 0 0 0 1-1v-1.3\" /></svg>", name: 'Заучивание',
      desc: 'Как сдать 40+40 из Мусхафа',
      // Видео-инструкция (27.10.2026): id ролика на YouTube. У раздела с ним
      // первым открывается видео, шаги со снимками - кнопкой под ним.
      video: 'roO2tI8iNmg',
      steps: [
        ['dash', 'Открой «Мусхаф»',
         'Заучивание сдаётся отсюда — там же, где ты читаешь.'],
        ['mushaf', 'Нажми 📖 наверху',
         'Эта кнопка включает режим заучивания. Рядом 🔁 — она для повторения, не путай, и 📜 — смысловой перевод: его читают отдельно, место запоминается само. А смысл одного аята — удержи на нём палец.'],
        ['pick', 'Первый раз — отметь своё место',
         'Приложение спросит, с какой строчки начинаешь. Внизу выбери, что заучиваешь: строку, половину листа или всю страницу. Потом тапни по самой строке.'],
        ['pointer', 'Место отмечено',
         'Наверху видно, где ты стоишь: страница, строчка и этап. Ошибся — «поправить» вернёт выбор. Дальше приложение ведёт само: строчки первой половины, половина целиком, строчки второй, вторая половина, вся страница.'],
        ['big', 'Поверни телефон — крупно, как в мусхафе',
         'Лёжа остаются только твои строки, во всю ширину, и первое слово следующей — чтобы стык не рвался. Строка не ломается, она такая же, как на листе. Слева счётчик: тап — один повтор, 40 раз глядя, потом 40 по памяти. 🔊 читает это же место голосом Хусари, по кругу. Тап по слову — перевод. Повернул обратно — снова весь лист.'],
        ['rec', 'Готов — «🎙 Сдать», потом «Записать»',
         'Читаешь вслух то, что заучил. Запись уходит устазу вместе с картинкой листа: ему видно, какое место ты сдавал.'],
        ['progress', 'На половине и странице — отметь повторы',
         'Строчку закрывает одна сдача. А половину листа и целую страницу почти никто не делает за раз, их набирают за 2-3 дня. Поэтому после отправки приложение спрашивает, сколько повторов вышло сегодня: жми +10 / +20 / +40 или «своё» и впиши число. Место закроется и пойдёт дальше, когда наберётся 80.']
      ]
    },
    {
      id: 'revision', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"m17 2 4 4-4 4\" /><path d=\"M3 11v-1a4 4 0 0 1 4-4h14\" /><path d=\"m7 22-4-4 4-4\" /><path d=\"M21 13v1a4 4 0 0 1-4 4H3\" /></svg>", name: 'Повторение',
      desc: 'Что читать каждый день',
      video: 'LnvB8Zf_Hsk',
      steps: [
        ['read', 'Читаешь всё, что уже выучил',
         'Повторение — это не вчерашняя строчка. Каждый день перечитываешь с начала суры Аль-Бакара до места, где остановился. Её начало открывается сразу: «⤒ Бакара» внизу. Забыл — подглядывай в текст, это не экзамен: цель — освежить, а не проверить себя.'],
        ['bookmark', 'Закладка помнит, где ты',
         '🔖 внизу открывает меню: «Сохранить закладку здесь» — на странице, где закончил, «К закладке» — вернуться к ней. Рядом листание ‹ стр. N › и «⤒ Бакара» — начало Аль-Бакары, откуда начинается повторение.'],
        ['revision', 'Прочитал — нажми 🔁',
         'Кнопка стоит рядом с 📖, на странице чтения. Это то же самое, что написать «повторил» в группу, только без набора текста.'],
        ['revision_ask', 'Подтверди — и готово',
         'Приложение переспросит: случайный тап не должен закрывать задание. Ответил «Да» — повторение за сегодня засчитано, а в группу уйдёт отметка. Второй раз за день жать не нужно, скажет, что уже засчитано.']
      ]
    },
    {
      id: 'words', mark: '\u0646', name: 'Слова и тренажёр',
      desc: 'Муфрадат, «Мои слова»',
      video: 'drBlR1-Ta3U',
      steps: [
        ['trainer_start', 'Скажи, докуда дошёл',
         'В первый раз тренажёр спросит страницу мусхафа. Слова он берёт не с неё одной, а со всего пути от начала до неё — это и есть твой словарь.'],
        ['trainer_q', 'Слово в своей строке и восемь переводов',
         'Тренажёр показывает строку мусхафа, откуда взято слово, само слово выделено зелёным. Соседние слова помогают вспомнить, что оно значит именно здесь. Выбери верный перевод. Сверху видно, сколько слов пройдено сегодня и сколько из них верно.'],
        ['trainer_answer', 'Ошибаться — часть работы',
         'После ответа сразу виден верный перевод. Ответил верно — сегодня это слово больше не спросят, очередь за другими. Ошибся — слово само уходит в «Мои слова» и начинает попадаться чаще: каждый третий вопрос берётся оттуда. Выйдет из списка, когда ответишь по нему верно три раза подряд. А хорошо закреплённое слово тренажёр отложит примерно на два месяца и потом вернёт — проверить, осталось ли оно в памяти.'],
        ['trainer_daily', '40 слов, из них 20 верно — задание закрыто',
         'Пилюля сверху держит оба числа. Слова считаются разные: одно и то же слово, отвеченное десять раз, засчитается за одно. Верным слово становится, когда ответил по нему верно хотя бы раз за день. Наберутся оба числа — задание «Слова» закроется само, а в группу уйдёт отметка.'],
        ['trainer_range', '➖ ➕ — докуда словарь',
         '➕ двигает закладку на страницу вперёд, ➖ возвращает назад. Выучил новую страницу — расширь, и её слова войдут в тренажёр.'],
        ['trainer_end', 'Итог: сколько слов выучено',
         '«✅ Закончить» показывает, сколько слов словаря выучено — то есть отвечено верно три раза подряд. Ошибся по выученному слову — оно снова в пути и вернётся в карточках. Ниже — точность за последние дни и место в рейтинге. Место решают вместе три вещи: точность, сколько разных слов ты тренировал и как далеко прошёл по Корану. Всё выучено — расширь словарь кнопкой ➕ или «На моё место», если заучивание ушло дальше.'],
        ['word_tap', 'Тап по слову — перевод',
         'Работает прямо на листе — и стоя, и лёжа, и в заучивании. Тапнул — увидел, что значит слово, ничего никуда не уходит.'],
        ['word_add', 'Двойной тап — слово в «Мои слова»',
         'Так и собираются забытые. Заметил при повторении, что слово не вспоминается, — два тапа, и тренажёр будет спрашивать его чаще.'],
        ['mywords', 'Список «Мои слова»',
         'Здесь всё, что просело: арабское слово и перевод, просто читать. Двойной тап по строке убирает слово из списка.']
      ]
    },
    {
      id: 'ustaz', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2\" /><circle cx=\"9\" cy=\"7\" r=\"4\" /><polyline points=\"16 11 18 13 22 9\" /></svg>", name: 'Работа с устазом',
      desc: 'Разбор, пометки, пересдача',
      video: 'JED2dRaFJmw',
      steps: [
        ['subs', 'Здесь видно, что с твоими записями',
         '«На проверке» — устаз ещё не дошёл, от тебя ничего не нужно. «Принято» — разобрано. «Пересдать» — просит начитать это место заново; такие записи собраны наверху, чтобы не искать.'],
        ['look', 'Разбор: его пометки на твоём листе',
         'Открывается кнопкой «Разбор устаза». Розовым отмечены слова, где была ошибка, внизу — его голос и «↺ 10 сек назад», если не расслышал. Заходить стоит и когда приняли: пометки там тоже есть. Кнопка «Пересдать» записывает то же место заново — и как только запись ушла, дорога снова открыта, ждать ответа не надо.']
      ]
    },
    {
      // Раздел устаза (08.09.2026). Студенту он не показывается совсем -
      // не «заперт», а не существует: у него этих экранов нет.
      id: 'review', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M12 20h9\" /><path d=\"M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z\" /></svg>", name: 'Проверка сдач', ustaz: true,
      desc: 'Кабинет устаза: очередь, разбор, вердикт',
      steps: [
        ['u_door', 'Дверь «Устаз» — только у тебя',
         'Студенты её не видят. Число на двери — сколько сдач ждут разбора в твоих группах. Оно спокойное, не красное: очередь проверки — это работа, а не долг.'],
        ['u_queue', '«Ждут» — очередь на разбор',
         'Строка под зонами — группа; тапни по ней, чтобы переключиться, там же видно, где сколько ждёт. Открыта всегда одна группа. В карточке: кто сдал, какое место (страница и строчка, половина листа или лист целиком) и сколько уже ждёт. «через апп» — запись из приложения, её разбираешь прямо здесь; «через группу» — голосовое, присланное в чат, у него места на листе нет.'],
        ['u_open', 'Открыл — перед тобой его лист',
         'Та же страница мусхафа, что у студента, и то самое место, которое он сдавал. «▶ Прослушать сдачу» включает запись, повторный тап по кнопке останавливает. Крестик слева вверху возвращает в очередь, ничего не решая.'],
        ['u_marks', 'Тап по слову — пометка ошибки',
         'В проверке тап по слову не показывает перевод, а отмечает его розовым: здесь ты не читаешь, а отмечаешь. Внизу счётчик — сколько слов отмечено. Тапнул ещё раз — снял. Эти пометки студент увидит на своём листе, в том же виде.'],
        ['u_comment', '🎙 Замечание — скажи голосом',
         'Записываешь разбор своим голосом: где ошибся, что поправить. Для «На пересдачу» замечание обязательно — вернуть работу молча значит оставить человека в тупике. Если нажмёшь пересдачу без записи, приложение само откроет запись, а не откажет.'],
        ['u_verdict', '✅ Принято или ↺ На пересдачу',
         '«Принято» — место закрыто, студент идёт дальше. «На пересдачу» — просишь начитать это же место заново, и следующий этап у него пока не откроется. Пометки слов уходят студенту в обоих случаях, вместе с голосом.'],
        ['u_done', '«Проверено» — что ты уже разобрал',
         'Твои разборы по дням, с пометками и голосом; фильтр «пересдачи» оставляет только возвращённые. Под такой строкой видно, ответил ли студент: «ждёт пересдачи» — ещё нет, «пересдал — новая запись в Ждут» — уже начитал заново, и она лежит в очереди. Старую запись переразбирать не нужно: она открывается только на просмотр.'],
        ['u_students', '«Студенты» — как идут дела',
         'Полоса под именем — месяц по дням: чем светлее столбик, тем меньше сдано в тот день. Рядом — пропуски. Тап по студенту открывает его карточку: что и когда он сдавал.']
      ]
    },

    /* «Правила» (07.10.2026, решение пользователя): студенты не знали, когда
       обнуляется серия, за что переводят, до скольки сдавать, как читать
       цвета месяца и как считаются отчёты - спорили с ботом и с устазом.
       Шесть коротких глав, каждая на свой вопрос, в своей карточке под
       «Как работать». Шаг без снимка - первый элемент null. Числа здесь
       те же, что в коде: STUDY_DAY_END_HOUR, EXCUSE_MONTHLY_LIMIT,
       MISS_THRESHOLDS, PREP_DAYS/PREP_MIN_DAYS, LESSON_MARKS_PER_WEEK -
       поменяли там, поправить здесь. */
    {
      id: 'r_day', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"4\" /><path d=\"M12 2v2\" /><path d=\"M12 20v2\" /><path d=\"m4.93 4.93 1.41 1.41\" /><path d=\"m17.66 17.66 1.41 1.41\" /><path d=\"M2 12h2\" /><path d=\"M20 12h2\" /><path d=\"m6.34 17.66-1.41 1.41\" /><path d=\"m19.07 4.93-1.41 1.41\" /></svg>", name: 'Учебный день',
      desc: 'Три задания, до трёх ночи, узр',
      steps: [
        [null, 'Три задания каждый день',
         'Заучивание 40+40, повторение и слова. У некоторых групп добавляются таджвид, нахв или хадис — что именно у твоей, видно на главном экране. Хафиз заучивание не сдаёт: у него повторение и слова. Всё сдаётся в приложении.'],
        [null, 'День длится до трёх ночи',
         'Сдал в 01:30 — это ещё вчерашний день, так удобно тем, кто учится ночью. В три часа ночи начинается новый день, и всё, что после, идёт уже в него.'],
        [null, 'Что считается сданным',
         'Заучивание — запись устазу из Мусхафа: строка, половина листа или лист. Повторение — перечитал с начала Аль-Бакары до своего места, нажал 🔁 и подтвердил. Слова — 40 слов в тренажёре, из них 20 верно; на первых страницах, где слов меньше, норма меньше. До 18 лет повторение сдаётся записью, а не кнопкой.'],
        [null, 'Узр — уважительная причина',
         'Заболел, в дороге, нет связи — напиши в своей группе «узр» и причину. Такой день не считается пропуском, но балла не даёт и серию не держит. До трёх узров в месяц; дальше день идёт как обычный пропуск.']
      ]
    },
    {
      id: 'r_points', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M6 3h12l4 6-10 13L2 9Z\" /><path d=\"M11 3 8 9l4 13 4-13-3-6\" /><path d=\"M2 9h20\" /></svg>", name: 'Баллы и серия',
      desc: 'За что сколько, почему серия обнулилась',
      steps: [
        [null, 'Баллы',
         'Каждое задание +1. Онлайн-урок +5. Неделя с понедельника по воскресенье без единого пропуска — ещё +5. Узр 0. Баллы не снимаются сами: снять может только устаз — аннулировав сдачу или отметку урока.'],
        [null, 'Серия 🔥 считает полные дни',
         'Серия — дни подряд, когда сданы ВСЕ задания дня. Сдал два из трёх — день в серию не идёт, и она начинается заново. Баллы при этом остаются, обнуляется только счётчик. Узр серию не спасает — она тоже начнётся заново. При переводе в другую группу серия идёт дальше.'],
        [null, 'Почему число в /rating падает',
         '/rating показывает только последние 7 дней. Старые дни выходят из окна, и число уменьшается само — ничего не снято. Все баллы за всё время — /mystats.']
      ]
    },
    {
      id: 'r_month', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M8 2v4\" /><path d=\"M16 2v4\" /><rect width=\"18\" height=\"18\" x=\"3\" y=\"4\" rx=\"2\" /><path d=\"M3 10h18\" /></svg>", name: 'Мой месяц',
      desc: 'Цвета дней, точка урока, запас',
      steps: [
        ['month', 'Что значит цвет дня',
         'Открой «Работа с устазом» и тапни по полоскам — раскроется месяц по дням. Тёмно-зелёный — сданы все задания. Зелёный посветлее — не хватило одного. Совсем светлый — не хватило двух и больше. Розоватый — в этот день ничего, и сегодняшний такой же, пока не сдал. Серый — день ещё не наступил. Тапни по неполному дню — под календарём покажу, что сдано и во сколько, чего не хватило и что ты делал в приложении в тот день. Устаз видит то же самое.'],
        [null, 'Точка под числом и запас',
         'Точка под днём — в этот день ты отметил онлайн-урок. Полоска «пропусков N из M» — запас месяца: красные чёрточки уже сгорели, пустые ещё есть. Сколько даёт группа — в главе «Пропуски и переводы».']
      ]
    },
    {
      id: 'r_misses', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M5 22h14\" /><path d=\"M5 2h14\" /><path d=\"M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22\" /><path d=\"M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2\" /></svg>", name: 'Пропуски и переводы',
      desc: 'Когда переводят в Тадаббур и как вернуться',
      steps: [
        [null, 'Что такое пропуск',
         'Пропуск — день, в который не сдано ничего и нет узра. Сдал хотя бы одно задание — это уже не пропуск, хотя в серию такой день не идёт. Считается с первого числа месяца.'],
        [null, 'Порог',
         'В про-группе 10 пропусков за месяц, в обычной 20 — и я перевожу в Тадаббур, из учебной группы выводят. Предупреждаю заранее в личку: в про-группе с пятого пропуска, в обычной с пятнадцатого.'],
        [null, 'Как вернуться',
         'Только через подготовительную группу: за 14 дней сдать 5 полных дней, когда есть все задания. Каждый полный день продлевает срок ещё на день. Набрал пять — я сам пришлю ссылку в учебную группу. Не набрал — остаёшься в Тадаббуре.'],
        [null, 'Переход в про-группу',
         'Если в обычной группе за 30 дней у тебя не больше трёх пропусков, раз в месяц я предложу перейти в про. Можно отказаться и остаться; предложение действует сутки.']
      ]
    },
    {
      id: 'r_lesson', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M4.9 16.1C1 12.2 1 5.8 4.9 1.9\" /><path d=\"M7.8 4.7a6.14 6.14 0 0 0-.8 7.5\" /><circle cx=\"12\" cy=\"9\" r=\"2\" /><path d=\"M16.2 4.8c2 2 2.26 5.11.8 7.47\" /><path d=\"M19.1 1.9a9.96 9.96 0 0 1 0 14.1\" /><path d=\"M9.5 18h5\" /><path d=\"m8 22 4-11 4 11\" /></svg>", name: 'Онлайн-урок',
      desc: 'Когда нажимать «Я был»',
      steps: [
        [null, 'Одна отметка в неделю',
         'Кнопка «Я был» — в «Работе с устазом». Нажимай только если урок был и ты на нём был. Одна отметка за неделю с понедельника по воскресенье, +5 баллов. Отмечай в день урока или на следующий: отметишь урок прошлой недели в понедельник — эта неделя будет занята.'],
        // 07.10.2026, решение пользователя: штраф −20 за лишнюю отметку
        // отменён - не все знали правило, а у Отбора два очных урока в неделю.
        // Лишнее нажатие сервер просто не засчитывает (LESSON_MARKS_PER_WEEK).
        [null, 'Отметка — аманат',
         'Сколько бы раз ты ни нажал «Я был», урок засчитывается один раз в неделю — лишние нажатия просто не считаются, без штрафа. Но помни: отметка — это аманат. Нажимай её, только когда действительно был на уроке. Если урока не было, устаз снимет отметку.']
      ]
    },
    {
      id: 'r_reports', group: 'rules', mark: "<svg class=\"ic\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\"><path d=\"M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z\" /><path d=\"M13 8H7\" /><path d=\"M17 12H7\" /></svg>", name: 'Отчёты и сообщения',
      desc: 'Что я пишу и как считаю',
      steps: [
        [null, 'Утро: кто сдал всё за вчера',
         'В семь утра в Тадаббур уходит список тех, кто вчера сдал все задания, со звёздочкой — сколько дней подряд. Кто сдал часть, в список не попадает, но баллы у него есть.'],
        [null, 'Понедельник: отчёт за неделю',
         'Очки — все баллы за семь дней: задания плюс бонусы за урок и за полную неделю. В скобках «дней» — дни, когда сдано хотя бы одно задание. Отдельно «+5 за постоянство» — кто прошёл неделю без пропуска. Первого числа — такой же отчёт за месяц.'],
        [null, 'Личные сообщения',
         'Утром: если вчера не сдано ничего — насыха; если не хватило одного задания — одна строка, чего именно. Три дня без сдачи — напоминание. Перед переводом — предупреждение. По одному поводу пишу не чаще раза в три дня.']
      ]
    }
  ];

  var LEARN_DONE_KEY = 'yassir_learn_done';
  var learnAt = null;          // {section, step} или null - значит оглавление

  function learnDone() {
    try { return JSON.parse(localStorage.getItem(LEARN_DONE_KEY) || '[]'); }
    catch (e) { return []; }
  }
  function learnMarkDone(id) {
    try {
      var done = learnDone();
      if (done.indexOf(id) < 0) { done.push(id); localStorage.setItem(LEARN_DONE_KEY, JSON.stringify(done)); }
    } catch (e) { /* приватный режим - галочка просто не запомнится */ }
  }

  // Тексты глав живут в LEARN по-русски; кыргызский и узбекский - в словаре
  // под ключами learn_<id>_name / _desc / _<шаг>_t / _<шаг>_b (16.10.2026).
  // Перевода нет - остаётся русский, как у T().
  function learnT(key, ru) {
    var d = I18N[UI_LANG];
    return (d && d[key] != null) ? d[key] : ru;
  }
  function learnName(sec) { return learnT('learn_' + sec.id + '_name', sec.name); }
  function learnStep(sec, k) {
    var s = sec.steps[k], p = 'learn_' + sec.id + '_' + k;
    return '<h3>' + learnT(p + '_t', s[1]) + '</h3><p>' + learnT(p + '_b', s[2]) + '</p>';
  }

  function learnPlural(n) {
    return T(n >= 2 && n <= 4 ? 'learn_steps_few' : 'learn_steps', { N: n });
  }

  /* Оглавление «Знаний» (11.09.2026) — два блока-карточки: объяснения
     приложения и уроки, которые выходят по четвергам.

     Блок именно карточка со строками внутри, а НЕ отдельный экран: экран на
     блок добавил бы третий тап до темы (Знания → Уроки → Таджвид → тема),
     а так их по-прежнему два. Приём тот же, что у карточек настроек
     (#sett .s-card) — в приложении он уже родной.

     Предметы внутри «Уроков» — плитками, а не строками: их ровно два, имена
     короткие, и выбор там равнозначный. Строки нужны там, где у пункта
     длинное имя и спутники справа (дата, замок, номер части) — то есть в
     списке самих уроков. */
  var lessonsCache = null;      // предметы со счётом, грузятся один раз за сеанс

  function learnRenderToc() {
    learnAt = null;
    var done = learnDone();
    document.getElementById('learn-title').textContent = T('learn_title');
    document.getElementById('learn-back').textContent = T(learnFromMore ? 'back_more' : 'back_dashboard');
    document.getElementById('learn-foot').style.display = 'none';

    // Уроки идут ПЕРВЫМИ (решение пользователя 11.09.2026, когда увидел
    // экран): за ними возвращаются каждую неделю, а объяснения приложения
    // читают один раз и потом заходят изредка. Блок рисуется заглушкой и
    // наполняется ответом — держать пустой экран, пока идёт сеть, незачем.
    // Нет у группы таджвида и нахва (14.09.2026) - блока «Уроки» нет вовсе,
    // а не пустая карточка. Знаем это из heartbeat ещё до запроса, поэтому
    // карточка не появляется, чтобы тут же пропасть.
    var noLessons = !!(dashFactsLast && dashFactsLast.learn && !dashFactsLast.learn.length);
    var html = noLessons ? '' : '<div class="k-card" id="k-lessons"><p class="k-head">'
      + T('learn_cap_lessons') + '<i>' + T('learn_lessons_note') + '</i></p>'
      + '<div class="k-tiles" id="k-subjects"></div></div>';

    // Две карточки из одного списка: «Как работать» (без group) и «Правила»
    // (group: 'rules', 07.10.2026). Правила ниже: их читают, когда возник
    // вопрос, а объяснения экранов - с первого дня.
    function learnCard(cap, group) {
      var out = '<div class="k-card"><p class="k-head">' + T(cap) + '</p>';
      LEARN.forEach(function (sec, i) {
        if ((sec.group || null) !== group) return;
        if (sec.ustaz && !meIsUstaz) return;   // у студента такого экрана нет
        var empty = !sec.steps.length;
        var right = empty ? T('learn_soon')
          : (done.indexOf(sec.id) >= 0
              ? '<span class="done">✓ ' + T('learn_read') + '</span>'
              : (group === 'rules' ? ''                                       // правила - страница, не шаги
                 : sec.video ? learnT('learn_video_badge', '▶ видео')
                 : learnPlural(sec.steps.length)));
        out += '<button class="learn-item"' + (empty ? ' disabled style="opacity:.55"' : ' data-sec="' + i + '"') + '>' +
          '<span class="mk">' + sec.mark + '</span>' +
          '<span><span class="nm">' + learnName(sec) + '</span>' +
          '<span class="ds">' + learnT('learn_' + sec.id + '_desc', sec.desc) + '</span></span>' +
          '<span class="cnt">' + right + '</span></button>';
      });
      return out + '</div>';
    }
    html += learnCard('learn_cap_how', null) + learnCard('learn_cap_rules', 'rules');


    var body = document.getElementById('learn-body');
    body.innerHTML = html;
    Array.prototype.forEach.call(body.querySelectorAll('[data-sec]'), function (b) {
      b.addEventListener('click', function () {
        var si = parseInt(b.getAttribute('data-sec'), 10);
        if (LEARN[si].video) learnRenderVideo(si);
        else learnRenderStep(si, 0);
      });
    });

    if (lessonsCache) return lessonsRenderSubjects(lessonsCache);
    apiCall('/lessons').then(function (res) {
      var d = res && res.data;
      lessonsCache = (d && d.subjects) || [];
      lessonsRenderSubjects(lessonsCache);
    }).catch(function () { lessonsRenderSubjects([]); });
  }

  // «13 августа» вместо «2026-08-13»: дата урока - это «когда прошли», а не
  // отметка в журнале.
  function lessonDate(at) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(at || '');
    if (!m) return at || '';
    return T('lesson_date', { D: parseInt(m[3], 10), M: T('month_' + parseInt(m[2], 10)) });
  }

  // Название и подпись предмета приходят с сервера по-русски (core/lessons.py);
  // на языке интерфейса - из словаря, иначе как пришло (27.10.2026, скрин zh).
  var SUBJ_TITLE_KEY = { j: 'tajweed_title', n: 'nahw_title' };

  /* Значок предмета (12.11.2026): иконка вместо эмодзи с сервера (📘/📗),
     таджвид синий, нахв зелёный - одинаково в «Знаниях» и на вкладке «Устаз». */
  function subjMark(id) {
    return '<span class="t-mk mk-' + id + '">' + (id === 'j' ? ICON['book-open-text'] : ICON['graduation-cap']) + '</span>';
  }
  function lessonsRenderSubjects(subjects) {
    var box = document.getElementById('k-subjects');
    if (!box) return;                      // ушли с оглавления, пока грузилось
    if (!subjects.length) {
      // Показывать нечего - убираем блок целиком, пустая карточка с
      // обещанием «появятся» у группы без предметов вводит в заблуждение.
      var card = document.getElementById('k-lessons');
      if (card) card.parentNode.removeChild(card);
      return;
    }
    box.innerHTML = subjects.map(function (s) {
      return '<button class="k-tile" data-subj="' + s.id + '">'
        + subjMark(s.id)
        + '<span class="t-nm">' + (T(SUBJ_TITLE_KEY[s.id]) || s.title) + '</span>'
        + '<span class="t-ds">' + (T('subj_' + s.id + '_sub') || s.sub) + '</span>'
        + '<span class="t-cnt">' + T('learn_open_of', { N: s.open, M: s.total }) + '</span>'
        + '</button>';
    }).join('');
    Array.prototype.forEach.call(box.querySelectorAll('[data-subj]'), function (b) {
      b.addEventListener('click', function () {
        lessonsRenderList(b.getAttribute('data-subj'));
      });
    });
  }

  // Список частей предмета: строками, сгруппированными по главам. Закрытый
  // урок виден с названием, но приглушён и не нажимается — видно, что
  // впереди (решение пользователя 11.09.2026).
  function lessonsRenderList(subject) {
    var meta = (lessonsCache || []).filter(function (s) { return s.id === subject; })[0] || {};
    learnAt = { lessons: subject };
    document.getElementById('learn-title').textContent = T(SUBJ_TITLE_KEY[subject]) || meta.title || '';
    document.getElementById('learn-back').textContent = T('learn_back_toc');
    document.getElementById('learn-foot').style.display = 'none';
    var body = document.getElementById('learn-body');
    body.innerHTML = '<p class="k-empty">…</p>';

    apiCall('/lessons?subject=' + encodeURIComponent(subject)).then(function (res) {
      var items = (res && res.data && res.data.items) || [];
      if (!items.length) { body.innerHTML = '<p class="k-empty">' + T('lessons_empty') + '</p>'; return; }
      var html = '', chapter = null, n = 0, firstClosed = true;
      items.forEach(function (it) {
        if (it.chapter !== chapter) {
          chapter = it.chapter;
          html += '<p class="k-cap">' + feedEsc(chapter) + '</p>';
        }
        n += 1;
        // ▶ у открытого урока с видеоуроком (10.11.2026).
        var right = it.open ? (it.video ? ICON.play : '') : ICON.lock;
        // «Откроется в четверг» — только у ближайшего закрытого: у всех
        // остальных это было бы неправдой.
        var desc = it.open ? lessonDate(it.at)
          : (firstClosed ? T('lesson_locked_soon') : T('lesson_locked'));
        if (!it.open) firstClosed = false;
        var topic = it.parts > 1
          ? it.topic + ' · ' + T('lesson_part_of', { N: it.part, M: it.parts })
          : it.topic;
        html += '<button class="learn-item' + (it.open ? '' : ' k-off') + '"'
          + (it.open ? ' data-lesson="' + it.id + '"' : ' disabled') + '>'
          + '<span class="mk">' + n + '</span>'
          + '<span><span class="nm">' + feedEsc(topic) + '</span>'
          + '<span class="ds">' + feedEsc(desc) + '</span></span>'
          + '<span class="cnt">' + right + '</span></button>';
      });
      body.innerHTML = html;
      var revGo = document.getElementById('subs-rev-go');
      if (revGo) revGo.addEventListener('click', function () {
        // Ведём туда же, куда 🔁 на странице чтения: мусхаф, первая страница
        // Аль-Бакары, панель записи (16.09.2026).
        document.getElementById('subs').style.display = 'none';
        openMushaf('page');
        setTimeout(function () { revisionRecOpen(); }, 700);
      });
      body.scrollTop = 0;
      Array.prototype.forEach.call(body.querySelectorAll('[data-lesson]'), function (b) {
        b.addEventListener('click', function () {
          lessonsRenderOne(subject, b.getAttribute('data-lesson'));
        });
      });
    }).catch(function () { body.innerHTML = '<p class="k-empty">' + T('lessons_empty') + '</p>'; });
  }

  var LESSON_AR_RUN = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+(?:[ \u00A0\u200C]+[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+)*/g;
  function lessonArabic(html) {
    return html.replace(LESSON_AR_RUN, function (m) { return '<span class="k-ar">' + m + '</span>'; });
  }

  function lessonsRenderOne(subject, id) {
    var body = document.getElementById('learn-body');
    body.innerHTML = '<p class="k-empty">…</p>';
    apiCall('/lesson?id=' + encodeURIComponent(id)).then(function (res) {
      var d = res && res.data;
      if (!d || !d.content) { return lessonsRenderList(subject); }
      learnAt = { lesson: subject };
      document.getElementById('learn-title').textContent = d.topic;
      document.getElementById('learn-back').textContent = '← '
        + (T(SUBJ_TITLE_KEY[subject])
           || ((lessonsCache || []).filter(function (s) { return s.id === subject; })[0] || {}).title
           || '');
      // Видеоурок (10.11.2026): ролик с YouTube над текстом, тот же плеер и те же
      // параметры, что у видео-инструкций «Как работать» (learnRenderVideo). Id
      // приходит с сервера (core/lessons.py, LESSON_VIDEOS) - по номеру урока.
      var video = d.video
        ? '<div class="learn-video"><iframe src="https://www.youtube-nocookie.com/embed/'
          + encodeURIComponent(d.video) + '?playsinline=1&rel=0&modestbranding=1" title="'
          + feedEsc(d.topic) + '" allow="autoplay; encrypted-media; picture-in-picture; fullscreen"'
          + ' allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></div>'
        : '';
      body.innerHTML = video + '<div class="k-text"><p class="k-chapter">' + feedEsc(d.chapter)
        + (d.parts > 1 ? ' · ' + T('lesson_part_of', { N: d.part, M: d.parts }) : '')
        + '</p>' + lessonArabic(feedEsc(d.content)) + '</div>';
      body.scrollTop = 0;
    }).catch(function () { lessonsRenderList(subject); });
  }

  /* Глава «Правил» - одной страницей (07.10.2026, после снимка на телефоне:
     правило короткое, экран на абзац оставлял две трети пустоты). Правила
     читают как справку, а не проходят как путь: все пункты подряд, со
     снимком там, где он есть, внизу одна кнопка «Готово». Шаги-снимки
     онбординга остаются по одному на экран - там важно довести до конца. */
  /* Снимок экрана к шагу - на языке интерфейса (28.10.2026, аудит zh: под
     китайским текстом стояли русские экраны). Снимает scripts/
     shoot_onboarding.py --lang; нет снимка своего языка - берём русский. */
  var LEARN_SHOT_LANGS = ['ky', 'uz', 'zh'];
  function learnShotImg(name) {
    var ru = 'onboarding/' + name + '.jpg';
    if (LEARN_SHOT_LANGS.indexOf(UI_LANG) < 0) return '<img alt="" src="' + ru + '">';
    return '<img alt="" src="onboarding/' + UI_LANG + '/' + name + '.jpg"'
      + ' onerror="this.onerror=null;this.src=\'' + ru + '\'">';
  }

  function learnRenderArticle(si) {
    var sec = LEARN[si];
    learnAt = { section: si, step: 0 };
    document.getElementById('learn-title').textContent = learnName(sec);
    document.getElementById('learn-back').textContent = T('learn_back_toc');
    var html = '<div id="learn-step" class="text article">';
    sec.steps.forEach(function (s, k) {
      html += '<section>' +
        (s[0] ? '<div class="shot">' + learnShotImg(s[0]) + '</div>' +
                '<p class="learn-zoomhint">' + T('learn_zoom') + '</p>' : '') +
        learnStep(sec, k) + '</section>';
    });
    var body = document.getElementById('learn-body');
    body.innerHTML = html + '</div>';
    body.scrollTop = 0;
    Array.prototype.forEach.call(body.querySelectorAll('.shot'), function (shot) {
      shot.addEventListener('click', function () {
        var zoom = document.getElementById('learn-zoom');
        zoom.querySelector('img').src = shot.querySelector('img').src;
        zoom.classList.add('visible');
      });
    });
    document.getElementById('learn-dots').innerHTML = '';
    document.getElementById('learn-prev').style.display = 'none';
    document.getElementById('learn-next').textContent = T('learn_done');
    document.getElementById('learn-foot').style.display = '';
    learnMarkDone(sec.id);
  }

  /* Видео-инструкция раздела (27.10.2026, решение пользователя): ролик
     сверху, под ним кнопка на прежние шаги со снимками - их не убрали, кому-то
     удобнее листать, а на ky/uz шаги переведены, ролик - нет.

     Плеер - youtube-nocookie, playsinline: играет на странице, а не уходит в
     полноэкранный плеер iOS; rel=0 - в конце предлагаются ролики только
     нашего канала. referrerpolicy обязателен: без адреса страницы YouTube
     отказывается играть встроенный ролик (ошибка 153).

     learnAt.step = -1: шаг «до первого», поэтому свайп и «Дальше» отсюда
     ведут на шаг 0, а «Назад» с шага 0 - обратно сюда (learnStepBy).
     Уход с экрана заменяет #learn-body - вместе с iframe останавливается и
     звук. Глава отмечается прочитанной при открытии, как страница «Правил». */
  function learnRenderVideo(si) {
    var sec = LEARN[si];
    learnAt = { section: si, step: -1 };
    document.getElementById('learn-title').textContent = learnName(sec);
    document.getElementById('learn-back').textContent = T('learn_back_toc');
    document.getElementById('learn-foot').style.display = 'none';
    var src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(sec.video)
      + '?playsinline=1&rel=0&modestbranding=1';
    var body = document.getElementById('learn-body');
    body.innerHTML =
      '<div class="learn-video"><iframe src="' + src + '" title="' + feedEsc(learnName(sec)) + '"'
      + ' allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen'
      + ' referrerpolicy="strict-origin-when-cross-origin"></iframe></div>'
      + '<button class="learn-item" id="learn-video-steps">'
      + '<span class="mk">' + sec.mark + '</span>'
      + '<span><span class="nm">' + learnT('learn_video_steps', 'Пошагово со снимками') + '</span>'
      + '<span class="ds">' + learnPlural(sec.steps.length) + '</span></span>'
      + '<span class="cnt">›</span></button>';
    body.scrollTop = 0;
    document.getElementById('learn-video-steps').addEventListener('click', function () {
      learnRenderStep(si, 0);
    });
    learnMarkDone(sec.id);
  }

  function learnRenderStep(si, step) {
    var sec = LEARN[si];
    if (sec.group === 'rules') return learnRenderArticle(si);
    learnAt = { section: si, step: step };
    var s = sec.steps[step], last = step === sec.steps.length - 1;
    document.getElementById('learn-title').textContent =
      learnName(sec) + ' \u00b7 ' + T('learn_of', { N: step + 1, M: sec.steps.length });
    document.getElementById('learn-back').textContent = T('learn_back_toc');
    var body = document.getElementById('learn-body');
    // Шаг без снимка (главы «Правила», 07.10.2026): только заголовок и текст.
    body.innerHTML =
      '<div id="learn-step"' + (s[0] ? '' : ' class="text"') + '>' +
      (s[0] ? '<div class="shot">' + learnShotImg(s[0]) + '</div>' +
              '<p class="learn-zoomhint">' + T('learn_zoom') + '</p>' : '') +
      learnStep(sec, step) + '</div>';
    body.scrollTop = 0;
    var dots = '';
    sec.steps.forEach(function (_, i) { dots += '<i' + (i === step ? ' class="on"' : '') + '></i>'; });
    document.getElementById('learn-dots').innerHTML = dots;
    document.getElementById('learn-prev').style.display = step ? '' : 'none';
    document.getElementById('learn-next').textContent = last ? T('learn_done') : T('learn_next');
    document.getElementById('learn-foot').style.display = '';
    // Мелкий шрифт на снимке не прочитать - по тапу показываем его целиком.
    if (s[0]) body.querySelector('.shot').addEventListener('click', function () {
      var zoom = document.getElementById('learn-zoom');
      zoom.querySelector('img').src = body.querySelector('.shot img').src;
      zoom.classList.add('visible');
    });
    if (last) learnMarkDone(sec.id);
  }

  function learnStepBy(delta) {
    if (!learnAt) return;
    var sec = LEARN[learnAt.section], next = learnAt.step + delta;
    if (sec.group === 'rules') return learnRenderToc();   // глава-страница: «Готово» - в оглавление
    if (next === -1 && sec.video) return learnRenderVideo(learnAt.section);   // с шага 0 - к ролику
    // Край в любую сторону возвращает в оглавление: «назад» с первого шага и
    // «Готово» с последнего ведут в одно и то же место, откуда любой раздел
    // открывается одним тапом.
    if (next < 0 || next >= sec.steps.length) return learnRenderToc();
    learnRenderStep(learnAt.section, next);
  }

  // Из оглавления «Знаний» возвращаемся туда, откуда пришли: с дашборда - на
  // дашборд, из вкладки «Ещё» - в «Ещё» (04.11.2026, нижняя панель).
  var learnFromMore = false;
  function openLearn(fromMore) {
    learnFromMore = fromMore === true;
    document.getElementById('dashboard').style.display = 'none';
    document.getElementById('more').style.display = 'none';
    document.getElementById('learn').style.display = 'flex';
    learnRenderToc();
  }

  document.getElementById('dash-learn').addEventListener('click', function () { openLearn(false); });

