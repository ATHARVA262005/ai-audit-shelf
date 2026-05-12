# 🦾 AI Audit

**Git-like versioning for AI workflows, organized as books and chapters.**

Every AI action gets logged as an immutable "chapter." Chapters bundle into "books" (versioned features). Books live on a "shelf" grouped by feature. Edit a feature? A new edition is created — the old one stays as a permanent audit trail.

```
Library
  └── [Feature: HR Automation]
        ├── b_001 v1  Employee Onboarding (4 chapters)
        └── b_002 v2  Employee Onboarding (5 chapters)  ← edits b_001
  └── [Feature: Reporting]
        └── b_003 v1  Monthly Reporting (3 chapters)
```

---

## Why

AI workflows are opaque. Prompts go in, results come out, and nobody can trace what happened. AI Audit gives you:

- **Full audit trail** — every prompt, result, actor, and timestamp is immutable
- **Feature-level versioning** — edits create new editions, old ones are preserved
- **Human-readable exports** — JSON for machines, Markdown for auditors
- **Works everywhere** — CLI, REST API, web dashboard, or one-line SDK calls

---

## Quick Start

### Prerequisites

- Python 3.10+
- No external dependencies for CLI (stdlib only)
- `fastapi` and `uvicorn` for the API server

```bash
pip install fastapi uvicorn
```

---

### 1. CLI

Log actions, bundle into books, browse the shelf.

```bash
# Log chapters
python cli.py add-chapter "Summarize Q1 sales" "Revenue up 15%" --actor alice --source claude
python cli.py add-chapter "Email report to team" "Sent to 5 managers" --actor bob --source copilot

# Bundle into a book
python cli.py create-book "Q1 Reporting" c_001 c_002 --feature "Reporting"

# Browse
python cli.py shelf
python cli.py show-book b_001
python cli.py list-chapters

# Create a new edition when requirements change
python cli.py add-chapter "Add regional breakdown" "APAC +22%, EMEA +8%" --actor alice --source claude
python cli.py new-edition b_001 --chapter-ids c_001 c_002 c_003

# Diff editions
python cli.py diff-books b_001 b_002

# Export for auditors
python cli.py export-book b_001 --format markdown
python cli.py export-book b_001 --format json

# Search
python cli.py search-chapters --actor alice
python cli.py search-chapters --keyword "sales"
python cli.py search-chapters --after "2026-05-01"
```

---

### 2. API Server

Start the server, then call it from any tool or language.

```bash
python api.py
```

Server runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

```bash
# Log a chapter
curl -X POST "http://localhost:8000/chapter?prompt=Analyze+reviews&result=85%25+positive&actor=agent&source=langchain"

# Create a book (title/feature as query params, chapter_ids as JSON body)
curl -X POST "http://localhost:8000/book?title=Review%20Analysis&feature=Reviews" \
  -H "Content-Type: application/json" \
  -d '["c_001", "c_002"]'

# Browse
curl http://localhost:8000/shelf
curl http://localhost:8000/books
curl http://localhost:8000/chapters

# Diff two editions
curl "http://localhost:8000/diff/books?id_a=b_001&id_b=b_002"

# Export
curl "http://localhost:8000/export/book/b_001?format=markdown"
```

**Auth (optional):** Set `AUDIT_API_KEY` env var to require `X-API-Key` header on write endpoints.

```bash
export AUDIT_API_KEY=secret123
# Now POST requests need: -H "X-API-Key: secret123"
```

---

### 3. Web Dashboard

Visual interface for browsing, searching, and diffing.

```bash
# Start the API server
python api.py

# Open the dashboard
open dashboard.html    # macOS
start dashboard.html   # Windows
xdg-open dashboard.html  # Linux
```

The dashboard connects to `http://localhost:8000` and provides:

- **Library** — bookshelf grouped by feature
- **Books** — table view with export buttons
- **Chapters** — full audit log with detail view
- **Search** — filter by actor, keyword, date
- **Diff** — compare two editions side-by-side

---

### 4. Agent Demo

See how any AI workflow plugs into the audit system.

```bash
# Terminal 1: start the server
python api.py

# Terminal 2: run the demo
python demo_agent.py
```

The demo simulates a "Product Review Automation" workflow — 4 steps, each logged as a chapter, then bundled into a book. The pattern is the same for any agent.

---

## Integration Recipes

### Python — requests (any framework)

```python
import requests

API = "http://localhost:8000"

def log_chapter(prompt: str, result: str, actor: str = "my-agent") -> str:
    """Log an action. Returns the chapter ID."""
    resp = requests.post(f"{API}/chapter", params={
        "prompt": prompt,
        "result": result,
        "actor": actor,
        "source": "my-app",
    })
    return resp.json()["chapter"]["id"]

def bundle_book(title: str, chapter_ids: list[str], feature: str = "") -> dict:
    """Bundle chapters into a book."""
    resp = requests.post(f"{API}/book", params={
        "title": title,
        "feature": feature or title,
    }, json=chapter_ids)
    return resp.json()["book"]

# Usage
c1 = log_chapter("Translate doc to Spanish", "Translation complete, 2400 words")
c2 = log_chapter("Review translation quality", "Score: 94/100, 3 minor corrections")
book = bundle_book("Translation Pipeline", [c1, c2])
print(f"Created {book['id']}")
```

---

### LangChain — Callback Handler

