# Conversion Engine

Sales conversion system for Tenacious that turns public-company signals into outreach, qualification, guarded SMS escalation, booking, and CRM-ready logs.

## Architecture

```text
                           +----------------------+
                           |   Public Data        |
                           | Crunchbase / jobs /  |
                           | layoffs / leadership |
                           +----------+-----------+
                                      |
                                      v
+------------------+        +----------------------+        +----------------------+
| data/ + docs/    |------->| enrichment/          |------->| hiring_signal_brief  |
| seed artifacts   |        | build_brief.py       |        | competitor_gap_brief |
+------------------+        | ai_maturity_scorer   |        +----------+-----------+
                            | competitor_gap       |                   |
                            +----------+-----------+                   v
                                       |                    +----------------------+
                                       |                    | agent/               |
                                       +------------------->| icp_classifier       |
                                                            | email_composer       |
                                                            | email_sender         |
                                                            | reply_handler        |
                                                            | qualifier            |
                                                            | sms_sender           |
                                                            | sms_receiver         |
                                                            | human_handoff        |
                                                            | state_manager        |
                                                            +----+------------+----+
                                                                 |            |
                                                                 v            v
                                                       +----------------+  +------------------+
                                                       | crm/           |  | calendar/        |
                                                       | hubspot_writer |  | booking_*        |
                                                       +--------+-------+  +---------+--------+
                                                                |                    |
                                                                v                    v
                                                         +-------------+      +--------------+
                                                         | HubSpot CRM |      | Cal.com      |
                                                         +-------------+      +--------------+

All meaningful events also append to JSONL logs in agent/, calendar/, and eval/.
```

## Purpose

This repo demonstrates an auditable outbound engine that:

- enriches a company from public signals
- scores AI maturity and competitor gaps
- classifies the lead into Tenacious ICP segments
- drafts and sends email outreach
- qualifies replies and escalates to SMS only after a qualifying email reply
- handles handoff, booking, and HubSpot timeline updates

## Top-Level Folders

| Folder           | Purpose                                                         |
| ---------------- | --------------------------------------------------------------- |
| `agent/`         | messaging, qualification, SMS gating, handoff, state logging    |
| `calendar/`      | Cal.com link generation, booking webhook handling, booking logs |
| `crm/`           | HubSpot contact and timeline write helpers                      |
| `data/`          | local challenge datasets and snapshots                          |
| `docs/`          | seed material, schemas, setup notes, failure-mode docs          |
| `enrichment/`    | master brief assembler and signal extractors                    |
| `eval/`          | evaluation logs, score summaries, and run artifacts             |
| `observability/` | reserved for future dashboards and monitoring assets            |
| `probes/`        | structured adversarial probe library and taxonomy               |
| `tests/`         | unit tests for qualification, gating, and enrichment edge cases |

## Tested Prerequisites

- Windows 10/11 or equivalent shell environment
- `Python 3.13.12`
- `pip 25.x` or compatible
- `Docker 28.3.0` for local Cal.com
- `Git` with repository write access

Python dependencies are pinned in [requirements.txt](/c:/Users/user/desktop/mll/week10/conversion-engine/requirements.txt).

## Setup

### 1. Create the virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Install Playwright browsers

```powershell
python -m playwright install chromium
```

### 3. Create `.env`

```powershell
Copy-Item .env.example .env
```

Fill in the values you actually plan to use.

## Environment Variables

| Variable                                                                                                       | Required               | Purpose                                 |
| -------------------------------------------------------------------------------------------------------------- | ---------------------- | --------------------------------------- |
| `LIVE_OUTBOUND`                                                                                                | yes                    | `false` keeps email/SMS sends simulated |
| `RESEND_API_KEY`                                                                                               | email live only        | outbound email API                      |
| `RESEND_FROM_EMAIL`                                                                                            | email live only        | sender address                          |
| `RESEND_TEST_TO_EMAIL`                                                                                         | recommended            | local testing recipient                 |
| `TEST_EMAIL_TO`                                                                                                | recommended            | shared local fallback recipient         |
| `HUBSPOT_ACCESS_TOKEN`                                                                                         | CRM live only          | HubSpot private app token               |
| `AFRICASTALKING_USERNAME`                                                                                      | SMS live only          | Africa's Talking username               |
| `AFRICASTALKING_API_KEY`                                                                                       | SMS live only          | Africa's Talking API key                |
| `AFRICASTALKING_BASE_URL`                                                                                      | SMS live only          | sandbox/live base URL                   |
| `AFRICASTALKING_SHORTCODE`                                                                                     | optional               | sender shortcode                        |
| `AFRICASTALKING_TEST_TO`                                                                                       | recommended            | local SMS test recipient                |
| `TEST_PHONE_TO`                                                                                                | recommended            | shared phone fallback                   |
| `CALCOM_API_KEY`                                                                                               | booking link live only | Cal.com API access                      |
| `CALCOM_BASE_URL`                                                                                              | yes for booking        | booking host                            |
| `CALCOM_BOOKING_USERNAME`                                                                                      | fallback okay          | booking path user                       |
| `CALCOM_EVENT_TYPE_SLUG`                                                                                       | fallback okay          | booking path event slug                 |
| `TENACIOUS_DELIVERY_LEAD_EMAIL`                                                                                | booking/email alerts   | internal notification recipient         |
| `CALCOM_POSTGRES_*` / `CALCOM_DATABASE_*` / `CALCOM_REDIS_URL` / `CALCOM_NEXTAUTH_*` / `CALCOM_ENCRYPTION_KEY` | Docker Cal.com only    | local Cal.com stack                     |

