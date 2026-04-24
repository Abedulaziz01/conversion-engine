from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.sms_consent_manager import handle_consent_command


SMS_LOG_PATH = ROOT / "agent" / "sms_log.jsonl"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_sms_log(entry: dict[str, Any]) -> None:
    SMS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SMS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def process_incoming_sms(payload: dict[str, Any]) -> dict[str, Any]:
    phone_number = str(payload.get("phone_number") or payload.get("from") or "").strip()
    message_text = str(payload.get("message") or payload.get("text") or "").strip()
    timestamp = str(payload.get("timestamp") or utc_now())
    if not phone_number or not message_text:
        raise ValueError("SMS payload must include phone number and message text")

    command = message_text.upper()
    if command in {"STOP", "HELP", "UNSUB"}:
        result = handle_consent_command(phone_number, command)
        append_sms_log(
            {
                "timestamp": timestamp,
                "recipient": phone_number,
                "message": message_text,
                "sent_or_simulated": "received",
                "delivery_status": "received",
                "message_id": None,
            }
        )
        return {"command_processed": True, "result": result}

    append_sms_log(
        {
            "timestamp": timestamp,
            "recipient": phone_number,
            "message": message_text,
            "sent_or_simulated": "received",
            "delivery_status": "received",
            "message_id": None,
        }
    )
    return {"command_processed": False}


class SmsWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhooks/sms-reply":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw_body)
            result = process_incoming_sms(payload)
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"error": str(exc)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def run_server(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), SmsWebhookHandler)
    print(f"SMS webhook listening on http://127.0.0.1:{port}/webhooks/sms-reply")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    port = 8010
    if argv and len(argv) > 1:
        port = int(argv[1])
    run_server(port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
