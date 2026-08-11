# Инфраструктура — управление ботом

## Два бота — норма

На сервере всегда **два** процесса `python3 bot.py`:

| BOT_PROFILE | БД | systemd |
|---|---|---|
| male | quran_male.db | системный `yassir-bot.service` |
| female | quran_female.db | user-level `yassir-bot-female.service` |

Проверить: `cat /proc/<PID>/environ | tr '\0' '\n' | grep BOT_PROFILE`

Конфликт 409 — только если оба с одинаковым профилем (т.е. дубль одного и того же бота).

## Деплой мужского бота

Репозиторий на сервере (`/home/stursunkul/yassir-bot`) принадлежит `stursunkul`,
а SSH-доступ у Claude — под `claude-access` (другой linux-юзер). Обычный `git pull`
падает с `Permission denied` на `.git/FETCH_HEAD`. Пуллить нужно от имени владельца:

```bash
ssh -i ~/.ssh/claude_gcp claude-access@34.51.213.67 \
  "sudo -u stursunkul git -C /home/stursunkul/yassir-bot pull && sudo /bin/systemctl restart yassir-bot"
```

`claude-access` имеет `sudo NOPASSWD: ALL` — это не проблема прав, а просто нужно не забыть `-u stursunkul`.

**Никогда** `systemctl --user` для мужского бота — user-level сервис отключён.

## sudo без пароля (разрешено)

```bash
sudo /bin/systemctl restart yassir-bot
sudo /bin/systemctl stop yassir-bot
sudo /bin/systemctl start yassir-bot
```

`status`, `disable`, `enable`, `loginctl` — требуют пароль (нет доступа).

## Диагностика

```bash
ps -f -C python3 | grep bot.py          # сколько ботов (должно быть 2: male + female)
journalctl -u yassir-bot -n 50          # логи мужского
```

## Управление женским ботом (user-level systemd, проверено 02.08.2026)

`claude-access` не является владельцем сессии `stursunkul`, поэтому голый
`sudo -u stursunkul systemctl --user ...` падает с `Failed to connect to
bus: Permission denied`. Рабочая форма — явно указать `XDG_RUNTIME_DIR`:

```bash
sudo -u stursunkul XDG_RUNTIME_DIR=/run/user/$(id -u stursunkul) \
  systemctl --user restart yassir-bot-female
sudo -u stursunkul XDG_RUNTIME_DIR=/run/user/$(id -u stursunkul) \
  systemctl --user status yassir-bot-female --no-pager -l
sudo -u stursunkul XDG_RUNTIME_DIR=/run/user/$(id -u stursunkul) \
  journalctl --user -u yassir-bot-female -n 50
```

Работает, потому что `linger` включён для `stursunkul` (сервис живёт без
активной login-сессии) — без linger даже с `XDG_RUNTIME_DIR` не завелось бы.

## Женский бот делит код с мужским (обнаружено 02.08.2026)

`yassir-bot-female.service` (`/home/stursunkul/.config/systemd/user/`) имеет
`WorkingDirectory=/home/stursunkul/yassir-bot` — ТУ ЖЕ директорию, что и
мужской системный сервис, просто другой `EnvironmentFile=.env.female`. Это
значит: `git pull`, который выполняет деплой мужского бота (GitHub Actions
на каждый push), **уже обновляет файлы и для женского** — но женский
процесс не подхватит изменения без отдельного рестарта (Python читает
модули один раз при старте).

**Практическое следствие**: после пуша в мужской бот код женского на диске
тоже свежий, но реально запущенный процесс — нет, пока его не
перезапустить вручную (см. команду выше). Обнаружено, когда женский процесс
оказался запущен с **26.07** — неделю без единого рестарта, то есть без
всех фиксов, включая целую фичу с 31.07 (баллы за «у»). Перед плановым
рестартом стоит проверять `ps -eo pid,lstart,cmd | grep bot.py` — если
female-PID стартовал задолго до последнего мужского деплоя, код устарел.

## Часовой пояс: created_at (UTC) vs date (Asia/Bishkek) — не бизнес-правило

`score_events.created_at` пишется через SQLite `datetime('now')` — это
**UTC**. Колонка `date` пишется отдельно, через `get_date()`
(`core/db.py`), которая использует `TZ = Asia/Bishkek` (UTC+6).

Из-за этого у вечерних/ночных сдач `date` оказывается на день позже, чем
можно ожидать по `created_at` — например, `created_at 2026-07-07 18:06:30`
соответствует `date = '2026-07-08'`. На первый взгляд это выглядит как
намеренное правило «учебный день начинается вечером» (как исламский
календарный день, начинающийся с Магриба), но это **просто артефакт
часового пояса хранения одной конкретной колонки**, не осознанная логика.

Найдено 12.08.2026 при фиксе `/rating` — эдвайзери сначала заподозрил,
что новая верхняя граница `date<=today` обрежет вечерние сдачи из-за
этого расхождения. Проверено на примере точно на границе (18:06 UTC =
00:06 местного, Bishkek) — подтвердило чисто арифметику часового пояса,
не бизнес-правило. `date` сама по себе — надёжные локальные календарные
данные (уже посчитана правильно через `get_date()`); нужно аккуратно
именно с `created_at`, если сравнивать её с локальным временем.

## users.phone — это Telegram ID, а не реальный номер телефона

Поле `phone` в таблицах `users`/`students` (и аргумент `phone` в
`core/tg.py` → `send_message`/`send_dm.py`) в большинстве случаев хранит
**числовой Telegram ID**, а не набираемый номер телефона —
`send_message` делает `int(str(chat_id))` и передаёт значение прямо в
Bot API как `chat_id`.

Реальный номер телефона студента (например, `+996505042513`) почти
никогда не совпадёт с тем, что лежит в `users.phone` (например,
`8973606493`) — **это ожидаемо, не ошибка данных**. Найдено 12.08.2026:
пытались сверить реальный номер, с которого позвонил студент, с базой —
не совпал, хотя человек тот же самый.

**Практическое следствие**: чтобы подтвердить личность студента по
реальному номеру телефона, `users.phone` для этого не годится — сверять
по имени/группе. Значение `users.phone` (какое бы оно ни было) годится
только как маршрутный ключ для `send_dm.py`/`send_message`, не как
предъявляемый пользователю или сверяемый вручную номер.
