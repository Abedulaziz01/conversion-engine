from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def load_env_file(path: Path = ENV_PATH) -> None:
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


def _headers() -> dict[str, str] | None:
    token = os.getenv("HUBSPOT_ACCESS_TOKEN")
    if not token:
        return None
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, url: str, *, json_body: dict[str, Any] | None = None) -> requests.Response:
    headers = _headers()
    if headers is None:
        raise RuntimeError("HUBSPOT_ACCESS_TOKEN is not configured")
    response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
    return response


def find_contact_by_email(email: str | None) -> dict[str, Any]:
    load_env_file()
    if not email:
        return {
            "mode": "skipped",
            "reason": "missing_email",
            "contact_id": None,
        }

    headers = _headers()
    if headers is None:
        return {
            "mode": "simulated",
            "reason": "missing_hubspot_token",
            "contact_id": None,
            "email": email,
        }

    try:
        response = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/search",
            headers=headers,
            json={
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email,
                            }
                        ]
                    }
                ],
                "properties": ["email", "lifecyclestage", "hs_lead_status"],
                "limit": 1,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        return {
            "mode": "failed",
            "reason": "search_request_error",
            "response_text": str(exc),
            "contact_id": None,
            "email": email,
        }
    if response.status_code != 200:
        return {
            "mode": "failed",
            "reason": f"search_failed:{response.status_code}",
            "response_text": response.text,
            "contact_id": None,
            "email": email,
        }

    results = response.json().get("results") or []
    if not results:
        return {
            "mode": "simulated",
            "reason": "contact_not_found",
            "contact_id": None,
            "email": email,
        }

    return {
        "mode": "live",
        "contact_id": str(results[0]["id"]),
        "email": email,
    }


def update_contact_status(
    *,
    email: str | None,
    status: str | None = None,
    lifecycle_stage: str | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lookup = find_contact_by_email(email)
    contact_id = lookup.get("contact_id")
    if not contact_id:
        return lookup

    properties: dict[str, Any] = {}
    if status:
        properties["hs_lead_status"] = status
    if lifecycle_stage:
        properties["lifecyclestage"] = lifecycle_stage
    if extra_properties:
        properties.update(extra_properties)

    if not properties:
        return {
            "mode": "skipped",
            "reason": "no_properties_to_update",
            "contact_id": contact_id,
        }

    try:
        response = _request(
            "PATCH",
            f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
            json_body={"properties": properties},
        )
    except requests.RequestException as exc:
        return {
            "mode": "failed",
            "reason": "update_request_error",
            "response_text": str(exc),
            "contact_id": contact_id,
        }
    if response.status_code != 200:
        return {
            "mode": "failed",
            "reason": f"update_failed:{response.status_code}",
            "response_text": response.text,
            "contact_id": contact_id,
        }

    return {
        "mode": "live",
        "contact_id": contact_id,
        "updated_properties": properties,
    }


def write_timeline_event(
    *,
    email: str | None,
    title: str,
    body: str,
) -> dict[str, Any]:
    lookup = find_contact_by_email(email)
    contact_id = lookup.get("contact_id")
    if not contact_id:
        return lookup

    try:
        note_response = _request(
            "POST",
            "https://api.hubapi.com/crm/v3/objects/notes",
            json_body={
                "properties": {
                    "hs_note_body": f"{title}\n\n{body}",
                    "hs_timestamp": str(int(datetime.now(UTC).timestamp() * 1000)),
                }
            },
        )
    except requests.RequestException as exc:
        return {
            "mode": "failed",
            "reason": "note_request_error",
            "response_text": str(exc),
            "contact_id": contact_id,
        }
    if note_response.status_code != 201:
        return {
            "mode": "failed",
            "reason": f"note_create_failed:{note_response.status_code}",
            "response_text": note_response.text,
            "contact_id": contact_id,
        }

    note_id = str(note_response.json()["id"])
    try:
        assoc_response = requests.put(
            f"https://api.hubapi.com/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact",
            headers=_headers(),
            timeout=30,
        )
    except requests.RequestException as exc:
        return {
            "mode": "failed",
            "reason": "note_association_request_error",
            "response_text": str(exc),
            "contact_id": contact_id,
            "note_id": note_id,
        }
    if assoc_response.status_code >= 400:
        return {
            "mode": "failed",
            "reason": f"note_association_failed:{assoc_response.status_code}",
            "response_text": assoc_response.text,
            "contact_id": contact_id,
            "note_id": note_id,
        }

    return {
        "mode": "live",
        "contact_id": contact_id,
        "note_id": note_id,
        "logged_at": utc_now(),
    }
