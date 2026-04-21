from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
DEFAULT_AT_BASE_URL = "https://api.sandbox.africastalking.com"


def console_symbol(preferred: str, fallback: str) -> str:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        preferred.encode(encoding)
    except UnicodeEncodeError:
        return fallback

    return preferred


SUCCESS_SYMBOL = console_symbol("✅", "[OK]")
FAIL_SYMBOL = console_symbol("❌", "[FAIL]")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def is_missing(value: str | None) -> bool:
    if value is None:
        return True

    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return True

    return cleaned.startswith("your_")


def get_env(*names: str, required: bool = True) -> str | None:
    for name in names:
        value = os.getenv(name)
        if not is_missing(value):
            return value

    if required:
        joined = ", ".join(names)
        raise RuntimeError(f"Set {joined} in .env before running this test.")

    return None


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    form_body: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    body: bytes | None = None
    final_headers = dict(headers or {})

    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        final_headers.setdefault("Content-Type", "application/json")
    elif form_body is not None:
        body = urllib.parse.urlencode(form_body).encode("utf-8")
        final_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = urllib.request.Request(
        url=url,
        data=body,
        headers=final_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return response.getcode(), json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {payload}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def request_status(url: str, timeout: int = 30) -> int:
    request = urllib.request.Request(url=url, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def print_success(service: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    print(f"{SUCCESS_SYMBOL} {service} connected{suffix}")


def print_failure(service: str, error: Exception) -> None:
    print(f"{FAIL_SYMBOL} {service} failed: {error}")


def test_resend() -> None:
    api_key = get_env("RESEND_API_KEY")
    to_email = get_env("TEST_EMAIL_TO", "RESEND_TEST_TO_EMAIL")
    from_email = get_env(
        "RESEND_TEST_FROM_EMAIL",
        "TEST_EMAIL_FROM",
        required=False,
    ) or "Connection Test <onboarding@resend.dev>"

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "conversion-engine-connection-test/1.0",
        },
        json={
            "from": from_email,
            "to": [to_email],
            "subject": "conversion-engine connection test",
            "text": "This is a test",
        },
        timeout=30,
    )

    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")

    response = response.json()

    email_id = response.get("id")
    if not email_id:
        raise RuntimeError(f"Unexpected response: {response}")

    print_success("RESEND", f"email id {email_id}")


def test_africas_talking() -> None:
    username = get_env("AFRICASTALKING_USERNAME")
    api_key = get_env("AFRICASTALKING_API_KEY")
    to_phone = get_env("TEST_PHONE_TO", "AFRICASTALKING_TEST_TO")
    shortcode = get_env("AFRICASTALKING_SHORTCODE", required=False)
    base_url = (
        get_env("AFRICASTALKING_BASE_URL", required=False) or DEFAULT_AT_BASE_URL
    ).rstrip("/")

    form_body = {
        "username": username,
        "to": to_phone,
        "message": "conversion-engine SMS test",
    }
    if shortcode:
        form_body["from"] = shortcode

    _, response = request_json(
        "POST",
        f"{base_url}/version1/messaging",
        headers={
            "apiKey": api_key,
            "Accept": "application/json",
        },
        form_body=form_body,
    )

    sms_data = response.get("SMSMessageData", {})
    recipients = sms_data.get("Recipients", [])
    if not recipients:
        raise RuntimeError(f"Unexpected response: {response}")

    first = recipients[0]
    status = str(first.get("status", ""))
    status_code = str(first.get("statusCode", ""))
    if "success" not in status.lower() and status_code != "101":
        raise RuntimeError(f"Unexpected recipient response: {first}")

    environment_label = "sandbox" if "sandbox" in base_url else "live"
    print_success(
        "AFRICAS_TALKING",
        f"{environment_label} message id {first.get('messageId', 'n/a')}",
    )


def test_hubspot() -> None:
    access_token = get_env("HUBSPOT_ACCESS_TOKEN")
    timestamp = int(time.time())
    contact_email = (
        get_env("HUBSPOT_TEST_EMAIL", required=False)
        or f"connection-test-{timestamp}@example.com"
    )

    _, response = request_json(
        "POST",
        "https://api.hubapi.com/crm/v3/objects/contacts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        json_body={
            "properties": {
                "firstname": "Test",
                "lastname": "Contact",
                "email": contact_email,
            }
        },
    )

    contact_id = response.get("id")
    if not contact_id:
        raise RuntimeError(f"Unexpected response: {response}")

    print_success("HUBSPOT", f"contact id {contact_id}")


def test_langfuse() -> None:
    get_env("LANGFUSE_PUBLIC_KEY")
    get_env("LANGFUSE_SECRET_KEY")
    get_env("LANGFUSE_BASE_URL", "LANGFUSE_HOST")

    try:
        from langfuse import get_client
    except ImportError as exc:
        raise RuntimeError(
            "langfuse package is not installed. Run `pip install -r requirements.txt` first."
        ) from exc

    langfuse = get_client()

    with langfuse.start_as_current_observation(
        as_type="span",
        name="connection-test",
        input={"source": "tests/test_connections.py"},
    ) as span:
        trace_id = span.trace_id

    langfuse.flush()
    trace_url = langfuse.get_trace_url(trace_id=trace_id)

    print_success("LANGFUSE", trace_url)


def test_calcom() -> None:
    base_url = get_env("CALCOM_BASE_URL", required=False) or "http://localhost:3000"
    status_code = request_status(base_url)

    if status_code != 200:
        raise RuntimeError(f"Expected HTTP 200 from {base_url}, got {status_code}")

    print_success("CALCOM", base_url)


def main() -> int:
    load_env_file(ENV_PATH)

    tests = [
        ("RESEND", test_resend),
        ("AFRICAS_TALKING", test_africas_talking),
        ("HUBSPOT", test_hubspot),
        ("LANGFUSE", test_langfuse),
        ("CALCOM", test_calcom),
    ]

    failed = False
    for service_name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:  # pragma: no cover - explicit test runner output
            failed = True
            print_failure(service_name, exc)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
