# Integration Recipes

AI Audit Shelf is designed to plug into any part of your AI stack in a few lines of code. This guide contains copy-pasteable snippets showing how to log chapters and bundle books across different frameworks and languages.

---

## Table of Contents

* [Python — requests (General Frameworks)](#python--requests-general-frameworks)
* [LangChain — Callback Handler](#langchain--callback-handler)
* [LlamaIndex — Callback Handler](#llamaindex--callback-handler)
* [OpenAI — Function Calls](#openai--function-calls)
* [Vercel AI SDK — Next.js App Router](#vercel-ai-sdk--nextjs-app-router)
* [Shell Script — Command Wrapper](#shell-script--command-wrapper)
* [curl (Any Language)](#curl-any-language)

---

## Python — requests (General Frameworks)

If you are using raw Python or any custom framework, you can use `requests` to log actions directly.

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

## LangChain — Callback Handler

This handler logs every single LLM call and tool execution automatically inside your LangChain agents.

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

## LlamaIndex — Callback Handler

This handler captures indexing, retrieval, and synthesis events inside your LlamaIndex pipelines.

```python
import requests
from typing import Optional, Dict, List, Any
from llama_index.core.callbacks import CallbackManager, CBEventType
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import EventPayload  # Requires llama-index-core >= 0.10

API = "http://localhost:8000"


class AuditCallbackHandler(BaseCallbackHandler):
    """Logs LlamaIndex query and LLM synthesis events to the AI Audit server."""

    def __init__(self, actor: str = "llamaindex-agent"):
        # Ignore background noise (chunking, tokenization, embedding) — track only QUERY and LLM
        all_events = list(CBEventType)
        all_events.remove(CBEventType.QUERY)
        all_events.remove(CBEventType.LLM)

        super().__init__(
            event_starts_to_ignore=all_events,
            event_ends_to_ignore=all_events,
        )
        self.actor = actor
        self._chapters: List[str] = []
        self._event_prompts: Dict[str, str] = {}

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs,
    ) -> str:
        if not payload:
            return event_id

        if event_type == CBEventType.QUERY:
            self._event_prompts[event_id] = payload.get(EventPayload.QUERY_STR, "")
        elif event_type == CBEventType.LLM:
            messages = payload.get(EventPayload.MESSAGES, [])
            prompt = payload.get(EventPayload.PROMPT, "")
            # Handle both chat message lists and raw prompt strings
            self._event_prompts[event_id] = str(messages[0]) if messages else str(prompt)

        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs,
    ) -> None:
        if not payload:
            return

        prompt = self._event_prompts.pop(event_id, "")
        result = ""

        if event_type == CBEventType.QUERY:
            response = payload.get(EventPayload.RESPONSE)
            result = str(response) if response else ""

        elif event_type == CBEventType.LLM:
            response = payload.get(EventPayload.RESPONSE)
            if response:
                # Handle both ChatResponse (.message.content) and CompletionResponse (.text)
                if hasattr(response, "message") and response.message:
                    result = response.message.content
                elif hasattr(response, "text"):
                    result = response.text
                else:
                    result = str(response)

        if prompt or result:
            chapter_id = self._log(prompt=prompt, result=result, event_type=event_type.value)
            if chapter_id:
                self._chapters.append(chapter_id)

    def _log(self, prompt: str, result: str, event_type: str = "") -> Optional[str]:
        try:
            resp = requests.post(
                f"{API}/chapter",
                params={
                    "prompt": f"[{event_type}] {prompt}"[:2000],
                    "result": result[:2000],
                    "actor": self.actor,
                    "source": "llamaindex",
                },
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()["chapter"]["id"]
        except Exception as e:
            print(f"Failed to log event to AI Audit server: {e}")
            return None

    def bundle(self, title: str, feature: str = "") -> dict:
        """Bundle all logged chapters into a book and clear tracking state."""
        if not self._chapters:
            return {"message": "No chapters logged to bundle."}

        try:
            resp = requests.post(
                f"{API}/book",
                params={
                    "title": title,
                    "feature": feature or title,
                },
                json=self._chapters,
                timeout=5,
            )
            resp.raise_for_status()
            book = resp.json()["book"]
            # Clear state only after a successful bundle
            self._chapters = []
            self._event_prompts = {}
            return book
        except Exception as e:
            print(f"Failed to bundle chapters: {e}")
            return {}

    def start_trace(self, trace_id: Optional[str] = None) -> None:
        pass

    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        pass


# Usage Example
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings

# 1. Initialize the handler — indexing noise is filtered out automatically
handler = AuditCallbackHandler(actor="rag-pipeline")
Settings.callback_manager = CallbackManager([handler])

# 2. Build the index and query engine (chunking/embedding events are ignored)
documents = SimpleDirectoryReader("./docs").load_data()
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()

# 3. Execute queries — handler fires only for QUERY and LLM events
response = query_engine.query("What are the key findings in Q1?")
print(response)

# 4. Bundle all logged chapters into a book
book = handler.bundle("Q1 RAG Query", feature="RAG Automation")
print(f"Audited successfully! Book created: {book.get('id')}")
```

---

## OpenAI — Function Calls

For direct OpenAI SDK integrations using function calling.

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

## Vercel AI SDK — Next.js App Router

A typed Next.js route handler utilizing `onFinish` to silently log prompts and streaming outputs in the background.

```typescript
// app/api/chat/route.ts
import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";

const AUDIT_API = process.env.AUDIT_API_URL ?? "http://localhost:8000";
const AUDIT_API_KEY = process.env.AUDIT_API_KEY ?? "";

async function logChapter(prompt: any, result: string): Promise<void> {
  try {
    const promptString = typeof prompt === "string" ? prompt : JSON.stringify(prompt);

    await fetch(`${AUDIT_API}/chapter?` + new URLSearchParams({
      prompt: `[Vercel AISDK] ${promptString}`.slice(0, 2000),
      result: result.slice(0, 2000),
      actor: "vercel-ai-sdk",
      source: "nextjs",
    }), {
      method: "POST",
      headers: {
        ...(AUDIT_API_KEY ? { "X-API-Key": AUDIT_API_KEY } : {}),
      },
      keepalive: true, 
    });
  } catch (err) {
    console.error("Failed to log chapter to AI Audit server:", err);
  }
}

export async function POST(req: Request) {
  const { messages } = await req.json();

  const lastUserMessage = [...messages]
    .reverse()
    .find((m: { role: string }) => m.role === "user")?.content ?? "";

  const result = streamText({
    model: openai("gpt-4o"),
    messages,
    onFinish: async ({ text }) => {
      await logChapter(lastUserMessage, text);
    },
  });

  return result.toDataStreamResponse();
}
```

---

## Shell Script — Command Wrapper

Wrap any shell script or CLI tool to audit deployments, tests, or builds.

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

## curl (Any Language)

Simple commands to curl the API.

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
