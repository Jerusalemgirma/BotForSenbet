import os
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Table for questions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                creator_id BIGINT,
                question_text TEXT,
                options TEXT,
                correct_option_id INTEGER,
                poll_id TEXT UNIQUE,
                chat_id BIGINT,
                message_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for answers
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS answers (
                poll_id TEXT,
                user_id BIGINT,
                user_name TEXT,
                option_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (poll_id, user_id)
            )
        ''')
        
        # Table for group registration
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                chat_id BIGINT,
                message_thread_id INTEGER,
                chat_title TEXT,
                PRIMARY KEY (chat_id, message_thread_id)
            )
        ''')
        conn.commit()
        
        # Migration: Add message_thread_id to groups if it doesn't exist
        # In Postgres, we can check information_schema or just try/catch
        try:
            cursor.execute('ALTER TABLE groups ADD COLUMN message_thread_id INTEGER')
            conn.commit()
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
            pass
            
        conn.close()
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

def add_question(creator_id, question_text, options, correct_option_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO questions (creator_id, question_text, options, correct_option_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    ''', (creator_id, question_text, json.dumps(options), correct_option_id))
    question_id = cursor.fetchone()['id']
    conn.commit()
    conn.close()
    return question_id

def update_question_poll(question_id, poll_id, chat_id, message_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE questions
        SET poll_id = %s, chat_id = %s, message_id = %s
        WHERE id = %s
    ''', (poll_id, chat_id, message_id, question_id))
    conn.commit()
    conn.close()

def save_answer(poll_id, user_id, user_name, option_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO answers (poll_id, user_id, user_name, option_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (poll_id, user_id) 
        DO UPDATE SET option_id = EXCLUDED.option_id, user_name = EXCLUDED.user_name, timestamp = CURRENT_TIMESTAMP
    ''', (poll_id, user_id, user_name, option_id))
    conn.commit()
    conn.close()

def get_question_by_poll_id(poll_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM questions WHERE poll_id = %s', (poll_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row['id'],
            "creator_id": row['creator_id'],
            "question_text": row['question_text'],
            "options": json.loads(row['options']),
            "correct_option_id": row['correct_option_id'],
            "poll_id": row['poll_id'],
            "chat_id": row['chat_id'],
            "message_id": row['message_id']
        }
    return None

def get_results(poll_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_name, option_id FROM answers WHERE poll_id = %s', (poll_id,))
    rows = cursor.fetchall()
    # Convert RealDictRow to list of tuples to match previous behavior expected by bot.py
    result = [(row['user_name'], row['option_id']) for row in rows]
    conn.close()
    return result

def register_group(chat_id, chat_title, message_thread_id=0):
    # Default message_thread_id to 0 if None, because composite PK cannot contain NULL in some contexts, 
    # but here we defined it as (chat_id, message_thread_id). 
    # However, in SQLite code it was allowing NULL? 
    # Wait, SQLite allows NULL in PK. Postgres does NOT allow NULL in PK.
    # So we must ensure message_thread_id is not None. 
    # Let's use 0 for "General" topic/no topic.
    if message_thread_id is None:
        message_thread_id = 0
        
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO groups (chat_id, chat_title, message_thread_id) 
        VALUES (%s, %s, %s)
        ON CONFLICT (chat_id, message_thread_id)
        DO UPDATE SET chat_title = EXCLUDED.chat_title
    ''', (chat_id, chat_title, message_thread_id))
    conn.commit()
    conn.close()

def get_registered_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id, chat_title, message_thread_id FROM groups')
    rows = cursor.fetchall()
    # Convert to list of tuples
    result = [(row['chat_id'], row['chat_title'], row['message_thread_id']) for row in rows]
    conn.close()
    return result

def get_user_questions(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, question_text, poll_id FROM questions WHERE creator_id = %s AND poll_id IS NOT NULL', (user_id,))
    rows = cursor.fetchall()
    # Convert to list of tuples
    result = [(row['id'], row['question_text'], row['poll_id']) for row in rows]
    conn.close()
    return result
