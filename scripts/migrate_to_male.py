"""
Миграция групп и студентов из quran_wa.db → quran_male.db
Женская группа (-4960876249) пропускается.
"""
import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')

SRC = os.path.join(os.path.dirname(__file__), '..', 'quran_wa.db')
DST = os.path.join(os.path.dirname(__file__), '..', 'quran_male.db')

FEMALE_CHAT_ID = "-4960876249"

src = sqlite3.connect(SRC)
src.row_factory = sqlite3.Row

# Инициализируем новую БД через штатный init
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['BOT_PROFILE'] = 'male'
os.environ['DB_PATH'] = DST
from core.db import init, save_group, add_student, get_group, get_students

init()

sc = src.cursor()
groups = sc.execute("SELECT * FROM groups WHERE active=1").fetchall()

migrated_groups = 0
migrated_students = 0
skipped_students = 0

for g in groups:
    chat_id = str(g['chat_id'])
    if chat_id == FEMALE_CHAT_ID:
        print(f"⏭  Пропускаем женскую группу: {chat_id}")
        continue

    title = g['title'] or chat_id
    tasks = g['tasks'] or 'm,r,t'
    lang = g['lang'] if 'lang' in g.keys() else 'ru'

    # Проверяем не существует ли уже
    existing = get_group(chat_id)
    if existing:
        print(f"⚠️  Группа уже есть: {chat_id} ({title})")
    else:
        save_group(chat_id, title, tasks)
        print(f"✅ Группа добавлена: {chat_id}  tasks={tasks}")
    migrated_groups += 1

    # Получаем ID группы в новой БД
    new_group = get_group(chat_id)
    if not new_group:
        print(f"  ❌ Не удалось найти группу {chat_id} в новой БД")
        continue

    # Студенты
    students = sc.execute(
        "SELECT * FROM students WHERE group_id=? AND active=1", (g['id'],)
    ).fetchall()

    existing_students = {s['name'] for s in get_students(new_group['id'])}

    for s in students:
        if s['name'] in existing_students:
            print(f"  ⚠️  {s['name']} уже есть")
            skipped_students += 1
            continue
        phone = str(s['phone']) if s['phone'] else None
        add_student(s['name'], new_group['id'], phone)
        tag = f"  phone={phone}" if phone else "  (без ID)"
        print(f"  👤 {s['name']}{tag}")
        migrated_students += 1

src.close()
print(f"\n{'='*50}")
print(f"Группы добавлены: {migrated_groups}")
print(f"Студентов добавлено: {migrated_students}")
print(f"Студентов пропущено (уже есть): {skipped_students}")
print("\nГотово! Теперь запусти /settype и /settasks в каждой группе если нужно.")
