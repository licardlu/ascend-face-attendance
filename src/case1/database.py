import sqlite3
import os
from datetime import datetime, timedelta, timezone

DB_NAME = 'attendance.db'
BEIJING_TZ = timezone(timedelta(hours=8))
BEIJING_MIGRATION_KEY = 'utc_to_beijing_v1'


def get_beijing_now():
    return datetime.now(BEIJING_TZ)


def format_timestamp(dt):
    return dt.astimezone(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')


def get_beijing_date():
    return get_beijing_now().strftime('%Y-%m-%d')


def utc_text_to_beijing_text(timestamp):
    try:
        parsed = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return timestamp

    return format_timestamp(parsed.replace(tzinfo=timezone.utc))


def migrate_existing_utc_timestamps(c):
    c.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    c.execute('SELECT value FROM metadata WHERE key = ?', (BEIJING_MIGRATION_KEY,))
    if c.fetchone():
        return

    c.execute('SELECT id, created_at FROM users')
    for user_id, created_at in c.fetchall():
        c.execute(
            'UPDATE users SET created_at = ? WHERE id = ?',
            (utc_text_to_beijing_text(created_at), user_id)
        )

    c.execute('SELECT id, timestamp FROM attendance')
    for attendance_id, timestamp in c.fetchall():
        c.execute(
            'UPDATE attendance SET timestamp = ? WHERE id = ?',
            (utc_text_to_beijing_text(timestamp), attendance_id)
        )

    c.execute(
        'INSERT INTO metadata (key, value) VALUES (?, ?)',
        (BEIJING_MIGRATION_KEY, format_timestamp(get_beijing_now()))
    )

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # User table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            embedding BLOB,
            avatar TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Attendance table
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            type TEXT,
            image_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    migrate_existing_utc_timestamps(c)

    conn.commit()
    conn.close()

def add_user(name, embedding, avatar=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    created_at = format_timestamp(get_beijing_now())
    c.execute(
        'INSERT INTO users (name, embedding, avatar, created_at) VALUES (?, ?, ?, ?)',
        (name, embedding, avatar, created_at)
    )
    user_id = c.lastrowid
    conn.commit()
    conn.close()
    return user_id

def update_user_name(user_id, name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE users SET name = ? WHERE id = ?', (name, user_id))
    conn.commit()
    conn.close()

def get_users():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM users ORDER BY id ASC')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return users

def delete_user(user_id):
    delete_users([user_id])


def delete_users(user_ids):
    normalized_ids = []
    for user_id in user_ids:
        try:
            normalized_ids.append(int(user_id))
        except (TypeError, ValueError):
            continue

    normalized_ids = sorted(set(normalized_ids))
    if not normalized_ids:
        return 0

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    placeholders = ','.join(['?'] * len(normalized_ids))
    c.execute(f'DELETE FROM attendance WHERE user_id IN ({placeholders})', normalized_ids)
    c.execute(f'DELETE FROM users WHERE id IN ({placeholders})', normalized_ids)
    deleted = c.rowcount
    conn.commit()
    conn.close()
    return deleted

def add_attendance(user_id, checkin_type, image_path):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now = get_beijing_now()
    today = now.strftime('%Y-%m-%d')
    c.execute('BEGIN IMMEDIATE')
    c.execute('''
        SELECT *
        FROM attendance
        WHERE user_id = ? AND substr(timestamp, 1, 10) = ?
        ORDER BY timestamp ASC, id ASC
        LIMIT 1
    ''', (user_id, today))
    existing = c.fetchone()
    if existing:
        result = dict(existing)
        result['created'] = False
        conn.commit()
        conn.close()
        return result

    timestamp = format_timestamp(now)
    c.execute(
        'INSERT INTO attendance (user_id, timestamp, type, image_path) VALUES (?, ?, ?, ?)',
        (user_id, timestamp, checkin_type, image_path)
    )
    attendance_id = c.lastrowid
    conn.commit()
    conn.close()
    return {
        'id': attendance_id,
        'user_id': user_id,
        'timestamp': timestamp,
        'type': checkin_type,
        'image_path': image_path,
        'created': True
    }


def update_attendance_image(attendance_id, image_path):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('UPDATE attendance SET image_path = ? WHERE id = ?', (image_path, attendance_id))
    conn.commit()
    conn.close()

def get_attendance():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    today = get_beijing_date()
    c.execute('''
        SELECT a.*, u.name
        FROM attendance a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE a.id IN (
            SELECT MIN(id)
            FROM attendance
            WHERE substr(timestamp, 1, 10) = ?
            GROUP BY user_id
        )
        ORDER BY a.timestamp DESC
    ''', (today,))
    records = [dict(row) for row in c.fetchall()]
    conn.close()
    return records

if __name__ == '__main__':
    init_db()
    print("Database initialized.")
