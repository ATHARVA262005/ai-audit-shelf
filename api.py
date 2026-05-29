"""FastAPI server for the AI Audit system."""

import json
import os
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import OAuth2PasswordRequestForm

from models import Chapter, Book
from db import get_connection, init_db, next_id, save_chapter, get_chapter, list_chapters, save_book, get_book, list_books, get_user
from auth import RoleChecker, create_access_token, verify_password

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


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def get_db():
    """Dependency that provides a database connection."""
    conn = get_connection()
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


# --- Authentication Endpoint ---

@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), conn=Depends(get_db)):
    """Authenticate user and return access JWT token."""
    user = get_user(form_data.username, conn)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": user["username"], "role": user["role"]})
    return {"access_token": access_token, "token_type": "bearer"}


# --- Chapters ---

@app.post("/chapter", response_model=dict, dependencies=[Depends(RoleChecker(["agent"]))])
async def api_add_chapter(
    prompt: str,
    result: str,
    actor: str = "anonymous",
    source: str = "manual",
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    validation_status: Optional[str] = None,
    validation_message: Optional[str] = None,
    conn=Depends(get_db),
):
    """Log a new chapter (atomic AI action). Restricted to Agents and Admins."""
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
        validation_status=validation_status,
        validation_message=validation_message,
    )
    save_chapter(chapter, conn)

    chapter_dict = chapter.to_dict()
    await manager.broadcast({"type": "NEW_CHAPTER", "data": chapter_dict})

    return {"status": "created", "chapter": chapter_dict}


@app.post("/chapter/{chapter_id}/validate", response_model=dict, dependencies=[Depends(RoleChecker(["agent"]))])
def api_validate_chapter(
    chapter_id: str,
    required_keywords: Optional[list[str]] = Query(None),
    regex_pattern: Optional[str] = None,
    json_format: bool = False,
    conn=Depends(get_db),
):
    """Run a validation gate check on a logged chapter's output."""
    chapter = get_chapter(chapter_id, conn)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")

    import re
    passed = True
    reasons = []

    if regex_pattern:
        try:
            if not re.search(regex_pattern, chapter.result):
                passed = False
                reasons.append(f"Result did not match regex pattern '{regex_pattern}'")
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {e}")

    if required_keywords:
        missing = [kw for kw in required_keywords if kw.lower() not in chapter.result.lower()]
        if missing:
            passed = False
            reasons.append(f"Missing required keywords: {', '.join(missing)}")

    if json_format:
        try:
            json.loads(chapter.result)
        except json.JSONDecodeError:
            passed = False
            reasons.append("Result is not a valid JSON document")

    chapter.validation_status = "passed" if passed else "failed"
    chapter.validation_message = "Validation passed." if passed else " | ".join(reasons)

    conn.execute(
        "UPDATE chapters SET validation_status = ?, validation_message = ? WHERE id = ?",
        (chapter.validation_status, chapter.validation_message, chapter.id),
    )
    conn.commit()

    return {
        "chapter_id": chapter_id,
        "validation_status": chapter.validation_status,
        "validation_message": chapter.validation_message,
        "chapter": chapter.to_dict(),
    }


@app.get("/chapters", response_model=list[dict], dependencies=[Depends(RoleChecker(["auditor"]))])
def api_list_chapters(conn=Depends(get_db)):
    """List all chapters. Restricted to Auditors and Admins."""
    return [ch.to_dict() for ch in list_chapters(conn)]


@app.get("/chapter/{chapter_id}", response_model=dict, dependencies=[Depends(RoleChecker(["auditor", "agent"]))])
def api_get_chapter(chapter_id: str, conn=Depends(get_db)):
    """Get a single chapter by ID. Restricted to Agents, Auditors and Admins."""
    ch = get_chapter(chapter_id, conn)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")
    return ch.to_dict()


@app.get("/search/chapters", response_model=list[dict], dependencies=[Depends(RoleChecker(["auditor"]))])
def api_search_chapters(
    actor: Optional[str] = None,
    keyword: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    conn=Depends(get_db),
):
    """Search chapters by actor, keyword, or date range. Restricted to Auditors and Admins."""
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

