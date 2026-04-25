from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_LOG_PATH = ROOT / "agent" / "state_log.jsonl"

from crm.hubspot_writer import update_contact_status, write_timeline_event


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_state_log(entry: dict[str, Any]) -> None:
    STATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_state_log() -> list[dict[str, Any]]:
    if not STATE_LOG_PATH.exists():
        return []
    rows = []
    for line in STATE_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def record_contact_event(
    event_type: str,
    *,
    sender_email: str | None = None,
    phone_number: str | None = None,
    trace_id: str | None = None,
    company: str | None = None,
    channel: str | None = None,
    details: dict[str, Any] | None = None,
    hubspot_status: str | None = None,
    lifecycle_stage: str | None = None,
    stop_automation: bool | None = None,
) -> dict[str, Any]:
    details = details or {}
    timeline_title = event_type.replace("_", " ").title()
    timeline_body = json.dumps(details, indent=2, sort_keys=True)
    hubspot_contact = update_contact_status(
        email=sender_email,
        status=hubspot_status,
        lifecycle_stage=lifecycle_stage,
        extra_properties=(
            {"hs_lead_status": hubspot_status} if hubspot_status else None
        ),
    )
    hubspot_timeline = write_timeline_event(
        email=sender_email,
        title=timeline_title,
        body=timeline_body,
    )
    entry = {
        "timestamp": utc_now(),
        "event_type": event_type,
        "sender_email": sender_email,
        "phone_number": phone_number,
        "trace_id": trace_id,
        "company": company,
        "channel": channel,
        "details": details,
        "hubspot_contact": hubspot_contact,
        "hubspot_timeline": hubspot_timeline,
        "stop_automation": stop_automation,
    }
    append_state_log(entry)
    return entry


def record_handoff(
    reason: str,
    *,
    sender_email: str | None = None,
    trace_id: str | None = None,
    company: str | None = None,
    channel: str | None = None,
) -> dict[str, Any]:
    return record_contact_event(
        "human_handoff",
        sender_email=sender_email,
        trace_id=trace_id,
        company=company,
        channel=channel,
        details={"reason": reason},
        hubspot_status="Needs Human Review",
        stop_automation=True,
    )


def has_recent_event_for_email(
    email: str | None,
    event_type: str,
    *,
    lookback_days: int = 30,
) -> bool:
    if not email:
        return False
    target = email.lower()
    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    for row in reversed(load_state_log()):
        if row.get("event_type") != event_type:
            continue
        if str(row.get("sender_email") or "").lower() != target:
            continue
        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00"))
        except Exception:
            continue
        if timestamp >= cutoff:
            return True
    return False
