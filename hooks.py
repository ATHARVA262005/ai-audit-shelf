"""Plugin hook system for post-chapter callbacks.

Hooks are plain Python callables with the signature:
    def on_chapter(chapter: dict) -> None

They can be registered programmatically via register_hook(), or loaded
automatically from a directory of .py files by setting the AUDIT_HOOKS_DIR
environment variable before starting the server.

Example hook file (e.g. my_hooks/notify.py):
    def on_chapter(chapter: dict) -> None:
        if "error" in chapter["result"].lower():
            print(f"[alert] Error detected in chapter {chapter['id']}")
"""

import importlib.util
import logging
import os
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger("ai_audit")

# Global registry of hook callables
CHAPTER_HOOKS: List[Callable[[dict], None]] = []


def register_hook(fn: Callable[[dict], None]) -> None:
    """Register a callable to be invoked after every chapter is saved."""
    CHAPTER_HOOKS.append(fn)
    logger.info(f"[hooks] Registered hook: {fn.__name__}")


def fire_chapter_hooks(chapter: dict) -> None:
    """Call all registered hooks with the chapter dict.

    Each hook is called in registration order. Errors in individual hooks
    are caught and logged so one bad hook never breaks the others.
    """
    for hook in CHAPTER_HOOKS:
        try:
            hook(chapter)
        except Exception as e:
            logger.error(f"[hooks] Hook '{hook.__name__}' raised an error: {e}")


def load_hooks_from_dir(directory: str) -> None:
    """Auto-load hook modules from a directory.

    Any .py file in the directory that defines an on_chapter(chapter: dict)
    function is imported and registered automatically.

    Args:
        directory: Path to the directory containing hook files.
    """
    path = Path(directory)
    if not path.is_dir():
        logger.warning(f"[hooks] AUDIT_HOOKS_DIR '{directory}' is not a valid directory — skipping.")
        return

    for py_file in sorted(path.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "on_chapter") and callable(module.on_chapter):
                register_hook(module.on_chapter)
                logger.info(f"[hooks] Loaded hook from: {py_file.name}")
            else:
                logger.warning(f"[hooks] Skipped '{py_file.name}' — no callable on_chapter() found.")
        except Exception as e:
            logger.error(f"[hooks] Failed to load hook from '{py_file.name}': {e}")


# Auto-load hooks from AUDIT_HOOKS_DIR on module import
_hooks_dir = os.environ.get("AUDIT_HOOKS_DIR", "")
if _hooks_dir:
    load_hooks_from_dir(_hooks_dir)