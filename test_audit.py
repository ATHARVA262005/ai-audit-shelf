import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

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
    # Delete test database if it exists
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass

    # Initialize a fresh database schema
    conn = get_connection(TEST_DB_PATH)
    init_db(conn)
    conn.close()

    yield

    # Clean up test database after the test
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except OSError:
            pass


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
    """Test API health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "OK", "version": "0.1.0"}


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
    client.post("/chapter", params={"prompt": "Step A", "result": "A"})
    client.post("/chapter", params={"prompt": "Step B", "result": "B"})
    
    client.post("/book", params={"title": "Original"}, json=["c_001"])
    client.post("/book", params={"title": "Updated"}, json=["c_001", "c_002"])

    response = client.get("/diff/books", params={"id_a": "b_001", "id_b": "b_002"})
    assert response.status_code == 200
    diff_data = response.json()
    assert len(diff_data["kept"]) == 1
    assert diff_data["kept"][0]["id"] == "c_001"
    assert len(diff_data["added"]) == 1
    assert diff_data["added"][0]["id"] == "c_002"
    assert len(diff_data["removed"]) == 0



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

