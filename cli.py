"""CLI interface for the AI Audit system."""

import argparse
import json
import sys
import contextlib
from datetime import datetime, timezone

from models import Chapter, Book
from db import get_connection, init_db, next_id, save_chapter, get_chapter, list_chapters, save_book, get_book, list_books


def cmd_add_chapter(args):
    """Log a new chapter (atomic AI action)."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        chapter_id = next_id(conn, "chapter")
        chapter = Chapter(
            id=chapter_id,
            prompt=args.prompt,
            result=args.result,
            actor=args.actor or "anonymous",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=args.source or "manual",
            model=args.model,
            temperature=args.temperature,
            seed=args.seed,
        )
        save_chapter(chapter, conn)
    print(f"Chapter {chapter_id} logged.")


def cmd_list_chapters(args):
    limit = getattr(args, 'limit', None)
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        chapters = list_chapters(conn, limit=limit)
    if not chapters:
        print("No chapters yet.")
        return
    print(f"{'ID':<8} {'Timestamp':<28} {'Prompt'}")
    print("-" * 80)
    for ch in chapters:
        prompt_short = ch.prompt[:45] + "..." if len(ch.prompt) > 45 else ch.prompt
        print(f"{ch.id:<8} {ch.timestamp:<28} {prompt_short}")


def cmd_show_chapter(args):
    """Show details of a specific chapter."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        chapter = get_chapter(args.chapter_id, conn)
    if chapter is None:
        print(f"Chapter '{args.chapter_id}' not found.")
        return
    print(f"Chapter: {chapter.id}")
    print(f"Actor:   {chapter.actor}")
    print(f"Source:  {chapter.source}")
    print(f"Time:    {chapter.timestamp}")
    if chapter.model:
        print(f"Model:   {chapter.model}")
    if chapter.temperature is not None:
        print(f"Temp:    {chapter.temperature}")
    if chapter.seed is not None:
        print(f"Seed:    {chapter.seed}")
    if chapter.validation_status:
        status_label = f"[{chapter.validation_status.upper()}]"
        print(f"Gate:    {status_label} - {chapter.validation_message}")
    print(f"\nPrompt:\n  {chapter.prompt}")
    print(f"\nResult:\n  {chapter.result}")
    if chapter.metadata:
        print(f"\nMetadata: {chapter.metadata}")


def cmd_create_book(args):
    """Bundle chapters into a book (feature)."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)

        # Validate chapter IDs exist
        for cid in args.chapter_ids:
            if get_chapter(cid, conn) is None:
                print(f"Error: Chapter '{cid}' not found.")
                return

        book_id = next_id(conn, "book")
        book = Book(
            id=book_id,
            title=args.title,
            chapter_ids=args.chapter_ids,
            version=1,
            feature=args.feature or args.title,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        save_book(book, conn)
    print(f"Book {book_id} created: \"{args.title}\" with {len(args.chapter_ids)} chapters.")


def cmd_list_books(args):
    limit = getattr(args, 'limit', None)
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        books = list_books(conn, limit=limit)
    if not books:
        print("Bookshelf is empty.")
        return
    print(f"{'ID':<8} {'Ver':<5} {'Chapters':<10} {'Title'}")
    print("-" * 60)
    for b in books:
        print(f"{b.id:<8} v{b.version:<4} {len(b.chapter_ids):<10} {b.title}")


def cmd_show_book(args):
    """Show details and chapters of a book."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        book = get_book(args.book_id, conn)
        if book is None:
            print(f"Book '{args.book_id}' not found.")
            return

        print(f"Book:     {book.id}")
        print(f"Title:    {book.title}")
        print(f"Feature:  {book.feature}")
        print(f"Version:  {book.version}")
        print(f"Created:  {book.created_at}")
        if book.parent_book_id:
            print(f"Parent:   {book.parent_book_id}")
        print(f"\nChapters ({len(book.chapter_ids)}):")
        print("-" * 60)
        for cid in book.chapter_ids:
            ch = get_chapter(cid, conn)
            if ch:
                prompt_short = ch.prompt[:50] + "..." if len(ch.prompt) > 50 else ch.prompt
                print(f"  {ch.id:<8} {prompt_short}")
            else:
                print(f"  {cid:<8} [missing]")


def cmd_new_edition(args):
    """Create a new edition of a book (version bump with modifications)."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)

        parent = get_book(args.book_id, conn)
        if parent is None:
            print(f"Book '{args.book_id}' not found.")
            return

        # Validate new chapter IDs
        chapter_ids = args.chapter_ids or parent.chapter_ids
        for cid in chapter_ids:
            if get_chapter(cid, conn) is None:
                print(f"Error: Chapter '{cid}' not found.")
                return

        new_book_id = next_id(conn, "book")
        new_book = Book(
            id=new_book_id,
            title=args.title or parent.title,
            chapter_ids=chapter_ids,
            version=parent.version + 1,
            feature=parent.feature,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent_book_id=parent.id,
        )
        save_book(new_book, conn)
    print(f"Book {new_book_id} created as v{new_book.version} of \"{new_book.title}\" (parent: {parent.id}).")


def cmd_shelf(args):
    """Display the library organized by feature."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        books = list_books(conn)
    if not books:
        print("Library is empty.")
        return

    # Group by feature
    features: dict[str, list[Book]] = {}
    for b in books:
        features.setdefault(b.feature, []).append(b)

    print("LIBRARY SHELF")
    print("=" * 60)
    for feature, feature_books in features.items():
        print(f"\n[{feature}]")
        for b in feature_books:
            marker = "  " if b.version == 1 else "  *"
            print(f"{marker} {b.id} v{b.version} - {b.title} ({len(b.chapter_ids)} chapters)")
    print()