@app.post("/book", response_model=dict, dependencies=[Depends(RoleChecker(["agent"]))])
async def api_create_book(
    title: str,
    chapter_ids: list[str],
    feature: Optional[str] = None,
    conn=Depends(get_db),
):
    """Bundle chapters into a book. Restricted to Agents and Admins."""
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

    book_dict = book.to_dict()
    await manager.broadcast({"type": "NEW_BOOK", "data": book_dict})

    return {"status": "created", "book": book_dict}


@app.get("/books", response_model=list[dict], dependencies=[Depends(RoleChecker(["auditor", "agent"]))])
def api_list_books(conn=Depends(get_db)):
    """List all books. Restricted to Agents, Auditors and Admins."""
    return [b.to_dict() for b in list_books(conn)]


@app.get("/book/{book_id}", response_model=dict, dependencies=[Depends(RoleChecker(["auditor", "agent"]))])
def api_get_book(book_id: str, conn=Depends(get_db)):
    """Get a single book by ID. Restricted to Agents, Auditors and Admins."""
    b = get_book(book_id, conn)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    return b.to_dict()


@app.post("/book/{book_id}/edition", response_model=dict, dependencies=[Depends(RoleChecker(["agent"]))])
async def api_new_edition(
    book_id: str,
    title: Optional[str] = None,
    chapter_ids: Optional[list[str]] = None,
    conn=Depends(get_db),
):
    """Create a new edition of a book (version bump). Restricted to Agents and Admins."""
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

    book_dict = new_book.to_dict()
    await manager.broadcast({"type": "NEW_BOOK", "data": book_dict})

    return {"status": "created", "book": book_dict}


# --- Export & Diff ---

@app.get("/export/book/{book_id}", dependencies=[Depends(RoleChecker(["auditor"]))])
def api_export_book(
    book_id: str,
    format: str = Query("json", pattern="^(json|markdown)$"),
    conn=Depends(get_db),
):
    """Export a book with all its chapters. Restricted to Auditors and Admins."""
    book = get_book(book_id, conn)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    chapters = [get_chapter(cid, conn) for cid in book.chapter_ids]
    chapters = [ch for ch in chapters if ch is not None]

    if format == "json":
        return {"book": book.to_dict(), "chapters": [ch.to_dict() for ch in chapters]}

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


@app.get("/diff/books", dependencies=[Depends(RoleChecker(["auditor"]))])
def api_diff_books(
    id_a: str = Query(..., description="First book ID"),
    id_b: str = Query(..., description="Second book ID"),
    conn=Depends(get_db),
):
    """Compare two books. Restricted to Auditors and Admins."""
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


@app.get("/shelf", dependencies=[Depends(RoleChecker(["auditor"]))])
def api_shelf(conn=Depends(get_db)):
    """Library view grouped by feature. Restricted to Auditors and Admins."""
    books = list_books(conn)
    features: dict[str, list] = {}
    for b in books:
        features.setdefault(b.feature, []).append(b.to_dict())
    return features


# --- Admin Exclusive Administrative Endpoints ---

@app.delete("/chapter/{chapter_id}", status_code=200, dependencies=[Depends(RoleChecker([]))])
def api_delete_chapter(chapter_id: str, conn=Depends(get_db)):
    """Delete a specific chapter. Restricted strictly to Admin role only."""
    if get_chapter(chapter_id, conn) is None:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")
    conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
    conn.commit()
    return {"status": "deleted", "target": chapter_id}


@app.delete("/book/{book_id}", status_code=200, dependencies=[Depends(RoleChecker([]))])
def api_delete_book(book_id: str, conn=Depends(get_db)):
    """Delete a specific book. Restricted strictly to Admin role only."""
    if get_book(book_id, conn) is None:
        raise HTTPException(status_code=404, detail=f"Book '{book_id}' not found")
    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    return {"status": "deleted", "target": book_id}


@app.get("/health")
def health_check():
    return {
        "status": "OK",
        "version": "0.1.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)