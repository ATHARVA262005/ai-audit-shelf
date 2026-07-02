"""FastAPI server for the AI Audit system."""

import json
import os
import re
import concurrent.futures
import logging
from datetime import datetime, timezone
from typing import Optional, List, Union
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Query, Depends, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from models import Chapter, Book
from db import get_connection, init_db, next_id, save_chapter, get_chapter, list_chapters, save_book, get_book, list_books


class ChapterCreate(BaseModel):
    prompt: str = Field(..., max_length=50000)
    result: str = Field(..., max_length=50000)
    actor: str = Field("anonymous", max_length=255)
    source: str = Field("manual", max_length=255)
    model: Optional[str] = Field(None, max_length=255)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    seed: Optional[int] = Field(None)
    validation_status: Optional[str] = Field(None, max_length=50)
    validation_message: Optional[str] = Field(None, max_length=1000)


class BookCreate(BaseModel):
    title: str = Field(..., max_length=255)
    chapter_ids: List[str] = Field(...)
    feature: Optional[str] = Field(None, max_length=255)


class BookEdition(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    chapter_ids: Optional[List[str]] = Field(None)


def _run_regex_match(pattern: str, string: str, queue):
    """Target worker function executed in an isolated process to bypass the GIL lock."""
    try:
        match = re.search(pattern, string)
        queue.put(bool(match))
    except Exception as e:
        queue.put(e)


def safe_regex_search(pattern: str, string: str, timeout: float = 1.5) -> bool:
    """Run regex search in an isolated OS process to guarantee timeout enforcement under ReDoS."""
    import multiprocessing
    # Use standard Spawn context on Windows/Unix for consistent cross-platform behavior
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=_run_regex_match, args=(pattern, string, queue))
    proc.start()
    proc.join(timeout=timeout)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        raise ValueError("Regex evaluation timed out (potential catastrophic backtracking/ReDoS detected)")
    if not queue.empty():
        result = queue.get()
        if isinstance(result, Exception):
            raise result
        return result
    return False



app = FastAPI(  
    title="AI Audit API",
    description="Git-like versioning for AI workflows, organized as books and chapters.",
    version="0.2.0",
)


import hmac

# Configure structured application logging (resolving OBS-01 and OBS-02)
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger("ai_audit")

# Secure default CORS configuration: do not default to "*" wildcard (resolving SEC-09)
CORS_ORIGINS_RAW = os.environ.get("AUDIT_CORS_ORIGINS", "http://localhost:8000")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_RAW.split(",") if origin.strip()]
allow_creds = CORS_ORIGINS != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Separate read vs. write keys to allow distinct access policy controls (resolving SEC-01 and SEC-03)
WRITE_API_KEY = os.environ.get("AUDIT_API_KEY", "")
READ_API_KEY = os.environ.get("AUDIT_READ_API_KEY", "")
LOCKDOWN_READS = os.environ.get("AUDIT_LOCKDOWN_READS", "false").lower() == "true"
DEV_MODE = os.environ.get("AUDIT_DEV_MODE", "false").lower() == "true"

# Enforce fail-fast security gate in production on server startup (resolving SEC-01)
if not WRITE_API_KEY and not DEV_MODE:
    logger.critical("Production Startup Prevented: AUDIT_API_KEY is not set.")
    raise RuntimeError(
        "CRITICAL SECURITY ERROR: The AUDIT_API_KEY environment variable is NOT set. "
        "For security, the application cannot run in production mode without an API key. "
        "Set AUDIT_API_KEY, or run with AUDIT_DEV_MODE=true for local testing."
    )


def verify_write_api_key(x_api_key: Optional[str] = Header(None)):
    """Timing-safe API key verification for write operations."""
    if WRITE_API_KEY:
        if not x_api_key or not hmac.compare_digest(x_api_key, WRITE_API_KEY):
            logger.warning("Security Warning: Unauthorized write attempt rejected (invalid API key).")
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


