# Настройка сервера (копия из прода)

Здесь лежит то, что раньше жило только на сервере (wiki/architecture.md, долг П4, закрыт 14.11.2026).
Руками эти файлы не правятся: меняем на сервере, потом `python scripts/server_config.py`
снимает копию, и она коммитится. Сверка без записи: `python scripts/server_config.py --check`.

| Файл | Где на сервере | Что это |
|---|---|---|
| `nginx/yassir-app` | `/etc/nginx/sites-available/yassir-app` | сайт yassirilm.com: раздача приложения, API обеих половин |
| `nginx/nginx.conf` | `/etc/nginx/nginx.conf` | общие настройки, сжатие |
| `systemd/yassir-bot.service` | `/etc/systemd/system/` | мужской бот (системная служба) |
| `systemd/yassir-bot-female.service` | `/home/stursunkul/.config/systemd/user/` | женский бот (служба пользователя) |
| `sudoers/*` | `/etc/sudoers.d/` | что деплою разрешено без пароля |
| `crontab.txt` | cron пользователя `stursunkul` | ночная копия баз, наблюдение |

Секретов здесь нет: ключи и токены - в `.env` и `.env.female` на сервере, в git не попадают.

## Поднять машину заново (кратко)

1. Пользователь `stursunkul`, код в `/home/stursunkul/yassir-bot` (`git clone`), `venv`, `pip install -r requirements.txt`.
2. `.env` и `.env.female` (права 600) - из закрытого хранения; базы - из последней копии (`scripts/backup_db.py`, `scripts/pull_backup.py`).
3. Файлы этой папки - по местам из таблицы; `crontab crontab.txt`; сертификат - `certbot --nginx`.
4. `/var/www/yassir-app`: ссылки на `mushaf_data/` (их ставит `.github/workflows/deploy.yml`) и листы `page*.json` (`~/scripts/link_mushaf_pages.sh`).
5. Пуш в `master` - выкатка: соберёт переводы и список отпечатков, перезапустит обоих ботов.

Подробности и грабли - `wiki/infrastructure.md`.