def cmd_export_book(args):
    """Export a book as JSON or Markdown."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        book = get_book(args.book_id, conn)
        if book is None:
            print(f"Book '{args.book_id}' not found.")
            return

        chapters = []
        for cid in book.chapter_ids:
            ch = get_chapter(cid, conn)
            if ch:
                chapters.append(ch)

    if args.format == "json":
        data = {
            "book": book.to_dict(),
            "chapters": [ch.to_dict() for ch in chapters],
        }
        print(json.dumps(data, indent=2))
    elif args.format == "markdown":
        print(f"# {book.title}")
        print(f"\n**Book ID:** {book.id}  ")
        print(f"**Feature:** {book.feature}  ")
        print(f"**Version:** {book.version}  ")
        print(f"**Created:** {book.created_at}  ")
        if book.parent_book_id:
            print(f"**Parent:** {book.parent_book_id}  ")
        print(f"\n---\n")
        for i, ch in enumerate(chapters, 1):
            print(f"## Chapter {i}: {ch.id}")
            print(f"\n**Actor:** {ch.actor}  ")
            print(f"**Source:** {ch.source}  ")
            print(f"**Timestamp:** {ch.timestamp}  ")
            print(f"\n### Prompt\n\n> {ch.prompt}\n")
            print(f"### Result\n\n{ch.result}\n")
            if ch.metadata:
                print(f"### Metadata\n\n```json\n{json.dumps(ch.metadata, indent=2)}\n```\n")
            print("---\n")


def cmd_search_chapters(args):
    """Search chapters by actor, keyword, or date range."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        chapters = list_chapters(conn)

    results = chapters
    if args.actor:
        results = [ch for ch in results if ch.actor.lower() == args.actor.lower()]
    if args.keyword:
        kw = args.keyword.lower()
        results = [ch for ch in results if kw in ch.prompt.lower() or kw in ch.result.lower()]
    if args.after:
        results = [ch for ch in results if ch.timestamp >= args.after]
    if args.before:
        results = [ch for ch in results if ch.timestamp <= args.before]

    if not results:
        print("No matching chapters found.")
        return
    print(f"{'ID':<8} {'Actor':<12} {'Source':<10} {'Timestamp':<28} {'Prompt'}")
    print("-" * 100)
    for ch in results:
        prompt_short = ch.prompt[:35] + "..." if len(ch.prompt) > 35 else ch.prompt
        print(f"{ch.id:<8} {ch.actor:<12} {ch.source:<10} {ch.timestamp:<28} {prompt_short}")


def cmd_diff_books(args):
    """Compare two book editions — show added/removed/changed chapters."""
    with contextlib.closing(get_connection()) as conn:
        init_db(conn)
        book_a = get_book(args.book_a, conn)
        book_b = get_book(args.book_b, conn)
        if book_a is None:
            print(f"Book '{args.book_a}' not found.")
            return
        if book_b is None:
            print(f"Book '{args.book_b}' not found.")
            return

        ids_a = set(book_a.chapter_ids)
        ids_b = set(book_b.chapter_ids)

        added = ids_b - ids_a
        removed = ids_a - ids_b
        kept = ids_a & ids_b

        print(f"DIFF: {book_a.id} (v{book_a.version}) -> {book_b.id} (v{book_b.version})")
        print("=" * 60)

        if kept:
            print(f"\n  Kept ({len(kept)}):")
            for cid in sorted(kept):
                ch = get_chapter(cid, conn)
                label = ch.prompt[:50] if ch else "[missing]"
                print(f"    = {cid}  {label}")

        if added:
            print(f"\n  Added ({len(added)}):")
            for cid in sorted(added):
                ch = get_chapter(cid, conn)
                label = ch.prompt[:50] if ch else "[missing]"
                print(f"    + {cid}  {label}")

        if removed:
            print(f"\n  Removed ({len(removed)}):")
            for cid in sorted(removed):
                ch = get_chapter(cid, conn)
                label = ch.prompt[:50] if ch else "[missing]"
                print(f"    - {cid}  {label}")

        if not added and not removed:
            print("\n  No chapter changes between these editions.")

        # Step-by-Step Semantic Comparison for prompt engineers
        min_len = min(len(book_a.chapter_ids), len(book_b.chapter_ids))
        if min_len > 0:
            print("\n" + "=" * 60)
            print("  STEP-BY-STEP SEMANTIC CHANGES")
            print("=" * 60)
            import difflib
            for idx in range(min_len):
                cid_a = book_a.chapter_ids[idx]
                cid_b = book_b.chapter_ids[idx]
                ch_a = get_chapter(cid_a, conn)
                ch_b = get_chapter(cid_b, conn)
                if ch_a and ch_b:
                    identical = (ch_a.prompt == ch_b.prompt and ch_a.result == ch_b.result)
                    status_lbl = "IDENTICAL" if identical else "MODIFIED"
                    print(f"\nStep {idx+1}: {cid_a} -> {cid_b} [{status_lbl}]")
                    if not identical:
                        # Print unified diff of prompt and result
                        if ch_a.prompt != ch_b.prompt:
                            print("  Prompt Changes:")
                            p_diff = difflib.unified_diff(
                                ch_a.prompt.splitlines(),
                                ch_b.prompt.splitlines(),
                                fromfile="prompt_v1",
                                tofile="prompt_v2",
                                lineterm=""
                            )
                            for d_line in p_diff:
                                print(f"    {d_line}")
                        if ch_a.result != ch_b.result:
                            print("  Result/Output Changes:")
                            r_diff = difflib.unified_diff(
                                ch_a.result.splitlines(),
                                ch_b.result.splitlines(),
                                fromfile="result_v1",
                                tofile="result_v2",
                                lineterm=""
                            )
                            for d_line in r_diff:
                                print(f"    {d_line}")


