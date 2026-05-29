"""FastAPI server for the AI Audit system."""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from models import Chapter, Book
from db import get_connection, init_db, next_id, save_chapter, get_chapter, list_chapters, save_book, get_book, list_books

app = FastAPI(
    title="AI Audit API",
    description="Git-like versioning for AI workflows, organized as books and chapters.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("AUDIT_API_KEY", "")


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Simple API key auth. Set AUDIT_API_KEY env var to enable."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_db():
    """Dependency that provides a database connection."""
    conn = get_connection()
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


# --- Chapters ---

@app.post("/chapter", response_model=dict, dependencies=[Depends(verify_api_key)])
def api_add_chapter(
    prompt: str,
    result: str,
    actor: str = "anonymous",
    source: str = "manual",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    conn=Depends(get_db),
):
    """Log a new chapter (atomic AI action)."""
    chapter_id = next_id(conn, "chapter")
    chapter = Chapter(
        id=chapter_id,
        prompt=prompt,
        result=result,
        actor=actor,
        timestamp=datetime.now(timezone.utc).isoformat(),
        source=source,
        model=model,
        temperature=temperature,
        seed=seed,
    )
    save_chapter(chapter, conn)
    return {"status": "created", "chapter": chapter.to_dict()}



@app.get("/chapters", response_model=list[dict])
def api_list_chapters(conn=Depends(get_db)):
    """List all chapters."""
    return [ch.to_dict() for ch in list_chapters(conn)]


@app.get("/chapter/{chapter_id}", response_model=dict)
def api_get_chapter(chapter_id: str, conn=Depends(get_db)):
    """Get a single chapter by ID."""
    ch = get_chapter(chapter_id, conn)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")
    return ch.to_dict()


@app.get("/search/chapters", response_model=list[dict])
def api_search_chapters(
    actor: Optional[str] = None,
    keyword: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    conn=Depends(get_db),
):
    """Search chapters by actor, keyword, or date range."""
    results = list_chapters(conn)
    if actor:
        results = [ch for ch in results if ch.actor.lower() == actor.lower()]
    if keyword:
        kw = keyword.lower()
        results = [ch for ch in results if kw in ch.prompt.lower() or kw in ch.result.lower()]
    if after:
        results = [ch for ch in results if ch.timestamp >= after]
    if before:
        results = [ch for ch in results if ch.timestamp <= before]
    return [ch.to_dict() for ch in results]


# --- Books ---

@app.post("/book", response_model=dict, dependencies=[Depends(verify_api_key)])
def api_create_book(
    title: str,
    chapter_ids: list[str],
    feature: Optional[str] = None,
    conn=Depends(get_db),
):
    """Bundle chapters into a book."""
    for cid in chapter_ids:
        if get_chapter(cid, conn) is None:
            raise HTTPException(status_code=400, detail=f"Chapter '{cid}' not found")
    book_id = next_id(conn, "book")
    book = Book(
        id=book_id,
        title=title,
        chapter_ids=chapter_ids,
        version=1,
        feature=feature or title,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_book(book, conn)
    return {"status": "created", "book": book.to_dict()}


@app.get("/books", response_model=list[dict])
def api_list_books(conn=Depends(get_db)):
    """List all books."""
    return [b.to_dict() for b in list_books(conn)]


@app.get("/book/{book_id}", response_model=dict)
def api_get_book(book_id: str, conn=Depends(get_db)):
    """Get a single book by ID."""
    b = get_book(book_id, conn)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    return b.to_dict()


@app.post("/book/{book_id}/edition", response_model=dict, dependencies=[Depends(verify_api_key)])
def api_new_edition(
    book_id: str,
    title: Optional[str] = None,
    chapter_ids: Optional[list[str]] = None,
    conn=Depends(get_db),
):
    """Create a new edition of a book (version bump)."""
    parent = get_book(book_id, conn)
    if parent is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    final_chapters = chapter_ids or parent.chapter_ids
    for cid in final_chapters:
        if get_chapter(cid, conn) is None:
            raise HTTPException(status_code=400, detail=f"Chapter '{cid}' not found")
    new_id = next_id(conn, "book")
    new_book = Book(
        id=new_id,
        title=title or parent.title,
        chapter_ids=final_chapters,
        version=parent.version + 1,
        feature=parent.feature,
        created_at=datetime.now(timezone.utc).isoformat(),
        parent_book_id=parent.id,
    )
    save_book(new_book, conn)
    return {"status": "created", "book": new_book.to_dict()}


# --- Export & Diff ---

@app.get("/export/book/{book_id}")
def api_export_book(
    book_id: str,
    format: str = Query("json", pattern="^(json|markdown)$"),
    conn=Depends(get_db),
):
    """Export a book with all its chapters."""
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
        lines.append(f"\n### Prompt\n\n> {ch.prompt}\n")
        lines.append(f"### Result\n\n{ch.result}\n")
        lines.append("---\n")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")



@app.get("/diff/books")
def api_diff_books(
    id_a: str = Query(..., description="First book ID"),
    id_b: str = Query(..., description="Second book ID"),
    conn=Depends(get_db),
):
    """Compare two books — shows added, removed, and kept chapters."""
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

    return {
        "book_a": {"id": book_a.id, "version": book_a.version},
        "book_b": {"id": book_b.id, "version": book_b.version},
        "kept": [chapter_info(cid) for cid in sorted(ids_a & ids_b)],
        "added": [chapter_info(cid) for cid in sorted(ids_b - ids_a)],
        "removed": [chapter_info(cid) for cid in sorted(ids_a - ids_b)],
    }


@app.get("/shelf")
def api_shelf(conn=Depends(get_db)):
    """Library view grouped by feature."""
    books = list_books(conn)
    features: dict[str, list] = {}
    for b in books:
        features.setdefault(b.feature, []).append(b.to_dict())
    return features


@app.get("/health")
def health_check():
    return {
        "status": "OK",
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
