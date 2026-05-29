import os
os.environ["AUDIT_DEV_MODE"] = "true"
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

# Add project root to sys.path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock database path for testing
TEST_DB_PATH = Path(__file__).parent / "test_audit.db"

# Override DB_PATH in db module before importing
import db
db.DB_PATH = TEST_DB_PATH

from models import Chapter, Book
from db import init_db, get_connection, save_chapter, get_chapter, list_chapters, save_book, get_book, list_books, next_id
from api import app

# Create FastAPI TestClient
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    """Fixture to ensure a fresh, clean database for each test run."""
    # Ensure test database exists and is fully initialized
    conn = get_connection(TEST_DB_PATH)
    init_db(conn)
    
    # Truncate all tables and reset sequence counters to ensure absolute pristine states across runs
    conn.execute("DELETE FROM chapters")
    conn.execute("DELETE FROM books")
    conn.execute("UPDATE counters SET value = 0")
    conn.commit()
    conn.close()
    
    yield



# --- SQLite DB Layer Tests ---

def test_init_db_and_counters():
    """Verify database initialization, tables structure, and counter seeds."""
    conn = get_connection(TEST_DB_PATH)
    
    # Check tables exist
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "chapters" in tables
    assert "books" in tables
    assert "counters" in tables

    # Check counter seeds
    cursor.execute("SELECT * FROM counters")
    counters = {row["name"]: row["value"] for row in cursor.fetchall()}
    assert counters["chapter"] == 0
    assert counters["book"] == 0
    
    conn.close()


