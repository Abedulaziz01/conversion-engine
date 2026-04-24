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
SMS_CONSENT_LOG_PATH = ROOT / "agent" / "sms_consent_log.jsonl"
SMS_LOG_PATH = ROOT / "agent" / "sms_log.jsonl"


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


def append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def normalize_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_phone(phone_number: str) -> str:
    return "".join(ch for ch in phone_number if ch in "+0123456789")


def send_help_reply(phone_number: str) -> dict[str, Any]:
    message_text = "Tenacious SMS support: reply STOP or UNSUB to opt out. Reply EMAIL for email-only follow-up."
    if normalize_bool(os.getenv("LIVE_OUTBOUND")):
        username = os.getenv("AFRICASTALKING_USERNAME")
        api_key = os.getenv("AFRICASTALKING_API_KEY")
        shortcode = os.getenv("AFRICASTALKING_SHORTCODE")
        base_url = (os.getenv("AFRICASTALKING_BASE_URL") or "https://api.sandbox.africastalking.com").rstrip("/")
        payload = {"username": username, "to": phone_number, "message": message_text}
        if shortcode:
            payload["from"] = shortcode
        response = requests.post(
            f"{base_url}/version1/messaging",
            headers={"apiKey": api_key, "Accept": "application/json"},
            data=payload,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Africa's Talking HELP reply failed with HTTP {response.status_code}: {response.text}")
        delivery_status = "sent"
    else:
        delivery_status = "simulated"

    log_entry = {
        "timestamp": utc_now(),
        "recipient": phone_number,
        "message": message_text,
        "sent_or_simulated": delivery_status,
        "delivery_status": delivery_status,
        "message_id": f"help-{phone_number}",
    }
    append_jsonl(SMS_LOG_PATH, log_entry)
    return log_entry


def handle_consent_command(phone_number: str, command: str) -> dict[str, Any]:
    normalized_phone = normalize_phone(phone_number)
    normalized_command = command.strip().upper()

    if normalized_command in {"STOP", "UNSUB"}:
        entry = {
            "timestamp": utc_now(),
            "phone_number": normalized_phone,
            "command": normalized_command,
            "hubspot_status": "SMS Opted Out",
            "future_sms_refused": True,
        }
        append_jsonl(SMS_CONSENT_LOG_PATH, entry)
        return entry

    if normalized_command == "HELP":
        help_log = send_help_reply(normalized_phone)
        entry = {
            "timestamp": utc_now(),
            "phone_number": normalized_phone,
            "command": normalized_command,
            "hubspot_status": "SMS Help Requested",
            "future_sms_refused": False,
            "help_reply": help_log,
        }
        append_jsonl(SMS_CONSENT_LOG_PATH, entry)
        return entry

    raise ValueError("Command must be STOP, HELP, or UNSUB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Handle SMS consent commands")
    parser.add_argument("--phone", required=True, help="Phone number")
    parser.add_argument("--command", required=True, help="STOP, HELP, or UNSUB")
    args = parser.parse_args(argv)

    load_env_file(ENV_PATH)
    result = handle_consent_command(args.phone, args.command)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
