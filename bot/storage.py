"""SQLite: минимум данных. Ни имени, ни телефона, ни ответов анкеты не храним.

users      — chat_id (нужен, чтобы бот мог написать) + случайный код для субайди
events     — обезличенная статистика: какое действие и по какому офферу
followups  — напоминания, на которые пользователь сам согласился
"""
import secrets
import sqlite3
import time
from pathlib import Path


class Storage:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                code TEXT NOT NULL,
                kind TEXT NOT NULL,
                offer_id INTEGER,
                ts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS followups (
                chat_id INTEGER NOT NULL,
                offer_id INTEGER NOT NULL,
                due_at INTEGER NOT NULL,
                stage INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (chat_id, offer_id)
            );
        """)
        self.db.commit()

    def user_code(self, chat_id: int) -> str:
        row = self.db.execute("SELECT code FROM users WHERE chat_id=?", (chat_id,)).fetchone()
        if row:
            return row[0]
        code = secrets.token_hex(5)
        self.db.execute("INSERT INTO users VALUES (?,?,?)", (chat_id, code, int(time.time())))
        self.db.commit()
        return code

    def log(self, chat_id: int, kind: str, offer_id: int | None = None) -> None:
        self.db.execute("INSERT INTO events VALUES (?,?,?,?)",
                        (self.user_code(chat_id), kind, offer_id, int(time.time())))
        self.db.commit()

    def add_followup(self, chat_id: int, offer_id: int, hours: float, stage: int = 1) -> None:
        self.db.execute("INSERT OR REPLACE INTO followups VALUES (?,?,?,?)",
                        (chat_id, offer_id, int(time.time() + hours * 3600), stage))
        self.db.commit()

    def remove_followup(self, chat_id: int, offer_id: int) -> None:
        self.db.execute("DELETE FROM followups WHERE chat_id=? AND offer_id=?", (chat_id, offer_id))
        self.db.commit()

    def due_followups(self) -> list[tuple[int, int, int]]:
        rows = self.db.execute("SELECT chat_id, offer_id, stage FROM followups WHERE due_at<=?",
                               (int(time.time()),)).fetchall()
        return rows

    def delete_user(self, chat_id: int) -> None:
        """Команда /delete: удаляем связь chat_id ↔ код и напоминания. Обезличенная статистика остаётся."""
        self.db.execute("DELETE FROM followups WHERE chat_id=?", (chat_id,))
        self.db.execute("DELETE FROM users WHERE chat_id=?", (chat_id,))
        self.db.commit()

    def stats(self, days: int = 30) -> dict:
        since = int(time.time() - days * 86400)
        kinds = dict(self.db.execute(
            "SELECT kind, COUNT(DISTINCT code) FROM events WHERE ts>=? GROUP BY kind", (since,)).fetchall())
        by_offer = self.db.execute(
            "SELECT offer_id, COUNT(DISTINCT code) FROM events WHERE kind='apply' AND ts>=? "
            "GROUP BY offer_id ORDER BY 2 DESC", (since,)).fetchall()
        return {"kinds": kinds, "apply_by_offer": by_offer}
