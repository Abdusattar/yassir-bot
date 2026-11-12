# Карта вики: что где лежит по блокам Яссира

Вики — по темам («как устроено и почему»), логи `logs/terminal/` — по датам («что было
в этот день»). Чтобы находить работу по блоку, а не по дате:

- **Вики:** найти блок ниже → открыть файл.
- **Логи:** каждый раздел лога начинается с метки блока в квадратных скобках, из списка
  ниже: `## [Мусхаф] шрифты на свой сервер`. Вся история блока одной командой:
  `grep -rn "\[Мусхаф\]" logs/terminal/`.
- В разделе лога — ссылка на файл вики, куда ушло долгосрочное знание.

Новый файл вики — сразу строкой в эту карту. Новая метка — сначала сюда.

| Метка в логах | Что это | Файлы вики |
|---|---|---|
| `[Мусхаф]` | лист, шрифты, раскладки, подгонка, подсказка по слову, смысл | `mushaf_yassirapp.md`, `ux_today_mushaf_proposal.md` |
| `[Заучивание]` | 40+40, запись сдачи, Хусари | `mushaf_yassirapp.md`, `hifz_audio_husary.md` |
| `[Устаз]` | проверка сдач, кабинет устаза, отчёты | `voice_review.md`, `weekly_reports.md` |
| `[Тренажёры]` | слова (муфрадат), таджвид, нахв, хадисы, рейтинг | `mufradat_trainer.md`, `leaderboard.md`, `curriculum.md` |
| `[Перевод]` | пословный и смысловой перевод, языки ky/uz/zh | `wbw_ru_method.md`, `i18n.md`, `chinese_zh.md` |
| `[Приложение]` | «Сегодня», лента, «Знания», вход, общая оболочка | `app_direction.md`, `login_without_telegram.md`, `newcomer_path.md` |
| `[Баллы]` | баллы, стрик, пропуски, узр, детекция отчётов | `scoring.md`, `skip_counting.md`, `excuse_detection.md`, `report_detection.md`, `ai_verification.md` |
| `[Группы]` | типы групп, prep, регистрация, рассылки, личные сообщения | `group_types.md`, `prep_group.md`, `registration_flow.md`, `engagement_broadcasts.md`, `dm_reachability.md` |
| `[Боты]` | два бота, один вход, сервер, деплой, nginx, безопасность | `infrastructure.md`, `one_bot.md`, `hacked_accounts.md` |
| `[ИИ]` | ИИ-таджвид по аудио, модели, расходы | `ai_tajweed_audio.md`, `ai_costs.md`, `ai_reasoning_models_max_tokens.md` |
| `[Контент]` | Тадаббур, насыхи, сито источников | `tadabbur_post_philosophy.md`, `tadabbur_audience.md`, `content_sieve_methodology.md` |
| `[Команда]` | как работаем вместе, архитектура, планы на согласовании | `team_workflow.md`, `index_split_plan.md` (исходники `app_src/` и сборка), `architecture_roadmap.md`, `architecture_roadmap_review.md` |
