# Подготовительная группа (prep)

## Суть

Испытательный период: студент вступает в подготовительную группу, у него есть 14 дней.  
Если сдаёт ≥5 дней отчётов — выбирает, в какую relaxed-группу перейти (по языку).  
Если <5 дней — остаётся в Тадаббуре, в учебную группу не переводится.

Задания те же что в relaxed (m, r, t).

## Параметры (core/prep.py)

```python
PREP_DAYS = 14       # дней на испытание
PREP_MIN_DAYS = 5    # минимум дней с отчётом для прохода
```

## Расписание (scheduler.py)

| Время | Действие |
|---|---|
| 07:00 | `send_prep_reminders()` — напоминание в prep-группу |
| 21:00 | `check_prep_students()` — проверка у кого истёк срок |

## Флоу 21:00 — check_prep_students

1. `get_prep_students_due()` — студенты в prep-группах, joined_date ≥ 14 дней назад
2. `count_report_days_since(uid, group_id, joined_date)` — сколько дней с отчётом
3. **≥5 дней**: `_send_choice()` — поздравление + inline кнопки выбора языка
4. **<5 дней**: `_deactivate_from_prep()` — деактивация + сообщение `prep_failed`

## Выбор языка (callback_query)

- Кнопки: "Кыргызский 🇰🇬" → `prep_lang:ky`, "Русский 🇷🇺" → `prep_lang:ru`
- Обработчик `handle_prep_callback(cq)` в `core/prep.py`
- Находит наименьшую relaxed-группу с нужным языком у которой есть invite_link
- Деактивирует студента из prep
- Отправляет ссылку на группу в личку студенту

## Напоминание 07:00 — send_prep_reminders

Для каждой prep-группы одно сообщение:
- **Активные** (сдавали ≥1 день): список имён
- **Пассивные** (0 дней): список имён

Тексты: `prep_reminder_active`, `prep_reminder_inactive` из i18n.

## in-memory состояние

```python
_pending_lang_choice: dict = {}  # {uid: {group_id, name, glang, joined_date}}
```

Заполняется в `_send_choice`, читается в `handle_prep_callback`.  
Живёт в памяти (не в БД) — при перезапуске бота теряется.

## invite_link

- Хранится в `groups.invite_link` (TEXT)
- Добавлен через `ALTER TABLE groups ADD COLUMN invite_link TEXT` при `init()`
- Устаз сохраняет: `/setlink https://t.me/+xxx`
- `get_relaxed_groups_by_lang(lang)` возвращает relaxed-группы с invite_link, sorted по количеству студентов ASC
