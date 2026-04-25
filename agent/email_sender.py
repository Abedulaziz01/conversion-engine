from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.email_composer import compose_email, load_json
from agent.icp_classifier import classify_brief


ENV_PATH = ROOT / ".env"
BRIEF_PATH = ROOT / "enrichment" / "output" / "hiring_signal_brief.json"
EMAIL_LOG_PATH = ROOT / "agent" / "email_log.jsonl"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_log(entry: dict[str, Any]) -> None:
    EMAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EMAIL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def normalize_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_subject(email_text: str, company_name: str, segment: str | None) -> str:
    if segment == "Segment 1":
        return f"Context: {company_name} growth timing"
    if segment == "Segment 2":
        return f"Note on {company_name}"
    if segment == "Segment 3":
        return f"Congrats on the engineering transition"
    if segment == "Segment 4":
        return f"Question on {company_name}'s AI capability"
    return f"Question for {company_name}"


def send_via_resend(recipient: str, subject: str, body: str) -> str:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured")

    from_email = os.getenv("RESEND_TEST_FROM_EMAIL") or os.getenv("TEST_EMAIL_FROM") or "Tenacious <onboarding@resend.dev>"
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "from": from_email,
            "to": [recipient],
            "subject": subject,
            "text": body,
        },
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend send failed with HTTP {response.status_code}: {response.text}")

    payload = response.json()
    return str(payload.get("id") or "")


def deliver_email(
    *,
    composed_email: dict[str, Any],
    recipient: str,
    trace_id: str,
) -> dict[str, Any]:
    live_outbound = normalize_bool(os.getenv("LIVE_OUTBOUND"))
    subject = build_subject(
        composed_email.get("email_text", ""),
        composed_email.get("company", "the company"),
        composed_email.get("segment"),
    )

    if live_outbound:
        message_id = send_via_resend(recipient, subject, composed_email["email_text"])
        sent_or_simulated = "sent"
    else:
        message_id = f"simulated-{trace_id}"
        sent_or_simulated = "simulated"

    log_entry = {
        "event_type": "outbound_email",
        "timestamp": utc_now(),
        "recipient": recipient,
        "subject": subject,
        "variant_tag": composed_email.get("variant"),
        "trace_id": trace_id,
        "sent_or_simulated": sent_or_simulated,
        "message_id": message_id,
        "segment": composed_email.get("segment"),
        "company": composed_email.get("company"),
    }
    append_log(log_entry)
    return log_entry


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    trace_id: str,
    company: str | None = None,
    variant_tag: str = "generic",
) -> dict[str, Any]:
    load_env_file(ENV_PATH)
    composed = {
        "company": company,
        "segment": None,
        "variant": variant_tag,
        "email_text": body,
    }
    live_outbound = normalize_bool(os.getenv("LIVE_OUTBOUND"))
    if live_outbound:
        message_id = send_via_resend(to, subject, body)
        sent_or_simulated = "sent"
    else:
        message_id = f"simulated-{trace_id}"
        sent_or_simulated = "simulated"

    log_entry = {
        "event_type": "outbound_email",
        "timestamp": utc_now(),
        "recipient": to,
        "subject": subject,
        "variant_tag": variant_tag,
        "trace_id": trace_id,
        "sent_or_simulated": sent_or_simulated,
        "message_id": message_id,
        "segment": None,
        "company": company,
    }
    append_log(log_entry)
    return log_entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send or simulate an outbound email")
    parser.add_argument("--company", required=True, help="Company name for the current brief")
    parser.add_argument("--recipient", required=True, help="Recipient email address")
    parser.add_argument("--segment", required=False, help="Force a segment for composition")
    args = parser.parse_args(argv)

    load_env_file(ENV_PATH)

    if not BRIEF_PATH.exists():
        print(json.dumps({"error": f"Brief not found: {BRIEF_PATH}"}, indent=2))
        return 1

    brief = load_json(BRIEF_PATH)
    if (brief.get("company") or "").lower() != args.company.lower():
        print(
            json.dumps(
                {
                    "error": (
                        f"Loaded brief is for '{brief.get('company')}', not '{args.company}'. "
                        "Run build_brief.py for the target company first."
                    )
                },
                indent=2,
            )
        )
        return 1

    classification = classify_brief(brief)
    composed = compose_email(brief, classification, requested_segment=args.segment)
    if "error" in composed:
        print(json.dumps(composed, indent=2))
        return 1

    trace_id = brief.get("crunchbase_id") or f"trace-{args.company.lower().replace(' ', '-')}"
    try:
        result = deliver_email(
            composed_email=composed,
            recipient=args.recipient,
            trace_id=str(trace_id),
        )
    except Exception as exc:
        error_entry = {
            "event_type": "outbound_email",
            "timestamp": utc_now(),
            "recipient": args.recipient,
            "subject": build_subject(composed.get("email_text", ""), composed.get("company", args.company), composed.get("segment")),
            "variant_tag": composed.get("variant"),
            "trace_id": str(trace_id),
            "sent_or_simulated": "failed",
            "message_id": None,
            "error": str(exc),
        }
        append_log(error_entry)
        print(json.dumps({"error": str(exc), "log_entry": error_entry}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
