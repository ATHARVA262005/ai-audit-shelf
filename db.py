"""SQLite storage layer for the AI Audit system."""

import sqlite3
import json
from pathlib import Path
from typing import Optional

from models import Chapter, Book

DB_PATH = Path(__file__).parent / "audit.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None):
    """Create tables if they don't exist."""
    should_close = conn is None
    if conn is None:
        conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chapters (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            result TEXT NOT NULL,
            actor TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'manual',
            metadata TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            chapter_ids TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            feature TEXT NOT NULL,
            created_at TEXT NOT NULL,
            parent_book_id TEXT,
            metadata TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
    """)
    # Ensure counters exist
    for name in ("chapter", "book"):
        conn.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES (?, 0)",
            (name,),
        )
        
    # Seed default users if empty (password for all is username + "123")
    # admin -> admin123, auditor -> auditor123, agent -> agent123
    default_users = [
        ("admin", "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36Xf6b5796b3796b3796b37", "admin"),
        ("auditor", "$2b$12$EixZaYVK1fsbw1ZfbX3OXe.NqGgI0zI3u6b5796b3796b3796b37", "auditor"),
        ("agent", "$2b$12$EixZaYVK1fsbw1ZfbX3OXe8XmU8.1zI3u6b5796b3796b3796b37", "agent")
    ]
    for username, pwd_hash, role in default_users:
        conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, pwd_hash, role),
        )
        
    conn.commit()
    if should_close:
        conn.close()


def next_id(conn: sqlite3.Connection, prefix: str) -> str:
    """Generate next sequential ID like c_001, b_002."""
    conn.execute(
        "UPDATE counters SET value = value + 1 WHERE name = ?",
        (prefix,),
    )
    row = conn.execute(
        "SELECT value FROM counters WHERE name = ?", (prefix,)
    ).fetchone()
    return f"{prefix[0]}_{row['value']:03d}"


# --- User operations ---

def get_user(username: str, conn: sqlite3.Connection) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def create_user(username: str, password_hash: str, role: str, conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()


# --- Chapter operations ---

def save_chapter(chapter: Chapter, conn: sqlite3.Connection):
    conn.execute(
        """INSERT INTO chapters (id, prompt, result, actor, timestamp, source, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            chapter.id,
            chapter.prompt,
            chapter.result,
            chapter.actor,
            chapter.timestamp,
            chapter.source,
            json.dumps(chapter.metadata),
        ),
    )
    conn.commit()


def get_chapter(chapter_id: str, conn: sqlite3.Connection) -> Optional[Chapter]:
    row = conn.execute(
        "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
    ).fetchone()
    if row is None:
        return None
    return Chapter(
        id=row["id"],
        prompt=row["prompt"],
        result=row["result"],
        actor=row["actor"],
        timestamp=row["timestamp"],
        source=row["source"],
        metadata=json.loads(row["metadata"]),
    )


def list_chapters(conn: sqlite3.Connection) -> list[Chapter]:
    rows = conn.execute("SELECT * FROM chapters ORDER BY timestamp DESC").fetchall()
    return [
        Chapter(
            id=r["id"],
            prompt=r["prompt"],
            result=r["result"],
            actor=r["actor"],
            timestamp=r["timestamp"],
            source=r["source"],
            metadata=json.loads(r["metadata"]),
        )
        for r in rows
    ]


# --- Book operations ---

def save_book(book: Book, conn: sqlite3.Connection):
    conn.execute(
        """INSERT INTO books (id, title, chapter_ids, version, feature, created_at, parent_book_id, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            book.id,
            book.title,
            json.dumps(book.chapter_ids),
            book.version,
            book.feature,
            book.created_at,
            book.parent_book_id,
            json.dumps(book.metadata),
        ),
    )
    conn.commit()


def get_book(book_id: str, str, conn: sqlite3.Connection) -> Optional[Book]:
    row = conn.execute(
        "SELECT * FROM books WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        return None
    return Book(
        id=row["id"],
        title=row["title"],
        chapter_ids=json.loads(row["chapter_ids"]),
        version=row["version"],
        feature=row["feature"],
        created_at=row["created_at"],
        parent_book_id=row["parent_book_id"],
        metadata=json.loads(row["metadata"]),
    )


def list_books(conn: sqlite3.Connection) -> list[Book]:
    rows = conn.execute("SELECT * FROM books ORDER BY created_at").fetchall()
    return [
        Book(
            id=r["id"],
            title=r["title"],
            chapter_ids=json.loads(r["chapter_ids"]),
            version=r["version"],
            feature=r["feature"],
            created_at=r["created_at"],
            parent_book_id=r["parent_book_id"],
            metadata=json.loads(r["metadata"]),
        )
        for r in rows
    ]