__version__ = "0.2.0"

def main():
    parser = argparse.ArgumentParser(
        prog="audit",
        description="AI Audit - Git-like versioning for AI workflows, organized as books and chapters.",
    )
    parser.add_argument("--version", action="version", version=f"AI Audit CLI v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # add-chapter
    p = sub.add_parser("add-chapter", help="Log a new chapter (atomic AI action)")
    p.add_argument("prompt", help="The prompt/instruction")
    p.add_argument("result", help="The output/result")
    p.add_argument("--actor", help="Who triggered this action")
    p.add_argument("--source", help="Source system (e.g., claude, copilot, manual)")
    p.add_argument("--model", help="Model name or version (e.g. gpt-4o)")
    p.add_argument("--temperature", type=float, help="Generation temperature (e.g. 0.7)")
    p.add_argument("--seed", type=int, help="Generation random seed")
    p.set_defaults(func=cmd_add_chapter)


    # list-chapters
    p = sub.add_parser("list-chapters", help="List all chapters")
    p.add_argument("--limit", type=int, default=None, metavar="N",
               help="Show only the N most recent chapters")
    p.set_defaults(func=cmd_list_chapters)

    # show-chapter
    p = sub.add_parser("show-chapter", help="Show chapter details")
    p.add_argument("chapter_id", help="Chapter ID (e.g., c_001)")
    p.set_defaults(func=cmd_show_chapter)

    # create-book
    p = sub.add_parser("create-book", help="Bundle chapters into a book")
    p.add_argument("title", help="Book title")
    p.add_argument("chapter_ids", nargs="+", help="Chapter IDs to include")
    p.add_argument("--feature", help="Feature/category (defaults to title)")
    p.set_defaults(func=cmd_create_book)

    # list-books
    p = sub.add_parser("list-books", help="List all books")
    p.add_argument("--limit", type=int, default=None, metavar="N",
               help="Show only the N most recent books")
    p.set_defaults(func=cmd_list_books)

    # show-book
    p = sub.add_parser("show-book", help="Show book details and chapters")
    p.add_argument("book_id", help="Book ID (e.g., b_001)")
    p.set_defaults(func=cmd_show_book)

    # new-edition
    p = sub.add_parser("new-edition", help="Create a new edition of a book")
    p.add_argument("book_id", help="Parent book ID")
    p.add_argument("--title", help="New title (optional, keeps parent title)")
    p.add_argument("--chapter-ids", nargs="+", help="New chapter list (optional, keeps parent chapters)")
    p.set_defaults(func=cmd_new_edition)

    # shelf
    p = sub.add_parser("shelf", help="Display the library organized by feature")
    p.set_defaults(func=cmd_shelf)

    # export-book
    p = sub.add_parser("export-book", help="Export a book as JSON or Markdown")
    p.add_argument("book_id", help="Book ID (e.g., b_001)")
    p.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format (default: json)")
    p.set_defaults(func=cmd_export_book)

    # search-chapters
    p = sub.add_parser("search-chapters", help="Search chapters by actor, keyword, or date range")
    p.add_argument("--actor", help="Filter by actor name")
    p.add_argument("--keyword", help="Search in prompt and result text")
    p.add_argument("--after", help="Show chapters after this ISO timestamp")
    p.add_argument("--before", help="Show chapters before this ISO timestamp")
    p.set_defaults(func=cmd_search_chapters)

    # diff-books
    p = sub.add_parser("diff-books", help="Compare two book editions")
    p.add_argument("book_a", help="First book ID")
    p.add_argument("book_b", help="Second book ID")
    p.set_defaults(func=cmd_diff_books)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
