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
journalctl --user -u yassir-bot-female -n 50  # логи женского
```