## Run Order

### Core local demo

1. Build or refresh the brief:

```powershell
python enrichment\build_brief.py "Jogg AI"
```

2. Launch the Streamlit demo:

```powershell
python -m streamlit run streamlit_app.py
```

### Email reply local test

1. Start the reply webhook:

```powershell
python agent\reply_handler.py 8000
```

2. In a second terminal, POST a reply:

```powershell
$body = @{
  sender_email = "you@example.com"
  body_text = "Interesting, yes we're looking to scale our Python team"
  timestamp = "2026-04-25T10:00:00Z"
  original_message_id = "simulated-jogg-ai"
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://127.0.0.1:8000/webhooks/email-reply" -Method POST -ContentType "application/json" -Body $body -UseBasicParsing
```

### SMS local test

Warm-lead SMS now requires a prior `email_reply_qualified` state event. The easiest path is:

1. process a positive email reply through `reply_handler.py`
2. ensure the phone maps to the replying email in `agent/contact_phone_map.json`
3. send SMS:

```powershell
python agent\sms_sender.py --phone "+251711704273" --message "Can we hold 20 minutes tomorrow?"
```

### Booking local test

1. Start the webhook:

```powershell
python calendar\booking_webhook_handler.py
```

2. Optional local Cal.com:

```powershell
docker compose up -d
```

3. Generate a link:

```powershell
python calendar\booking_link_generator.py "Jogg AI" "Segment 4"
```

## Key Safety Rules in This Repo

- SMS is blocked unless the contact has a recent qualified email reply.
- `STOP` and `UNSUB` immediately block future SMS.
- pricing beyond public tiers routes to human handoff.
- capacity promises call the bench checker first.
- blocked or failed scraping degrades confidence instead of inventing data.

## Logs and State

Important logs:

- `agent/email_log.jsonl`
- `agent/sms_log.jsonl`
- `agent/sms_consent_log.jsonl`
- `agent/state_log.jsonl`
- `agent/handoff_log.jsonl`
- `calendar/booking_log.jsonl`

`agent/state_manager.py` is the central place for:

- state events
- HubSpot contact status writes
- HubSpot timeline notes
- automation-stop flags for handoff or opt-out paths

## Tests

Run the targeted test suite:

```powershell
python -m unittest `
  tests.test_qualification_logic `
  tests.test_enrichment_edge_cases `
  tests.test_sms_warm_gate
```

Expected result:

```text
...
OK
```

## Failure Behavior

See::

- [docs/enrichment_failure_modes.md](/c:/Users/user/desktop/mll/week10/conversion-engine/docs/enrichment_failure_modes.md)
- [docs/ai_maturity_scoring.md](/c:/Users/user/desktop/mll/week10/conversion-engine/docs/ai_maturity_scoring.md)
- [docs/competitor_gap_brief.md](/c:/Users/user/desktop/mll/week10/conversion-engine/docs/competitor_gap_brief.md)

## Limitations

- Playwright scraping can fail in restricted Windows event-loop environments; the brief now falls back safely instead of crashing.
- Resend outbound email is supported, but free-tier inbound reply webhook parity depends on provider capabilities.
- Real Cal.com end-to-end booking requires a working Cal.com instance plus a public webhook endpoint.
- HubSpot writes simulate cleanly when no token is configured, but that is not a substitute for production validation.
- A production LLM reply path still needs a durable queue, bounded concurrency, retry-with-jitter, and circuit-breaker handling so bursty inbound traffic does not silently drop replies when an upstream model provider rate-limits or degrades.
- The local data sample is intentionally incomplete, so some companies will fall back to generic outreach.

## Next Steps

- move state and logging from JSONL files into a proper datastore
- add stronger end-to-end tests around HubSpot and Cal.com integrations
- harden the future LLM reply path with provider-aware backpressure: queue inbound replies, cap in-flight completions, honor `Retry-After` on `429`, and degrade to deferred/manual review instead of dropping work on repeated `5xx` failures
- add dashboards in `observability/` for funnel stage counts and failure alerts
- evaluate probe-library failures continuously against held-out traces
