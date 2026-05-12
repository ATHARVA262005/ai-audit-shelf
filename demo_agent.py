"""
Agent Integration Demo — shows how any AI workflow plugs into the Audit API.

Simulates a "Product Review Automation" workflow:
  1. Fetch product reviews
  2. Analyze sentiment
  3. Generate summary report
  4. Notify stakeholders

Each step logs a chapter to the audit server, then all chapters
are bundled into a book.
"""

import requests
import time

API_BASE = "http://localhost:8000"


def log_chapter(prompt: str, result: str, actor: str = "review-agent", source: str = "agent") -> str:
    """Post a chapter to the audit API. Returns the chapter ID."""
    resp = requests.post(f"{API_BASE}/chapter", params={
        "prompt": prompt,
        "result": result,
        "actor": actor,
        "source": source,
    })
    resp.raise_for_status()
    chapter = resp.json()["chapter"]
    print(f"  Logged chapter {chapter['id']}: {prompt[:60]}")
    return chapter["id"]


def create_book(title: str, chapter_ids: list[str], feature: str) -> dict:
    """Bundle chapters into a book via the API."""
    resp = requests.post(f"{API_BASE}/book", params={
        "title": title,
        "feature": feature,
    }, json=chapter_ids)
    resp.raise_for_status()
    book = resp.json()["book"]
    print(f"\n  Book {book['id']} created: \"{title}\" (v{book['version']}, {len(chapter_ids)} chapters)")
    return book


def simulate_workflow():
    """Run a mock AI workflow and log every step."""

    print("=" * 60)
    print("  AGENT DEMO: Product Review Automation")
    print("=" * 60)
    print()

    # --- Step 1: Fetch reviews ---
    print("[Step 1] Fetching product reviews...")
    time.sleep(0.3)
    c1 = log_chapter(
        prompt="Fetch all product reviews from the last 30 days",
        result="Retrieved 247 reviews across 12 products. Top rated: Widget Pro (4.8 avg). Lowest: Gadget Mini (2.1 avg).",
    )

    # --- Step 2: Sentiment analysis ---
    print("[Step 2] Running sentiment analysis...")
    time.sleep(0.3)
    c2 = log_chapter(
        prompt="Analyze sentiment of all reviews and classify as positive/neutral/negative",
        result="Positive: 168 (68%), Neutral: 49 (20%), Negative: 30 (12%). Main complaints: shipping delays (18), battery life (9).",
    )

    # --- Step 3: Generate report ---
    print("[Step 3] Generating summary report...")
    time.sleep(0.3)
    c3 = log_chapter(
        prompt="Generate executive summary report for product team",
        result="Report generated: 3-page PDF with sentiment trends, top complaints, and product-specific breakdowns. Attached to JIRA PROD-4821.",
    )

    # --- Step 4: Notify stakeholders ---
    print("[Step 4] Notifying stakeholders...")
    time.sleep(0.3)
    c4 = log_chapter(
        prompt="Send summary report to product and support leads",
        result="Email sent to 4 recipients (product-lead@, support-lead@, qa-lead@, vp-product@). Slack notification posted to #product-reviews.",
    )

    # --- Bundle into a book ---
    print("\n[Bundling] Creating book from workflow chapters...")
    book = create_book(
        title="Product Review Automation — May 2026",
        chapter_ids=[c1, c2, c3, c4],
        feature="Review Automation",
    )

    # --- Show the result ---
    print("\n" + "=" * 60)
    print("  DONE — Full audit trail available at:")
    print(f"    GET  {API_BASE}/book/{book['id']}")
    print(f"    GET  {API_BASE}/export/book/{book['id']}?format=markdown")
    print(f"    GET  {API_BASE}/docs  (Swagger UI)")
    print("=" * 60)

    return book


if __name__ == "__main__":
    try:
        simulate_workflow()
    except requests.ConnectionError:
        print(f"\nError: Cannot reach {API_BASE}")
        print("Start the API server first:  python api.py")
