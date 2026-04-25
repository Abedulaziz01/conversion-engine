from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


HANDOFF_LOG_PATH = ROOT / "agent" / "handoff_log.jsonl"
from agent.state_manager import record_handoff


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_handoff_log(entry: dict[str, Any]) -> None:
    HANDOFF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HANDOFF_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def handoff_to_human(
    reason: str,
    *,
    sender_email: str | None = None,
    trace_id: str | None = None,
    company: str | None = None,
) -> dict[str, Any]:
    state_entry = record_handoff(
        reason,
        sender_email=sender_email,
        trace_id=trace_id,
        company=company,
        channel="shared",
    )
    entry = {
        "timestamp": utc_now(),
        "reason": reason,
        "sender_email": sender_email,
        "trace_id": trace_id,
        "company": company,
        "hubspot_activity_timeline": "logged_for_human_follow_up",
        "hubspot_contact_status": "Needs Human Review",
        "automated_follow_up_stopped": True,
        "state_sync": state_entry,
    }
    append_handoff_log(entry)
    return entry


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print('Usage: python agent/human_handoff.py "hostile_reply"')
        return 1

    result = handoff_to_human(argv[1])
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
