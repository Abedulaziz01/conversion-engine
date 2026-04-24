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


ENV_PATH = ROOT / ".env"
EMAIL_LOG_PATH = ROOT / "agent" / "email_log.jsonl"
SMS_LOG_PATH = ROOT / "agent" / "sms_log.jsonl"
SMS_CONSENT_LOG_PATH = ROOT / "agent" / "sms_consent_log.jsonl"
PHONE_MAP_PATH = ROOT / "agent" / "contact_phone_map.json"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_sms_log(entry: dict[str, Any]) -> None:
    SMS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SMS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def normalize_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_phone(phone_number: str) -> str:
    return "".join(ch for ch in phone_number if ch in "+0123456789")


def load_phone_mapping() -> dict[str, str]:
    if not PHONE_MAP_PATH.exists():
        return {}
    try:
        payload = json.loads(PHONE_MAP_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        normalize_phone(phone): str(email)
        for phone, email in payload.items()
        if phone and email
    }


def load_email_log() -> list[dict[str, Any]]:
    if not EMAIL_LOG_PATH.exists():
        return []
    rows = []
    for line in EMAIL_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_sms_consent_log() -> list[dict[str, Any]]:
    if not SMS_CONSENT_LOG_PATH.exists():
        return []
    rows = []
    for line in SMS_CONSENT_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def resolve_email_for_phone(phone_number: str) -> str | None:
    normalized_phone = normalize_phone(phone_number)
    mapping = load_phone_mapping()
    mapped = mapping.get(normalized_phone)
    if mapped:
        return mapped

    test_phone = normalize_phone(os.getenv("AFRICASTALKING_TEST_TO") or os.getenv("TEST_PHONE_TO") or "")
    test_email = os.getenv("TEST_EMAIL_TO") or os.getenv("RESEND_TEST_TO_EMAIL")
    if normalized_phone and normalized_phone == test_phone and test_email:
        return test_email
    if normalized_phone and normalized_phone == test_phone:
        for row in reversed(load_email_log()):
            if row.get("event_type") == "inbound_email_reply" and row.get("sender_email"):
                return str(row.get("sender_email"))
    return None


def has_replied_by_email(phone_number: str) -> bool:
    email = resolve_email_for_phone(phone_number)
    if not email:
        return False
    target = email.lower()
    for row in load_email_log():
        if row.get("event_type") == "inbound_email_reply" and str(row.get("sender_email") or "").lower() == target:
            return True
    return False


def is_opted_out(phone_number: str) -> bool:
    normalized = normalize_phone(phone_number)
    latest_command = None
    for row in load_sms_consent_log():
        if normalize_phone(str(row.get("phone_number") or "")) == normalized:
            latest_command = str(row.get("command") or "").upper()
    return latest_command in {"STOP", "UNSUB"}


def send_sms_via_africastalking(phone_number: str, message_text: str) -> tuple[str, str]:
    username = os.getenv("AFRICASTALKING_USERNAME")
    api_key = os.getenv("AFRICASTALKING_API_KEY")
    shortcode = os.getenv("AFRICASTALKING_SHORTCODE")
    base_url = (os.getenv("AFRICASTALKING_BASE_URL") or "https://api.sandbox.africastalking.com").rstrip("/")
    if not username or not api_key:
        raise RuntimeError("Africa's Talking credentials are not configured")

    payload = {
        "username": username,
        "to": phone_number,
        "message": message_text,
    }
    if shortcode:
        payload["from"] = shortcode

    response = requests.post(
        f"{base_url}/version1/messaging",
        headers={"apiKey": api_key, "Accept": "application/json"},
        data=payload,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Africa's Talking send failed with HTTP {response.status_code}: {response.text}")

    data = response.json()
    recipients = data.get("SMSMessageData", {}).get("Recipients", [])
    if not recipients:
        raise RuntimeError(f"Unexpected Africa's Talking response: {data}")

    recipient = recipients[0]
    return str(recipient.get("messageId") or ""), str(recipient.get("status") or "unknown")


def send_sms(phone_number: str, message_text: str) -> dict[str, Any]:
    normalized_phone = normalize_phone(phone_number)
    sent_or_simulated = "simulated"
    delivery_status = "simulated"
    message_id = None
    refused = None

    if len(message_text) > 160:
        refused = "message too long"
        delivery_status = "refused"
    elif is_opted_out(normalized_phone):
        refused = "opted out"
        delivery_status = "refused"
    elif not has_replied_by_email(normalized_phone):
        refused = "cold contact"
        delivery_status = "refused"
    else:
        live_outbound = normalize_bool(os.getenv("LIVE_OUTBOUND"))
        if live_outbound:
            message_id, delivery_status = send_sms_via_africastalking(normalized_phone, message_text)
            sent_or_simulated = "sent"
        else:
            message_id = f"simulated-sms-{normalized_phone}"
            sent_or_simulated = "simulated"
            delivery_status = "simulated"

    log_entry = {
        "timestamp": utc_now(),
        "recipient": normalized_phone,
        "message": message_text,
        "sent_or_simulated": sent_or_simulated if refused is None else "refused",
        "delivery_status": delivery_status,
        "message_id": message_id,
    }
    if refused is not None:
        log_entry["refused"] = refused

    append_sms_log(log_entry)
    return log_entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send or simulate a warm-lead SMS")
    parser.add_argument("--phone", required=True, help="Recipient phone number")
    parser.add_argument("--message", required=True, help="SMS body under 160 chars")
    args = parser.parse_args(argv)

    load_env_file(ENV_PATH)
    result = send_sms(args.phone, args.message)
    print(json.dumps(result, indent=2))
    return 0 if result.get("sent_or_simulated") != "refused" else 1


if __name__ == "__main__":
    raise SystemExit(main())
