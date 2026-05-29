

![AI Audit Shelf Cover](aiAuditShelf-cover.jpg)

**Git-like versioning for AI workflows, organized as books and chapters.**

Every AI action gets logged as an immutable "chapter." Chapters bundle into "books" (versioned features). Books live on a "shelf" grouped by feature. Edit a feature? A new edition is created — the old one stays as a permanent audit trail.

Repository: [github.com/ATHARVA262005/ai-audit-shelf](https://github.com/ATHARVA262005/ai-audit-shelf)

> ⭐️ **If you find this project useful, please consider giving it a star!**  
> [ATHARVA262005/ai-audit-shelf](https://github.com/ATHARVA262005/ai-audit-shelf)

[![Stars](https://img.shields.io/github/stars/ATHARVA262005/ai-audit-shelf?style=flat&color=yellow)](https://github.com/ATHARVA262005/ai-audit-shelf/stargazers)
[![Forks](https://img.shields.io/github/forks/ATHARVA262005/ai-audit-shelf?style=flat)](https://github.com/ATHARVA262005/ai-audit-shelf/network/members)
[![Issues](https://img.shields.io/github/issues/ATHARVA262005/ai-audit-shelf.svg)](https://github.com/ATHARVA262005/ai-audit-shelf/issues)
[![Contributors](https://img.shields.io/github/contributors/ATHARVA262005/ai-audit-shelf?color=blue)](https://github.com/ATHARVA262005/ai-audit-shelf/graphs/contributors)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GSSoC 2026](https://img.shields.io/badge/GSSoC-2026-orange)](https://gssoc.girlscript.tech/)

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

## Operator Guide

If you are introducing AI Audit Shelf to a founder, operator, or non-technical teammate, start with the audit problem before the book/chapter metaphor:

- [Audit UX for operators](docs/audit-ux-for-operators.md)

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

**Authentication (breaking change in v0.2.0):** The API now uses JWT + RBAC. The old `AUDIT_API_KEY` / `X-API-Key` flow has been removed.

> ⚠️ **Breaking change:** All endpoints (except `GET /health`) now require a Bearer token. Update any scripts or integrations that used `X-API-Key`.

**Step 1 — Get a token:**

```bash
curl -X POST "http://localhost:8000/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=agent&password=agent123"
# → {"access_token": "<JWT>", "token_type": "bearer"}
```

**Step 2 — Use the token on every request:**

```bash
TOKEN="<paste JWT here>"

# Agent: write chapters and books
curl -X POST "http://localhost:8000/chapter?prompt=Analyze+reviews&result=85%25+positive&actor=agent&source=langchain" \
  -H "Authorization: Bearer $TOKEN"

# Auditor: read data and run diffs
curl "http://localhost:8000/shelf" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/diff/books?id_a=b_001&id_b=b_002" -H "Authorization: Bearer $TOKEN"
```

**Default sandbox accounts** (password = username + `123`):

| Role | Username | Password | Permissions |
|---|---|---|---|
| Admin | `admin` | `admin123` | Full access + DELETE |
| Auditor | `auditor` | `auditor123` | Read-only (GET endpoints) |
| Agent | `agent` | `agent123` | Write-only (POST endpoints) |

Set `AUDIT_JWT_SECRET` env var to override the default signing key in production:

```bash
export AUDIT_JWT_SECRET=your-secret-key
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

The dashboard will show a **login form** on first load. Use any of the sandbox accounts above (e.g. `auditor` / `auditor123` to browse). The JWT is stored in `localStorage` and sent automatically as `Authorization: Bearer` on all requests.

The API URL is auto-detected from `window.location`. To point to a different server, click **⚙️ API URL** in the sidebar or set it via `localStorage`:

```js
localStorage.setItem('auditApiUrl', 'https://my-server.example.com');
```

The dashboard connects to the configured API URL and provides:

- **Library** — bookshelf grouped by feature
- **Books** — table view with export buttons
- **Chapters** — full audit log with detail view
- **Search** — filter by actor, keyword, date
- **Diff** — compare two editions side-by-side

> **API URL config:** If your API server runs on a different port or host, type the URL into the input at the bottom of the sidebar. The value is saved in your browser and persists across reloads.

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

AI Audit Shelf is built to be extremely lightweight and integrate with any AI stack in a few lines of code. 

All detailed, copy-pasteable integration recipes have been consolidated into our dedicated documentation:

👉 **[View Integration Recipes Guide](docs/integration-recipes.md)**

Inside, you will find complete, typed examples for:

* 🐍 **[Python (requests)](docs/integration-recipes.md#python--requests-general-frameworks)** — Simple API wrapper for custom scripts and general frameworks.
* 🦜 **[LangChain Callback Handler](docs/integration-recipes.md#langchain--callback-handler)** — Automatically log all prompt generations and tool executions within LangChain agents.
* 🦙 **[LlamaIndex Callback Handler](docs/integration-recipes.md#llamaindex--callback-handler)** — Track retrieval, query pipelines, and response synthesis without indexing noise.
* 🤖 **[OpenAI Function Calls](docs/integration-recipes.md#openai--function-calls)** — Log direct completions and function calls cleanly.
* ⚡ **[Vercel AI SDK (Next.js)](docs/integration-recipes.md#vercel-ai-sdk--nextjs-app-router)** — A streaming Next.js App Router API endpoint with a background `onFinish` logging callback.
* 🐚 **[Shell Command Wrapper](docs/integration-recipes.md#shell-script--command-wrapper)** — Audit terminal commands, python scripts, and deployment steps.
* 🌐 **[curl / REST Reference](docs/integration-recipes.md#curl-any-language)** — Quick API examples for any other language.

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

---

## Contributors

Thanks to everyone who has contributed to this project! 🎉

[![Contributors](https://contrib.rocks/image?repo=ATHARVA262005/ai-audit-shelf)](https://github.com/ATHARVA262005/ai-audit-shelf/graphs/contributors)

---

## Roadmap

We are actively developing the next version of AI Audit Shelf, focusing heavily on **reproducibility** and **agent pipeline safety**. Here is what we are building next (inspired directly by community feedback!):

* 🧪 **First-Class Reproducibility Parameters:** First-class database support for tracking generation metadata (`model_version`, `temperature`, `seed`, `top_p`) so prompt differences are deterministic.
* 🛑 **Verification & Validation Gates:** Integration of synchronous and asynchronous validation callbacks (hooks) to halt execution flows and flag errors before prompt drift propagates downstream.
* 🔗 **Contextual Session Tracking:** Automatic linking of prompt versions directly to the originating user `session_id` or failing execution context.
* 📦 **Docker Support:** Containerized deployment templates for single-command self-hosting.

Want to help shape these features? Join the discussion on our [Issues tracker](https://github.com/ATHARVA262005/ai-audit-shelf/issues)!

---

## Contributing


All contributions are welcome — from fixing a typo to adding a full integration recipe.

### Ways to contribute

| Type | How |
|---|---|
| 🐛 Bug fix | Open an issue, then a PR |
| 📖 Docs / Recipe | Add an integration example to the README |
| ✨ Feature | Open an issue first to discuss |
| ⭐ No code? | Star the repo — it helps more people find it |

### Good first issues

Looking for a place to start? Check the [`good first issue`](https://github.com/ATHARVA262005/ai-audit-shelf/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) label — these are small, well-defined tasks perfect for first-time contributors.

### How to submit a PR

```bash
# 1. Fork the repo and clone your fork
git clone https://github.com/<your-username>/ai-audit-shelf
cd ai-audit-shelf

# 2. Create a branch
git checkout -b feat/your-feature-name

# 3. Make your changes and commit
git commit -m "feat: describe your change"

# 4. Push and open a PR against main
git push origin feat/your-feature-name
```

For questions, open a [discussion](https://github.com/ATHARVA262005/ai-audit-shelf/discussions) or reach out to [@ATHARVA262005](https://github.com/ATHARVA262005).

---

## License

MIT — see [LICENSE](LICENSE)
