"""SQLite storage layer for the AI Audit system."""

import sqlite3
import json
from typing import Optional, List
from models import Chapter, Book

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect("audit_shelf.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: Optional[sqlite3.Connection] = None):
    """Initialize database tables and set up FTS5 full-text search indexing."""
    passed_conn = conn is not None
    if not passed_conn:
        conn = get_connection()
    
    assert conn is not None
    should_close = not passed_conn

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            result TEXT NOT NULL,
            actor TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            chapter_ids TEXT NOT NULL,
            version INTEGER NOT NULL,
            feature TEXT NOT NULL,
            created_at TEXT NOT NULL,
            parent_book_id TEXT,
            metadata TEXT DEFAULT '{}'
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        );
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
    """)

    for name in ("chapter", "book"):
        conn.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES (?, 0)",
            (name,),
        )

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

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
            id UNINDEXED,
            prompt,
            result
        );
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS after_chapter_insert AFTER INSERT ON chapters BEGIN
            INSERT INTO chapters_fts(id, prompt, result) VALUES (new.id, new.prompt, new.result);
        END;
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS after_chapter_delete AFTER DELETE ON chapters BEGIN
            DELETE FROM chapters_fts WHERE id = old.id;
        END;
    """)

    existing_fts_count = conn.execute("SELECT COUNT(*) as cnt FROM chapters_fts").fetchone()["cnt"]
    if existing_fts_count == 0:
        conn.execute("""
            INSERT INTO chapters_fts(id, prompt, result)
            SELECT id, prompt, result FROM chapters;
        """)

    conn.commit()
    if should_close:
        conn.close()

def next_id(conn: sqlite3.Connection, prefix: str) -> str:
    conn.execute(
        "UPDATE counters SET value = value + 1 WHERE name = ?", (prefix,)
    )
    row = conn.execute(
        "SELECT value FROM counters WHERE name = ?", (prefix,)
    ).fetchone()
    return f"{prefix[0]}_{row['value']:03d}"

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

def save_chapter(chapter: Chapter, conn: sqlite3.Connection):
    conn.execute(
        """
        INSERT INTO chapters (id, prompt, result, actor, timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            chapter.id,
            chapter.prompt,
            chapter.result,
            chapter.actor,
            chapter.timestamp,
            chapter.source,
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
    )

def list_chapters(conn: sqlite3.Connection) -> List[Chapter]:
    rows = conn.execute("SELECT * FROM chapters ORDER BY timestamp DESC").fetchall()
    return [
        Chapter(
            id=r["id"],
            prompt=r["prompt"],
            result=r["result"],
            actor=r["actor"],
            timestamp=r["timestamp"],
            source=r["source"],
        )
        for r in rows
    ]

def search_chapters_fts(
    conn: sqlite3.Connection,
    keyword: Optional[str] = None,
    actor: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
) -> List[Chapter]:
    """Search chapters dynamically using SQLite FTS5 MATCH capabilities and BM25 ranking."""
    query_parts = []
    params = []

    if keyword:
        query_parts.append("chapters.id IN (SELECT id FROM chapters_fts WHERE chapters_fts MATCH ?)")
        params.append(keyword)
    
    if actor:
        query_parts.append("LOWER(chapters.actor) = LOWER(?)")
        params.append(actor)
        
    if after:
        query_parts.append("chapters.timestamp >= ?")
        params.append(after)
        
    if before:
        query_parts.append("chapters.timestamp <= ?")
        params.append(before)

    base_sql = "SELECT chapters.* FROM chapters"
    
    if keyword:
        base_sql += " JOIN chapters_fts ON chapters.id = chapters_fts.id"
        
    if query_parts:
        base_sql += " WHERE " + " AND ".join(query_parts)
        
    if keyword:
        base_sql += " ORDER BY bm25(chapters_fts) ASC"
    else:
        base_sql += " ORDER BY chapters.timestamp DESC"

    rows = conn.execute(base_sql, params).fetchall()
    return [
        Chapter(
            id=r["id"],
            prompt=r["prompt"],
            result=r["result"],
            actor=r["actor"],
            timestamp=r["timestamp"],
            source=r["source"],
        )
        for r in rows
    ]

def save_book(book: Book, conn: sqlite3.Connection):
    conn.execute(
        """
        INSERT INTO books (id, title, chapter_ids, version, feature, created_at, parent_book_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
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

def get_book(book_id: str, conn: sqlite3.Connection) -> Optional[Book]:
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

def list_books(conn: sqlite3.Connection) -> List[Book]:
    rows = conn.execute("SELECT * FROM books ORDER BY created_at DESC").fetchall()
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
