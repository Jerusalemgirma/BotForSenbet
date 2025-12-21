import sqlite3
import json
from datetime import datetime

DB_NAME = "bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for questions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER,
            question_text TEXT,
            options TEXT,
            correct_option_id INTEGER,
            poll_id TEXT UNIQUE,
            chat_id INTEGER,
            message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Table for answers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            poll_id TEXT,
            user_id INTEGER,
            user_name TEXT,
            option_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (poll_id, user_id)
        )
    ''')
    
    # Table for group registration
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def add_question(creator_id, question_text, options, correct_option_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO questions (creator_id, question_text, options, correct_option_id)
        VALUES (?, ?, ?, ?)
    ''', (creator_id, question_text, json.dumps(options), correct_option_id))
    question_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return question_id

def update_question_poll(question_id, poll_id, chat_id, message_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE questions
        SET poll_id = ?, chat_id = ?, message_id = ?
        WHERE id = ?
    ''', (poll_id, chat_id, message_id, question_id))
    conn.commit()
    conn.close()

def save_answer(poll_id, user_id, user_name, option_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO answers (poll_id, user_id, user_name, option_id)
        VALUES (?, ?, ?, ?)
    ''', (poll_id, user_id, user_name, option_id))
    conn.commit()
    conn.close()

def get_question_by_poll_id(poll_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM questions WHERE poll_id = ?', (poll_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "creator_id": row[1],
            "question_text": row[2],
            "options": json.loads(row[3]),
            "correct_option_id": row[4],
            "poll_id": row[5],
            "chat_id": row[6],
            "message_id": row[7]
        }
    return None

def get_results(poll_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_name, option_id FROM answers WHERE poll_id = ?', (poll_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def register_group(chat_id, chat_title):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO groups (chat_id, chat_title) VALUES (?, ?)', (chat_id, chat_title))
    conn.commit()
    conn.close()

def get_registered_groups():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, chat_title FROM groups')
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_questions(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, question_text, poll_id FROM questions WHERE creator_id = ? AND poll_id IS NOT NULL', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