def test_chapter_crud_with_reproducibility():
    """Test saving and loading chapters with optional reproducibility fields."""
    conn = get_connection(TEST_DB_PATH)
    
    # 1. Test chapter with fully loaded parameters
    ch1 = Chapter(
        id="c_001",
        prompt="Write a sorting algorithm",
        result="def qsort...",
        actor="dev-agent",
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="agent-framework",
        model="gpt-4o",
        temperature=0.2,
        seed=101,
        metadata={"tokens": 150}
    )
    save_chapter(ch1, conn)

    # 2. Test chapter with defaults / missing optional fields
    ch2 = Chapter(
        id="c_002",
        prompt="Simple test",
        result="Success",
        actor="user",
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    save_chapter(ch2, conn)

    # 3. Retrieve and assert correctness
    loaded_ch1 = get_chapter("c_001", conn)
    assert loaded_ch1 is not None
    assert loaded_ch1.id == "c_001"
    assert loaded_ch1.model == "gpt-4o"
    assert loaded_ch1.temperature == 0.2
    assert loaded_ch1.seed == 101
    assert loaded_ch1.metadata == {"tokens": 150}

    loaded_ch2 = get_chapter("c_002", conn)
    assert loaded_ch2 is not None
    assert loaded_ch2.id == "c_002"
    assert loaded_ch2.model is None
    assert loaded_ch2.temperature is None
    assert loaded_ch2.seed is None

    # 4. List chapters
    all_chapters = list_chapters(conn)
    assert len(all_chapters) == 2
    assert all_chapters[0].id == "c_002"  # Newest first sorting order
    assert all_chapters[1].id == "c_001"

    conn.close()


def test_book_crud_and_versioning():
    """Test saving, fetching, and grouping books."""
    conn = get_connection(TEST_DB_PATH)

    b1 = Book(
        id="b_001",
        title="Agent V1",
        chapter_ids=["c_001", "c_002"],
        version=1,
        feature="Text Generation",
        created_at=datetime.now(timezone.utc).isoformat(),
        parent_book_id=None,
        metadata={"accuracy": 0.92}
    )
    save_book(b1, conn)

    loaded_b1 = get_book("b_001", conn)
    assert loaded_b1 is not None
    assert loaded_b1.title == "Agent V1"
    assert loaded_b1.chapter_ids == ["c_001", "c_002"]
    assert loaded_b1.version == 1
    assert loaded_b1.feature == "Text Generation"
    assert loaded_b1.metadata == {"accuracy": 0.92}

    all_books = list_books(conn)
    assert len(all_books) == 1
    assert all_books[0].id == "b_001"

    conn.close()


def test_sequential_counters():
    """Test that sequential counters increase atomically."""
    conn = get_connection(TEST_DB_PATH)
    
    id1 = next_id(conn, "chapter")
    id2 = next_id(conn, "chapter")
    id3 = next_id(conn, "book")

    assert id1 == "c_001"
    assert id2 == "c_002"
    assert id3 == "b_001"

    conn.close()


# --- FastAPI HTTP API Integration Tests ---

def test_api_health():
    """Test API health check endpoint and database connectivity validation."""
    response = client.get("/health")
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "healthy"
    assert res["database"] == "connected"
    assert res["version"] == "0.2.0"
    assert "timestamp" in res


def test_api_db_backup():
    """Test that authenticated database online backup is triggered and executes successfully."""
    response = client.post("/db/backup")
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "success"
    assert "backup_file" in res
    assert "timestamp" in res
    
    # Assert backup file is physically generated
    from pathlib import Path
    from db import DB_PATH
    backup_file_path = DB_PATH.parent / "backups" / res["backup_file"]
    assert backup_file_path.exists()
    
    # Clean up backup artifact
    try:
        backup_file_path.unlink()
    except OSError:
        pass


def test_api_add_and_list_chapters():
    """Test adding and listing chapters through FastAPI."""
    # 1. Post new chapter with reproducibility settings
    response = client.post(
        "/chapter",
        params={
            "prompt": "Hello AI",
            "result": "Hello User",
            "actor": "tester",
            "source": "api-test",
            "model": "gpt-3.5-turbo",
            "temperature": 0.7,
            "seed": 999
        }
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "created"
    assert res_data["chapter"]["id"] == "c_001"
    assert res_data["chapter"]["model"] == "gpt-3.5-turbo"
    assert res_data["chapter"]["temperature"] == 0.7
    assert res_data["chapter"]["seed"] == 999

    # 2. Get list of chapters
    response = client.get("/chapters")
    assert response.status_code == 200
    chapters = response.json()
    assert len(chapters) == 1
    assert chapters[0]["id"] == "c_001"
    assert chapters[0]["model"] == "gpt-3.5-turbo"


def test_api_get_chapter_by_id():
    """Test getting single chapter by ID or raising 404."""
    # Attempt non-existent
    response = client.get("/chapter/c_999")
    assert response.status_code == 404

    # Seed one and query
    client.post(
        "/chapter",
        params={"prompt": "Short prompt", "result": "Short result"}
    )
    response = client.get("/chapter/c_001")
    assert response.status_code == 200
    assert response.json()["id"] == "c_001"


def test_api_search_chapters():
    """Test endpoint keyword, actor, and date filters."""
    # Add two chapters
    client.post("/chapter", params={"prompt": "Apple pie", "result": "Yum", "actor": "chef"})
    client.post("/chapter", params={"prompt": "Banana split", "result": "Sweet", "actor": "chef"})
    client.post("/chapter", params={"prompt": "Apple tree", "result": "Green", "actor": "gardener"})

    # Search keyword
    response = client.get("/search/chapters", params={"keyword": "Apple"})
    assert response.status_code == 200
    assert len(response.json()) == 2

    # Search actor
    response = client.get("/search/chapters", params={"actor": "chef"})
    assert response.status_code == 200
    assert len(response.json()) == 2

    # Search both
    response = client.get("/search/chapters", params={"actor": "chef", "keyword": "Apple"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_api_create_and_version_books():
    """Test book creation, versioning, and feature shelf grouping."""
    # 1. Seed two chapters
    client.post("/chapter", params={"prompt": "Step 1", "result": "Done"})
    client.post("/chapter", params={"prompt": "Step 2", "result": "Done"})

    # 2. Create Book
    response = client.post(
        "/book",
        params={"title": "RAG Flow", "feature": "Search RAG"},
        json=["c_001", "c_002"]
    )
    assert response.status_code == 200
    book = response.json()["book"]
    assert book["id"] == "b_001"
    assert book["version"] == 1

    # 3. Bump version (new edition)
    client.post("/chapter", params={"prompt": "Step 3", "result": "Done"})
    response = client.post(
        "/book/b_001/edition",
        params={"title": "RAG Flow Premium"},
        json=["c_001", "c_002", "c_003"]
    )
    assert response.status_code == 200
    new_book = response.json()["book"]
    assert new_book["id"] == "b_002"
    assert new_book["version"] == 2
    assert new_book["parent_book_id"] == "b_001"

    # 4. Check library shelf endpoint
    response = client.get("/shelf")
    assert response.status_code == 200
    shelf = response.json()
    assert "Search RAG" in shelf
    assert len(shelf["Search RAG"]) == 2


def test_api_book_exports():
    """Test JSON and Markdown serialization exports including model details."""
    client.post(
        "/chapter",
        params={
            "prompt": "Core Task",
            "result": "Completed",
            "model": "gpt-4o",
            "temperature": 0.5,
            "seed": 42
        }
    )
    client.post(
        "/book",
        params={"title": "Model Export Flow", "feature": "Exports"},
        json=["c_001"]
    )

    # 1. Check JSON export
    response = client.get("/export/book/b_001", params={"format": "json"})
    assert response.status_code == 200
    assert response.json()["book"]["id"] == "b_001"
    assert response.json()["chapters"][0]["model"] == "gpt-4o"

    # 2. Check Markdown export contains model parameters
    response = client.get("/export/book/b_001", params={"format": "markdown"})
    assert response.status_code == 200
    markdown_content = response.text
    assert "# Model Export Flow" in markdown_content
    assert "**Model:** `gpt-4o`" in markdown_content
    assert "**Temperature:** 0.5" in markdown_content
    assert "**Seed:** 42" in markdown_content


def test_api_diff_books():
    """Test book comparison differences."""
    client.post("/chapter", params={"prompt": "Step A", "result": "Original output"})
    client.post("/chapter", params={"prompt": "Step A updated", "result": "Modified output"})
    
    client.post("/book", params={"title": "Original version"}, json=["c_001"])
    client.post("/book", params={"title": "Updated version"}, json=["c_002"])

    response = client.get("/diff/books", params={"id_a": "b_001", "id_b": "b_002"})
    assert response.status_code == 200
    diff_data = response.json()
    
    # Verify semantic step comparisons for v0.2.0
    assert "steps_comparison" in diff_data
    assert len(diff_data["steps_comparison"]) == 1
    step = diff_data["steps_comparison"][0]
    assert step["step_number"] == 1
    assert step["chapter_a"]["id"] == "c_001"
    assert step["chapter_b"]["id"] == "c_002"
    assert step["are_identical"] is False
    assert any(x.startswith("- ") for x in step["prompt_diff"])
    assert any(x.startswith("+ ") for x in step["prompt_diff"])


def test_api_validation_gates():
    """Test Validation Gates endpoints, regexes, keywords, and JSON format checks."""
    # 1. Test posting a chapter with custom validation details loaded initially
    response = client.post(
        "/chapter",
        params={
            "prompt": "Say hello",
            "result": "Hello world",
            "validation_status": "passed",
            "validation_message": "Pre-validated"
        }
    )
    assert response.status_code == 200
    assert response.json()["chapter"]["validation_status"] == "passed"
    assert response.json()["chapter"]["validation_message"] == "Pre-validated"

    # 2. Test dynamic validation gate - Successful Regex and Keyword check
    response = client.post(
        "/chapter/c_001/validate",
        params={
            "required_keywords": ["hello", "world"],
            "regex_pattern": "^Hello"
        }
    )
    assert response.status_code == 200
    res = response.json()
    assert res["validation_status"] == "passed"
    assert res["validation_message"] == "Validation passed."

    # 3. Test dynamic validation gate - Failing keyword check
    response = client.post(
        "/chapter/c_001/validate",
        params={
            "required_keywords": ["hello", "mars"]
        }
    )
    assert response.status_code == 200
    res = response.json()
    assert res["validation_status"] == "failed"
    assert "mars" in res["validation_message"]

    # 4. Test dynamic validation gate - Successful JSON format check
    client.post(
        "/chapter",
        params={
            "prompt": "Get details as json",
            "result": '{"status": "complete", "score": 95}'
        }
    )
    response = client.post(
        "/chapter/c_002/validate",
        params={"json_format": True}
    )
    assert response.status_code == 200
    assert response.json()["validation_status"] == "passed"

    # 5. Test dynamic validation gate - Failing JSON format check
    client.post(
        "/chapter",
        params={
            "prompt": "Get details as faulty json",
            "result": "{bad_json: complete}"
        }
    )
    response = client.post(
        "/chapter/c_003/validate",
        params={"json_format": True}
    )
    assert response.status_code == 200
    assert response.json()["validation_status"] == "failed"
    assert "not a valid JSON document" in response.json()["validation_message"]


def test_api_pagination():
    """Test pagination limits and offsets on list and search endpoints."""
    # Seed 5 unique chapters
    for i in range(1, 6):
        client.post(
            "/chapter",
            json={"prompt": f"Prompt {i}", "result": f"Result {i}", "actor": "PaginationTester"}
        )

    # 1. Test limit of 2 chapters
    response = client.get("/chapters", params={"limit": 2})
    assert response.status_code == 200
    res = response.json()
    assert len(res) == 2

    # 2. Test offset
    response = client.get("/chapters", params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    res_offset = response.json()
    assert len(res_offset) == 2
    # Ensure they are different
    assert res[0]["id"] != res_offset[0]["id"]

    # 3. Test search pagination
    response = client.get("/search/chapters", params={"actor": "PaginationTester", "limit": 2, "offset": 1})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_redos_regex_timeout():
    """Test that catastrophic backtracking ReDoS pattern times out safely instead of freezing the thread."""
    client.post(
        "/chapter",
        json={"prompt": "ReDoS prompt", "result": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab"}
    )
    # Catastrophic backtracking pattern: (a+)+$
    # We query the validate endpoint on c_004 (or the new chapter ID)
    # Find latest logged chapter ID first
    latest_chapters = client.get("/chapters", params={"limit": 1}).json()
    latest_id = latest_chapters[0]["id"]

    response = client.post(
        f"/chapter/{latest_id}/validate",
        params={"regex_pattern": "(a+)+$"}
    )
    assert response.status_code == 200
    # Should report failed due to timeout
    assert response.json()["validation_status"] == "failed"
    assert "timed out" in response.json()["validation_message"]


def test_input_boundaries():
    """Test size-bounded validations for prompts and results."""
    huge_prompt = "a" * 60000
    # JSON body validation
    response = client.post(
        "/chapter",
        json={"prompt": huge_prompt, "result": "short"}
    )
    assert response.status_code == 422  # Pydantic validation fails

    # Query param fallback validation
    response = client.post(
        "/chapter",
        params={"prompt": huge_prompt, "result": "short"}
    )
    assert response.status_code == 400


def test_concurrent_id_generation():
    """Test that concurrent next_id sequential counter runs are thread-safe and never collide."""
    import concurrent.futures
    from db import get_connection, next_id

    ids = []
    def get_next_book_id():
        conn = get_connection()
        try:
            return next_id(conn, "book")
        finally:
            conn.close()

    # Use ThreadPoolExecutor to generate 15 sequential IDs concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(get_next_book_id) for _ in range(15)]
        for f in concurrent.futures.as_completed(futures):
            ids.append(f.result())

    # Assert that all 15 generated IDs are fully unique
    assert len(ids) == 15
    assert len(set(ids)) == 15


def test_cli_operations(capsys):
    """Test all CLI commands inside cli.py using mock arguments and capsys output inspections."""
    import argparse
    import cli
    from db import get_connection

    # Clear active test DB data first to ensure clean state
    conn = get_connection()
    try:
        from db import init_db
        init_db(conn)
        conn.execute("DELETE FROM chapters")
        conn.execute("DELETE FROM books")
        conn.execute("DELETE FROM counters")
        conn.commit()
    finally:
        conn.close()

    # 1. Test CLI add-chapter command
    add_args = argparse.Namespace(
        prompt="Initial prompt check",
        result="Initial model result response",
        actor="cli_tester",
        source="unit_test",
        model="gpt-4o",
        temperature=0.7,
        seed=101
    )
    cli.cmd_add_chapter(add_args)
    captured = capsys.readouterr()
    assert "Chapter c_001 logged." in captured.out

    # 2. Test CLI list-chapters command
    cli.cmd_list_chapters(None)
    captured = capsys.readouterr()
    assert "c_001" in captured.out
    assert "Initial prompt check" in captured.out

    # 3. Test CLI show-chapter command
    show_ch_args = argparse.Namespace(chapter_id="c_001")
    cli.cmd_show_chapter(show_ch_args)
    captured = capsys.readouterr()
    assert "Chapter: c_001" in captured.out
    assert "Actor:   cli_tester" in captured.out
    assert "Source:  unit_test" in captured.out
    assert "Model:   gpt-4o" in captured.out
    assert "Temp:    0.7" in captured.out
    assert "Seed:    101" in captured.out

    # 4. Test CLI create-book command
    create_bk_args = argparse.Namespace(
        title="CLI Integration Book",
        chapter_ids=["c_001"],
        feature="CLI Features"
    )
    cli.cmd_create_book(create_bk_args)
    captured = capsys.readouterr()
    assert "Book b_001 created:" in captured.out

    # 5. Test CLI list-books command
    cli.cmd_list_books(None)
    captured = capsys.readouterr()
    assert "b_001" in captured.out
    assert "v1" in captured.out
    assert "CLI Integration Book" in captured.out

    # 6. Test CLI show-book command
    show_bk_args = argparse.Namespace(book_id="b_001")
    cli.cmd_show_book(show_bk_args)
    captured = capsys.readouterr()
    assert "Book:     b_001" in captured.out
    assert "Feature:  CLI Features" in captured.out

    # 7. Test CLI new-edition command
    add_args2 = argparse.Namespace(
        prompt="Second prompt check",
        result="Second model result",
        actor="cli_tester",
        source="unit_test",
        model="gpt-4o",
        temperature=0.7,
        seed=102
    )
    cli.cmd_add_chapter(add_args2)
    captured = capsys.readouterr()
    
    new_ed_args = argparse.Namespace(
        book_id="b_001",
        title="CLI Integration Book v2",
        chapter_ids=["c_001", "c_002"]
    )
    cli.cmd_new_edition(new_ed_args)
    captured = capsys.readouterr()
    assert "Book b_002 created as v2" in captured.out

    # 8. Test CLI shelf command
    cli.cmd_shelf(None)
    captured = capsys.readouterr()
    assert "LIBRARY SHELF" in captured.out
    assert "[CLI Features]" in captured.out
    assert "b_001 v1" in captured.out
    assert "b_002 v2" in captured.out

    # 9. Test CLI export-book command (JSON format)
    export_json_args = argparse.Namespace(book_id="b_001", format="json")
    cli.cmd_export_book(export_json_args)
    captured = capsys.readouterr()
    assert '"id": "b_001"' in captured.out
    assert '"title": "CLI Integration Book"' in captured.out

    # 10. Test CLI export-book command (Markdown format)
    export_md_args = argparse.Namespace(book_id="b_001", format="markdown")
    cli.cmd_export_book(export_md_args)
    captured = capsys.readouterr()
    assert "# CLI Integration Book" in captured.out
    assert "**Book ID:** b_001" in captured.out

    # 11. Test CLI search-chapters command
    search_args = argparse.Namespace(
        actor="cli_tester",
        keyword="prompt",
        after=None,
        before=None
    )
    cli.cmd_search_chapters(search_args)
    captured = capsys.readouterr()
    assert "c_001" in captured.out
    assert "c_002" in captured.out

    # 12. Test CLI diff-books command (including steps semantic diffs!)
    diff_args = argparse.Namespace(book_a="b_001", book_b="b_002")
    cli.cmd_diff_books(diff_args)
    captured = capsys.readouterr()
    assert "DIFF: b_001 (v1) -> b_002 (v2)" in captured.out
    assert "STEP-BY-STEP SEMANTIC CHANGES" in captured.out
    assert "Step 1: c_001 -> c_001 [IDENTICAL]" in captured.out
