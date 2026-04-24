from __future__ import annotations

from typing import Any


def qualify_reply(reply_event: dict[str, Any]) -> dict[str, Any]:
    """
    Lightweight qualification handoff.

    The richer qualification logic can grow from here, but the reply handler
    already has a concrete downstream function to trigger.
    """

    body = str(reply_event.get("body_text") or "").lower()
    sender = reply_event.get("sender_email")

    if any(token in body for token in ["interested", "yes", "book", "call", "talk"]):
        status = "engaged"
    elif any(token in body for token in ["not interested", "stop", "unsubscribe", "remove"]):
        status = "disqualified"
    else:
        status = "needs_review"

    return {
        "sender_email": sender,
        "qualification_status": status,
        "trace_id": reply_event.get("trace_id"),
    }