```python
from langchain.callbacks.base import BaseCallbackHandler
import requests

API = "http://localhost:8000"

class AuditCallbackHandler(BaseCallbackHandler):
    """Logs every LLM call to the AI Audit server."""

    def __init__(self, actor: str = "langchain-agent"):
        self.actor = actor
        self._chapters = []

    def on_llm_end(self, response, **kwargs):
        prompt = response.generations[0][0].text if response.generations else ""
        chapter_id = self._log(
            prompt=str(kwargs.get("prompts", [""]))[0],
            result=prompt,
        )
        self._chapters.append(chapter_id)

    def on_tool_end(self, output: str, **kwargs):
        chapter_id = self._log(
            prompt=f"Tool: {kwargs.get('name', 'unknown')}",
            result=output[:2000],
        )
        self._chapters.append(chapter_id)

    def _log(self, prompt: str, result: str) -> str:
        resp = requests.post(f"{API}/chapter", params={
            "prompt": prompt,
            "result": result,
            "actor": self.actor,
            "source": "langchain",
        })
        return resp.json()["chapter"]["id"]

    def bundle(self, title: str, feature: str = "") -> dict:
        """Bundle all logged chapters into a book."""
        resp = requests.post(f"{API}/book", params={
            "title": title,
            "feature": feature or title,
        }, json=self._chapters)
        return resp.json()["book"]


# Usage
from langchain.chat_models import ChatOpenAI
from langchain.agents import initialize_agent, Tool

handler = AuditCallbackHandler(actor="support-bot")

llm = ChatOpenAI(model="gpt-4", callbacks=[handler])
agent = initialize_agent(
    tools=[Tool(name="Search", func=lambda q: "results...", description="Search docs")],
    llm=llm,
    callbacks=[handler],
)

agent.run("Find the refund policy for EU customers")
handler.bundle("EU Refund Lookup", feature="Support Automation")
```

---

### OpenAI — Function Calls

```python
from openai import OpenAI
import requests
import json

API = "http://localhost:8000"
client = OpenAI()

def log_chapter(prompt: str, result: str) -> str:
    resp = requests.post(f"{API}/chapter", params={
        "prompt": prompt,
        "result": result,
        "actor": "openai-agent",
        "source": "openai",
    })
    return resp.json()["chapter"]["id"]

def run_with_audit(user_message: str):
    """Run an OpenAI call with full audit logging."""
    # Log the request
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": user_message}],
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                },
            },
        }],
    )

    msg = response.choices[0].message
    result = msg.content or json.dumps(msg.tool_calls[0].function.model_dump())

    chapter_id = log_chapter(prompt=user_message, result=result)
    print(f"Logged as {chapter_id}")
    return result

# Usage
run_with_audit("What's the weather in Tokyo?")
```

---

### Shell Script

```bash
#!/bin/bash
# audit-wrap.sh — wrap any command and log its execution

API="http://localhost:8000"
ACTOR="${AUDIT_ACTOR:-shell}"
PROMPT="$1"
shift
RESULT=$("$@" 2>&1)
EXIT_CODE=$?

# Log to audit server
CHAPTER_ID=$(curl -s -X POST "$API/chapter" \
  --data-urlencode "prompt=$PROMPT" \
  --data-urlencode "result=$RESULT" \
  --data-urlencode "actor=$ACTOR" \
  --data-urlencode "source=shell" \
  | python -c "import sys,json; print(json.load(sys.stdin)['chapter']['id'])")

echo "Audit: $CHAPTER_ID (exit $EXIT_CODE)"
exit $EXIT_CODE
```

Usage:

```bash
# Wrap any command
./audit-wrap.sh "Deploy to staging" ./deploy.sh staging
./audit-wrap.sh "Run test suite" pytest tests/

# Set a custom actor
AUDIT_ACTOR="ci-bot" ./audit-wrap.sh "Build release" make build
```

---

### curl (any language)

```bash
# Log a chapter
curl -X POST "http://localhost:8000/chapter" \
  -G \
  --data-urlencode "prompt=Analyze customer churn" \
  --data-urlencode "result=Churn rate: 4.2%, down from 5.1%" \
  --data-urlencode "actor=data-agent" \
  --data-urlencode "source=custom"

# Create a book (title/feature as query params, chapter_ids as JSON body)
curl -X POST "http://localhost:8000/book?title=Churn%20Analysis%20Q1&feature=Analytics" \
  -H "Content-Type: application/json" \
  -d '["c_001", "c_002", "c_003"]'
```

---

## Project Structure

```
aiAudit/
├── models.py         # Chapter and Book dataclasses
├── db.py             # SQLite storage layer
├── cli.py            # CLI (11 commands)
├── api.py            # FastAPI server (11 endpoints)
├── dashboard.html    # Web UI (single file, no build)
├── demo_agent.py     # Integration demo
└── audit.db          # SQLite database (auto-created)
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chapter` | Log a new chapter |
| GET | `/chapters` | List all chapters |
| GET | `/chapter/{id}` | Get a chapter by ID |
| GET | `/search/chapters` | Search by actor, keyword, date |
| POST | `/book` | Create a book from chapter IDs |
| GET | `/books` | List all books |
| GET | `/book/{id}` | Get a book by ID |
| POST | `/book/{id}/edition` | Create new edition (version bump) |
| GET | `/export/book/{id}` | Export as JSON or `?format=markdown` |
| GET | `/diff/books` | Compare two books (`?id_a=X&id_b=Y`) |
| GET | `/shelf` | Library grouped by feature |

Full interactive docs at `http://localhost:8000/docs` when the server is running.

---

## License

MIT