def verify_read_api_key(x_api_key: Optional[str] = Header(None)):
    """Timing-safe API key verification for read operations (separate and optional policy)."""
    if READ_API_KEY:
        if not x_api_key or not hmac.compare_digest(x_api_key, READ_API_KEY):
            logger.warning("Security Warning: Unauthorized read attempt rejected (invalid read key).")
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    elif LOCKDOWN_READS and WRITE_API_KEY:
        if not x_api_key or not hmac.compare_digest(x_api_key, WRITE_API_KEY):
            logger.warning("Security Warning: Unauthorized read attempt rejected (lockdown reads active).")
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.on_event("startup")
def startup_event():
    """Run database schema migration exactly once on app launch."""
    logger.info("Initializing database schemas and running dynamic migrations.")
    conn = get_connection()
    try:
        init_db(conn)
        logger.info("Database schemas fully initialized.")
    except Exception as e:
        logger.critical(f"Database schema initialization failed: {str(e)}")
        raise e
    finally:
        conn.close()


def get_db():
    """Dependency that provides a thread-safe database connection."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()



# --- Chapters ---

# --- Chapters ---

@app.post("/chapter", response_model=dict, dependencies=[Depends(verify_write_api_key)])
def api_add_chapter(
    prompt: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    actor: str = Query("anonymous"),
    source: str = Query("manual"),
    model: Optional[str] = Query(None),
    temperature: Optional[float] = Query(None),
    seed: Optional[int] = Query(None),
    validation_status: Optional[str] = Query(None),
    validation_message: Optional[str] = Query(None),
    body: Optional[ChapterCreate] = None,
    conn=Depends(get_db),
):
    """Log a new chapter (atomic AI action) via JSON request body or query parameter fallback."""
    # 1. Resolve values from body or parameters (favor body)
    if body:
        f_prompt = body.prompt
        f_result = body.result
        f_actor = body.actor
        f_source = body.source
        f_model = body.model
        f_temp = body.temperature
        f_seed = body.seed
        f_val_status = body.validation_status
        f_val_msg = body.validation_message
    else:
        # Enforce parameter boundaries if query fallback is utilized
        if not prompt or not result:
            raise HTTPException(status_code=400, detail="Missing prompt or result payload")
        if len(prompt) > 50000 or len(result) > 50000:
            raise HTTPException(status_code=400, detail="Payload length exceeds maximum allowed characters (50,000)")
        f_prompt = prompt
        f_result = result
        f_actor = actor[:255] if actor else "anonymous"
        f_source = source[:255] if source else "manual"
        f_model = model[:255] if model else None
        f_temp = temperature
        f_seed = seed
        f_val_status = validation_status[:50] if validation_status else None
        f_val_msg = validation_message[:1000] if validation_message else None

    chapter_id = next_id(conn, "chapter")
    chapter = Chapter(
        id=chapter_id,
        prompt=f_prompt,
        result=f_result,
        actor=f_actor,
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=f_source,
        model=f_model,
        temperature=f_temp,
        seed=f_seed,
        validation_status=f_val_status,
        validation_message=f_val_msg,
    )
    save_chapter(chapter, conn)
    return {"status": "created", "chapter": chapter.to_dict()}


@app.post("/chapter/{chapter_id}/validate", response_model=dict, dependencies=[Depends(verify_write_api_key)])
def api_validate_chapter(
    chapter_id: str,
    required_keywords: Optional[list[str]] = Query(None),
    regex_pattern: Optional[str] = None,
    json_format: bool = False,
    conn=Depends(get_db),
):
    """Run a validation gate check on a logged chapter's output with ReDoS-safe worker pool timeouts."""
    chapter = get_chapter(chapter_id, conn)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")

    passed = True
    reasons = []

    # 1. ReDoS-safe regex evaluation (1.5s execution boundary)
    if regex_pattern:
        if len(regex_pattern) > 1000:
            raise HTTPException(status_code=400, detail="Regex pattern exceeds length safety limits")
        try:
            matched = safe_regex_search(regex_pattern, chapter.result, timeout=1.5)
            if not matched:
                passed = False
                reasons.append(f"Result did not match regex pattern '{regex_pattern}'")
        except ValueError as e:
            passed = False
            reasons.append(str(e))
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {e}")

    # 2. Keywords check
    if required_keywords:
        missing = [kw for kw in required_keywords if kw.lower() not in chapter.result.lower()]
        if missing:
            passed = False
            reasons.append(f"Missing required keywords: {', '.join(missing)}")

    # 3. JSON format check
    if json_format:
        try:
            json.loads(chapter.result)
        except json.JSONDecodeError:
            passed = False
            reasons.append("Result is not a valid JSON document")

    # Update chapter status in DB
    chapter.validation_status = "passed" if passed else "failed"
    chapter.validation_message = "Validation passed." if passed else " | ".join(reasons)

    # Perform SQL UPDATE
    conn.execute(
        "UPDATE chapters SET validation_status = ?, validation_message = ? WHERE id = ?",
        (chapter.validation_status, chapter.validation_message, chapter.id),
    )
    conn.commit()
    logger.info(f"AUDIT TRAIL: Chapter '{chapter.id}' validation state updated to '{chapter.validation_status}' - Msg: {chapter.validation_message}")

    return {
        "chapter_id": chapter_id,
        "validation_status": chapter.validation_status,
        "validation_message": chapter.validation_message,
        "chapter": chapter.to_dict(),
    }


