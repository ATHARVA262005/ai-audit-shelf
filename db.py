import sqlite3, json
from typing import Optional, List
from models import Chapter, Book

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect("audit_shelf.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: Optional[sqlite3.Connection] = None):
    passed_conn = conn is not None
    if not passed_conn:
        conn = get_connection()
    assert conn is not None
    should_close = not passed_conn
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chapters (
            id TEXT PRIMARY KEY, prompt TEXT NOT NULL, result TEXT NOT NULL,
            actor TEXT NOT NULL, timestamp TEXT NOT NULL, source TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, chapter_ids TEXT NOT NULL,
            version INTEGER NOT NULL, feature TEXT NOT NULL, created_at TEXT NOT NULL,
            parent_book_id TEXT, metadata TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL
        );
    """)
    for name in ("chapter", "book"):
        conn.execute("INSERT OR IGNORE INTO counters (name, value) VALUES (?, 0)", (name,))
    from auth import get_password_hash
    for u, p, r in [("admin","admin123","admin"),("auditor","auditor123","auditor"),("agent","agent123","agent")]:
        conn.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)", (u, get_password_hash(p), r))
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(id UNINDEXED, prompt, result);
        CREATE TRIGGER IF NOT EXISTS after_chapter_insert AFTER INSERT ON chapters BEGIN
            INSERT INTO chapters_fts(id, prompt, result) VALUES (new.id, new.prompt, new.result);
        END;
        CREATE TRIGGER IF NOT EXISTS after_chapter_delete AFTER DELETE ON chapters BEGIN
            DELETE FROM chapters_fts WHERE id = old.id;
        END;
    """)
    if conn.execute("SELECT COUNT(*) as c FROM chapters_fts").fetchone()["c"] == 0:
        conn.execute("INSERT INTO chapters_fts(id, prompt, result) SELECT id, prompt, result FROM chapters;")
    conn.commit()
    if should_close:
        conn.close()

def next_id(conn, prefix):
    conn.execute("UPDATE counters SET value = value + 1 WHERE name = ?", (prefix,))
    return f"{prefix[0]}_{conn.execute('SELECT value FROM counters WHERE name = ?', (prefix,)).fetchone()['value']:03d}"

def get_user(username, conn):
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None

def create_user(username, password_hash, role, conn):
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, password_hash, role))
    conn.commit()

def save_chapter(chapter, conn):
    conn.execute("INSERT INTO chapters (id, prompt, result, actor, timestamp, source) VALUES (?, ?, ?, ?, ?, ?)",
        (chapter.id, chapter.prompt, chapter.result, chapter.actor, chapter.timestamp, chapter.source))
    conn.commit()

def get_chapter(chapter_id, conn):
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    if row is None: return None
    return Chapter(id=row["id"], prompt=row["prompt"], result=row["result"], actor=row["actor"], timestamp=row["timestamp"], source=row["source"])

def list_chapters(conn):
    return [Chapter(id=r["id"], prompt=r["prompt"], result=r["result"], actor=r["actor"], timestamp=r["timestamp"], source=r["source"])
            for r in conn.execute("SELECT * FROM chapters ORDER BY timestamp DESC").fetchall()]
