"""Built-in hook: posts a chapter summary to a Slack webhook URL.

Requires the AUDIT_SLACK_WEBHOOK environment variable to be set to a valid
Slack Incoming Webhook URL. If the variable is not set, the hook is a no-op.

Example:
    export AUDIT_SLACK_WEBHOOK="https://hooks.slack.com/services/XXX/YYY/ZZZ"
"""

import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger("ai_audit")


def on_chapter(chapter: dict) -> None:
    """Post a chapter summary to Slack if AUDIT_SLACK_WEBHOOK is configured."""
    webhook_url = os.environ.get("AUDIT_SLACK_WEBHOOK", "")
    if not webhook_url:
        return

    prompt_preview = chapter.get("prompt", "")[:100]
    result_preview = chapter.get("result", "")[:100]

    message = {
        "text": (
            f"*New AI Audit Chapter Logged*\n"
            f"*ID:* `{chapter.get('id')}`\n"
            f"*Actor:* {chapter.get('actor')}\n"
            f"*Source:* {chapter.get('source')}\n"
            f"*Timestamp:* {chapter.get('timestamp')}\n"
            f"*Prompt:* {prompt_preview}{'...' if len(chapter.get('prompt', '')) > 100 else ''}\n"
            f"*Result:* {result_preview}{'...' if len(chapter.get('result', '')) > 100 else ''}"
        )
    }

    try:
        data = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                logger.warning(f"[slack_notify] Slack webhook returned status {resp.status}")
    except urllib.error.URLError as e:
        logger.error(f"[slack_notify] Failed to post to Slack: {e}")