@app.get("/chapters", response_model=list[dict], dependencies=[Depends(verify_read_api_key)])
def api_list_chapters(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db)
):
    """List all chapters with memory-safe limit and offset pagination."""
    # SQLite offset pagination fallback
    rows = conn.execute(
        "SELECT * FROM chapters ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    return [
        Chapter(
            id=r["id"],
            prompt=r["prompt"],
            result=r["result"],
            actor=r["actor"],
            timestamp=r["timestamp"],
            source=r["source"],
            model=r["model"],
            temperature=r["temperature"],
            seed=r["seed"],
            validation_status=r["validation_status"],
            validation_message=r["validation_message"],
            metadata=json.loads(r["metadata"]),
        ).to_dict()
        for r in rows
    ]


@app.get("/chapter/{chapter_id}", response_model=dict, dependencies=[Depends(verify_read_api_key)])
def api_get_chapter(chapter_id: str, conn=Depends(get_db)):
    """Get a single chapter by ID (authenticated)."""
    ch = get_chapter(chapter_id, conn)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")
    return ch.to_dict()


@app.get("/search/chapters", response_model=list[dict], dependencies=[Depends(verify_read_api_key)])
def api_search_chapters(
    actor: Optional[str] = None,
    keyword: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    conn=Depends(get_db),
):
    """Search chapters by actor, keyword, or date range with performance index push-downs."""
    query = "SELECT * FROM chapters WHERE 1=1"
    params = []
    if actor:
        query += " AND LOWER(actor) = ?"
        params.append(actor.lower())
    if keyword:
        query += " AND (LOWER(prompt) LIKE ? OR LOWER(result) LIKE ?)"
        params.extend([f"%{keyword.lower()}%", f"%{keyword.lower()}%"])
    if after:
        query += " AND timestamp >= ?"
        params.append(after)
    if before:
        query += " AND timestamp <= ?"
        params.append(before)

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [
        Chapter(
            id=r["id"],
            prompt=r["prompt"],
            result=r["result"],
            actor=r["actor"],
            timestamp=r["timestamp"],
            source=r["source"],
            model=r["model"],
            temperature=r["temperature"],
            seed=r["seed"],
            validation_status=r["validation_status"],
            validation_message=r["validation_message"],
            metadata=json.loads(r["metadata"]),
        ).to_dict()
        for r in rows
    ]



# --- Books ---

