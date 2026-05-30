"""Built-in hook: prints an alert when flagged keywords appear in a chapter result.

Configure flagged keywords via the AUDIT_ALERT_KEYWORDS environment variable
as a comma-separated list. Defaults to: error,exception,failed,critical

Example:
    export AUDIT_ALERT_KEYWORDS="error,unauthorized,timeout"
"""

import logging
import os

logger = logging.getLogger("ai_audit")

_raw = os.environ.get("AUDIT_ALERT_KEYWORDS", "error,exception,failed,critical")
FLAGGED_KEYWORDS = [kw.strip().lower() for kw in _raw.split(",") if kw.strip()]


def on_chapter(chapter: dict) -> None:
    """Alert if the chapter result contains any flagged keywords."""
    result_lower = chapter.get("result", "").lower()
    matched = [kw for kw in FLAGGED_KEYWORDS if kw in result_lower]
    if matched:
        logger.warning(
            f"[keyword_alert] Chapter '{chapter.get('id')}' contains flagged keyword(s): "
            f"{', '.join(matched)}"
        )