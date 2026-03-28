import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from config import config


class Database:
    def __init__(self):
        self.conn = sqlite3.connect('contest_bot.db', check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT UNIQUE NOT NULL,
                channel_name TEXT,
                channel_username TEXT,
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id TEXT UNIQUE NOT NULL,
                description TEXT,
                media_type TEXT,
                media_file_id TEXT,
                button_text TEXT DEFAULT 'Qatnashaman',
                winners_count INTEGER DEFAULT 1,
                finish_type TEXT,
                finish_value TEXT,
                channel_id INTEGER,
                creator_id INTEGER,
                message_id INTEGER,
                post_link TEXT,
                is_active INTEGER DEFAULT 1,
                is_published INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels (id),
                FOREIGN KEY (creator_id) REFERENCES users (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contest_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id TEXT,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT,
                FOREIGN KEY (contest_id) REFERENCES contests (contest_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id TEXT,
                user_id INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contest_id) REFERENCES contests (contest_id),
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(contest_id, user_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS temp_contest_data (
                user_id INTEGER,
                key TEXT,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, key)
            )
        ''')

        self.conn.commit()

    def get_or_create_user(self, telegram_id: int, username: str = None, full_name: str = None) -> Dict:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()

        if user:
            return dict(user)

        is_admin = 1 if telegram_id in config.ADMIN_IDS else 0
        cursor.execute('''
            INSERT INTO users (telegram_id, username, full_name, is_admin)
            VALUES (?, ?, ?, ?)
        ''', (telegram_id, username, full_name, is_admin))
        self.conn.commit()

        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        return dict(cursor.fetchone())

    def get_user(self, telegram_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        return dict(user) if user else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        return dict(user) if user else None

    def add_channel(self, channel_id: str, channel_name: str, channel_username: str, owner_id: int) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO channels (channel_id, channel_name, channel_username, owner_id)
                VALUES (?, ?, ?, ?)
            ''', (channel_id, channel_name, channel_username, owner_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_user_channels(self, user_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM channels WHERE owner_id = ?', (user_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_channel(self, channel_id: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM channels WHERE id = ?', (channel_id,))
        channel = cursor.fetchone()
        return dict(channel) if channel else None

    def get_channel_by_id(self, channel_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM channels WHERE id = ?', (channel_id,))
        channel = cursor.fetchone()
        return dict(channel) if channel else None

    def get_channel_by_channel_id(self, channel_id: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM channels WHERE channel_id = ?', (channel_id,))
        channel = cursor.fetchone()
        return dict(channel) if channel else None

    def delete_channel(self, channel_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM channels WHERE id = ?', (channel_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def create_contest(self, contest_data: Dict) -> str:
        cursor = self.conn.cursor()

        cursor.execute('''
            INSERT INTO contests (
                contest_id, description, media_type, media_file_id,
                button_text, winners_count, finish_type, finish_value,
                channel_id, creator_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            contest_data['contest_id'],
            contest_data.get('description'),
            contest_data.get('media_type'),
            contest_data.get('media_file_id'),
            contest_data.get('button_text', 'Qatnashaman'),
            contest_data.get('winners_count', 1),
            contest_data.get('finish_type'),
            contest_data.get('finish_value'),
            contest_data.get('channel_id'),
            contest_data.get('creator_id')
        ))
        self.conn.commit()

        if contest_data.get('channels'):
            for ch in contest_data['channels']:
                cursor.execute('''
                    INSERT INTO contest_channels (contest_id, channel_id, channel_username, channel_name)
                    VALUES (?, ?, ?, ?)
                ''', (contest_data['contest_id'], str(ch['id']), ch['username'], ch['name']))
            self.conn.commit()

        return contest_data['contest_id']

    def update_contest_published(self, contest_id: str, message_id: int, post_link: str = None):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE contests 
            SET is_published = 1, message_id = ?, post_link = ?
            WHERE contest_id = ?
        ''', (message_id, post_link, contest_id))
        self.conn.commit()

    def get_contest(self, contest_id: str) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM contests WHERE contest_id = ?', (contest_id,))
        contest = cursor.fetchone()
        if contest:
            contest_dict = dict(contest)
            cursor.execute('SELECT * FROM contest_channels WHERE contest_id = ?', (contest_id,))
            contest_dict['channels'] = [dict(row) for row in cursor.fetchall()]
            return contest_dict
        return None

    def get_user_contests(self, user_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM contests 
            WHERE creator_id = ? 
            ORDER BY created_at DESC
        ''', (user_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_active_contests(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM contests 
            WHERE is_active = 1 AND is_published = 1
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def finish_contest(self, contest_id: str):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE contests SET is_active = 0 WHERE contest_id = ?', (contest_id,))
        self.conn.commit()

    def add_participant(self, contest_id: str, user_id: int) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO participants (contest_id, user_id)
                VALUES (?, ?)
            ''', (contest_id, user_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def is_participant(self, contest_id: str, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM participants WHERE contest_id = ? AND user_id = ?
        ''', (contest_id, user_id))
        return cursor.fetchone() is not None

    def get_participants_count(self, contest_id: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM participants WHERE contest_id = ?', (contest_id,))
        return cursor.fetchone()[0]

    def get_participants(self, contest_id: str) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.*, u.username, u.full_name
            FROM participants p
            JOIN users u ON p.user_id = u.id
            WHERE p.contest_id = ?
            ORDER BY p.joined_at
        ''', (contest_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_random_winners(self, contest_id: str, count: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT p.user_id, u.username, u.full_name
            FROM participants p
            JOIN users u ON p.user_id = u.id
            WHERE p.contest_id = ?
            ORDER BY RANDOM()
            LIMIT ?
        ''', (contest_id, count))
        return [dict(row) for row in cursor.fetchall()]

    def is_contest_finished(self, contest_id: str) -> bool:
        """Konkurs tugaganligini tekshirish"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT is_active FROM contests WHERE contest_id = ?', (contest_id,))
        row = cursor.fetchone()
        if row:
            return row[0] == 0  # is_active = 0 bo'lsa tugagan
        return True

    def save_temp_contest_data(self, user_id: int, key: str, value: Any):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO temp_contest_data (user_id, key, value)
                VALUES (?, ?, ?)
            ''', (user_id, key, json.dumps(value, ensure_ascii=False)))
            self.conn.commit()
        except Exception as e:
            print(f"Error saving temp data: {e}")

    def get_temp_contest_data(self, user_id: int, key: str) -> Optional[Any]:
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT value FROM temp_contest_data WHERE user_id = ? AND key = ?', (user_id, key))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            print(f"Error getting temp data: {e}")
            return None

    def clear_temp_contest_data(self, user_id: int):
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM temp_contest_data WHERE user_id = ?', (user_id,))
            self.conn.commit()
        except Exception as e:
            print(f"Error clearing temp data: {e}")

    def close(self):
        self.conn.close()


db = Database()