@app.post("/book", response_model=dict, dependencies=[Depends(verify_write_api_key)])
def api_create_book(
    title: Optional[str] = Query(None),
    feature: Optional[str] = Query(None),
    payload: Union[List[str], BookCreate] = Body(...),
    conn=Depends(get_db),
):
    """Bundle chapters into a book using polymorphic body payload or legacy queries."""
    if isinstance(payload, BookCreate):
        f_title = payload.title
        f_chapter_ids = payload.chapter_ids
        f_feature = payload.feature
    else:
        # Legacy list representation fallback
        if not title:
            raise HTTPException(status_code=400, detail="Missing title query parameter")
        if len(title) > 255 or (feature and len(feature) > 255):
            raise HTTPException(status_code=400, detail="Title/feature exceeds 255 character limit")
        f_title = title
        f_chapter_ids = payload
        f_feature = feature

    if not f_chapter_ids:
        raise HTTPException(status_code=400, detail="Book must contain at least one chapter ID")

    for cid in f_chapter_ids:
        if get_chapter(cid, conn) is None:
            raise HTTPException(status_code=400, detail=f"Chapter '{cid}' not found")
    book_id = next_id(conn, "book")
    book = Book(
        id=book_id,
        title=f_title,
        chapter_ids=f_chapter_ids,
        version=1,
        feature=f_feature or f_title,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_book(book, conn)
    return {"status": "created", "book": book.to_dict()}


@app.get("/books", response_model=list[dict], dependencies=[Depends(verify_read_api_key)])
def api_list_books(conn=Depends(get_db)):
    """List all books (authenticated)."""
    return [b.to_dict() for b in list_books(conn)]


@app.get("/book/{book_id}", response_model=dict, dependencies=[Depends(verify_read_api_key)])
def api_get_book(book_id: str, conn=Depends(get_db)):
    """Get a single book by ID (authenticated)."""
    b = get_book(book_id, conn)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    return b.to_dict()


@app.post("/book/{book_id}/edition", response_model=dict, dependencies=[Depends(verify_write_api_key)])
def api_new_edition(
    book_id: str,
    title: Optional[str] = Query(None),
    payload: Union[List[str], BookEdition] = Body(...),
    conn=Depends(get_db),
):
    """Create a new edition of a book (version bump) via polymorphic JSON body or parameters."""
    parent = get_book(book_id, conn)
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")

    if isinstance(payload, BookEdition):
        f_title = payload.title or parent.title
        f_chapter_ids = payload.chapter_ids or parent.chapter_ids
    else:
        # Legacy list representation fallback
        if title and len(title) > 255:
            raise HTTPException(status_code=400, detail="Title length exceeds 255 characters")
        f_title = title or parent.title
        f_chapter_ids = payload or parent.chapter_ids

    for cid in f_chapter_ids:
        if get_chapter(cid, conn) is None:
            raise HTTPException(status_code=400, detail=f"Chapter '{cid}' not found")
    new_id = next_id(conn, "book")
    new_book = Book(
        id=new_id,
        title=f_title,
        chapter_ids=f_chapter_ids,
        version=parent.version + 1,
        feature=parent.feature,
        created_at=datetime.now(timezone.utc).isoformat(),
        parent_book_id=parent.id,
    )
    save_book(new_book, conn)
    return {"status": "created", "book": new_book.to_dict()}



# --- Export & Diff ---

@app.get("/export/book/{book_id}", dependencies=[Depends(verify_read_api_key)])
def api_export_book(
    book_id: str,
    format: str = Query("json", pattern="^(json|markdown)$"),
    conn=Depends(get_db),
):
    """Export a book with all its chapters (authenticated)."""
    book = get_book(book_id, conn)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    chapters = [get_chapter(cid, conn) for cid in book.chapter_ids]
    chapters = [ch for ch in chapters if ch is not None]

    if format == "json":
        return {"book": book.to_dict(), "chapters": [ch.to_dict() for ch in chapters]}

    # Markdown
    lines = [f"# {book.title}", ""]
    lines.append(f"**Book ID:** {book.id}  ")
    lines.append(f"**Feature:** {book.feature}  ")
    lines.append(f"**Version:** {book.version}  ")
    lines.append(f"**Created:** {book.created_at}  ")
    if book.parent_book_id:
        lines.append(f"**Parent:** {book.parent_book_id}  ")
    lines.extend(["", "---", ""])
    for i, ch in enumerate(chapters, 1):
        lines.append(f"## Chapter {i}: {ch.id}")
        lines.append(f"\n**Actor:** {ch.actor}  ")
        lines.append(f"**Source:** {ch.source}  ")
        lines.append(f"**Timestamp:** {ch.timestamp}  ")
        if ch.model:
            lines.append(f"**Model:** `{ch.model}`  ")
        if ch.temperature is not None:
            lines.append(f"**Temperature:** {ch.temperature}  ")
        if ch.seed is not None:
            lines.append(f"**Seed:** {ch.seed}  ")
        if ch.validation_status:
            icon = "✅" if ch.validation_status == "passed" else "❌"
            lines.append(f"**Validation:** {icon} {ch.validation_status.upper()} ({ch.validation_message})  ")
        lines.append(f"\n### Prompt\n\n> {ch.prompt}\n")
        lines.append(f"### Result\n\n{ch.result}\n")
        lines.append("---\n")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@app.get("/diff/books", dependencies=[Depends(verify_read_api_key)])
def api_diff_books(
    id_a: str = Query(..., description="First book ID"),
    id_b: str = Query(..., description="Second book ID"),
    conn=Depends(get_db),
):
    """Compare two books — shows added, removed, kept chapters, and a line-by-line semantic diff of changes (v0.2.0 Killer Feature)."""
    import difflib
    book_a = get_book(id_a, conn)
    book_b = get_book(id_b, conn)
    if book_a is None:
        raise HTTPException(status_code=404, detail=f"Book '{id_a}' not found")
    if book_b is None:
        raise HTTPException(status_code=404, detail=f"Book '{id_b}' not found")

    ids_a = set(book_a.chapter_ids)
    ids_b = set(book_b.chapter_ids)

    def chapter_info(cid):
        ch = get_chapter(cid, conn)
        return {"id": cid, "prompt": ch.prompt if ch else "[missing]"}

    steps_comparison = []
    min_len = min(len(book_a.chapter_ids), len(book_b.chapter_ids))
    for idx in range(min_len):
        cid_a = book_a.chapter_ids[idx]
        cid_b = book_b.chapter_ids[idx]
        ch_a = get_chapter(cid_a, conn)
        ch_b = get_chapter(cid_b, conn)
        
        if ch_a and ch_b:
            prompt_diff = list(difflib.ndiff(ch_a.prompt.splitlines(), ch_b.prompt.splitlines()))
            result_diff = list(difflib.ndiff(ch_a.result.splitlines(), ch_b.result.splitlines()))
            steps_comparison.append({
                "step_number": idx + 1,
                "chapter_a": {
                    "id": cid_a,
                    "prompt": ch_a.prompt,
                    "result": ch_a.result,
                    "model": ch_a.model,
                    "temperature": ch_a.temperature,
                    "seed": ch_a.seed
                },
                "chapter_b": {
                    "id": cid_b,
                    "prompt": ch_b.prompt,
                    "result": ch_b.result,
                    "model": ch_b.model,
                    "temperature": ch_b.temperature,
                    "seed": ch_b.seed
                },
                "prompt_diff": prompt_diff,
                "result_diff": result_diff,
                "are_identical": ch_a.prompt == ch_b.prompt and ch_a.result == ch_b.result
            })

    return {
        "book_a": {"id": book_a.id, "version": book_a.version, "title": book_a.title},
        "book_b": {"id": book_b.id, "version": book_b.version, "title": book_b.title},
        "kept": [chapter_info(cid) for cid in sorted(ids_a & ids_b)],
        "added": [chapter_info(cid) for cid in sorted(ids_b - ids_a)],
        "removed": [chapter_info(cid) for cid in sorted(ids_a - ids_b)],
        "steps_comparison": steps_comparison
    }


@app.get("/shelf", dependencies=[Depends(verify_read_api_key)])
def api_shelf(conn=Depends(get_db)):
    """Library view grouped by feature (authenticated)."""
    books = list_books(conn)
    features: dict[str, list] = {}
    for b in books:
        features.setdefault(b.feature, []).append(b.to_dict())
    return features


@app.get("/health")
def health_check(conn=Depends(get_db)):
    """Liveness & Readiness probe verifying database connectivity."""
    try:
        conn.execute("SELECT 1").fetchone()
        return {
            "status": "healthy",
            "database": "connected",
            "version": "0.2.0",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Health check probe failed: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail=f"Service Unhealthy: Database is unreachable or corrupted ({str(e)})"
        )


@app.post("/db/backup", dependencies=[Depends(verify_write_api_key)])
def api_backup_db():
    """Create a point-in-time backup of the SQLite database safely using the online backup API."""
    import sqlite3
    from db import DB_PATH
    logger.info("Starting safe online SQLite database backup.")
    
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"audit_backup_{timestamp}.db"
    
    try:
        # Perform safe point-in-time online backup
        src = get_connection()
        dst = sqlite3.connect(str(backup_file))
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        logger.info(f"Database online backup successfully completed at: {backup_file}")
        return {"status": "success", "backup_file": str(backup_file.name), "timestamp": timestamp}
    except Exception as e:
        logger.error(f"Database online backup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database backup failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    ssl_key = os.environ.get("AUDIT_SSL_KEYFILE", None)
    ssl_cert = os.environ.get("AUDIT_SSL_CERTFILE", None)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        ssl_keyfile=ssl_key,
        ssl_certfile=ssl_cert
    )

