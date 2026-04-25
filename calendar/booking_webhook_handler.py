from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.email_sender import send_email
from agent.state_manager import record_contact_event


load_dotenv()

app = Flask(__name__)

BOOKING_LOG = ROOT / "calendar" / "booking_log.jsonl"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_log(entry: dict) -> None:
    BOOKING_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BOOKING_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@app.route("/webhooks/booking-confirmed", methods=["POST"])
def booking_confirmed():
    data = request.json

    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        attendee = (data.get("payload", {}).get("attendees") or [])[0]
        name = attendee.get("name", "Unknown")
        email = attendee.get("email", "")
        booked_time = data.get("payload", {}).get("startTime", "")
        duration = data.get("payload", {}).get("eventDuration", 30)
        notes = data.get("payload", {}).get("description", "")
    except (KeyError, IndexError) as exc:
        return jsonify({"error": f"Bad payload: {exc}"}), 400

    log_entry = {
        "logged_at": utc_now(),
        "name": name,
        "email": email,
        "booked_time": booked_time,
        "duration": duration,
        "notes": notes,
    }
    append_log(log_entry)

    hubspot_result = record_contact_event(
        "booking_confirmed",
        sender_email=email,
        trace_id=f"booking-{email.replace('@', '-at-').replace('.', '-')}",
        company=name,
        channel="calendar",
        details=log_entry,
        hubspot_status="IN_PROGRESS",
        lifecycle_stage="opportunity",
    )
    notification_result = notify_delivery_lead(name, email, booked_time)

    return jsonify(
        {
            "status": "ok",
            "logged": True,
            "hubspot": hubspot_result,
            "delivery_lead": notification_result,
        }
    ), 200


def notify_delivery_lead(name: str, email: str, booked_time: str) -> dict:
    """Notify the Tenacious delivery lead using the existing email sender."""
    recipient = (
        os.getenv("TENACIOUS_DELIVERY_LEAD_EMAIL")
        or os.getenv("TEST_EMAIL_TO")
        or os.getenv("RESEND_TEST_TO_EMAIL")
    )
    if not recipient:
        return {"mode": "skipped", "reason": "delivery lead email not configured"}

    return send_email(
        to=recipient,
        subject=f"New discovery call booked - {name}",
        body=(
            f"A discovery call has been booked.\n\n"
            f"Prospect: {name}\n"
            f"Email: {email}\n"
            f"Time: {booked_time}\n\n"
            f"Check HubSpot for full details."
        ),
        trace_id=f"booking-{email.replace('@', '-at-').replace('.', '-')}",
        company=name,
        variant_tag="internal-booking-alert",
    )


if __name__ == "__main__":
    print("Webhook handler running on http://127.0.0.1:5001/webhooks/booking-confirmed")
    app.run(port=5001, debug=True)
