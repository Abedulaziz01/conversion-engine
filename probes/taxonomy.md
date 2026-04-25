# Probe Taxonomy

This taxonomy groups the structured probe library into ten operational categories and records the current average trigger rate per category.

## Category Summary

| Category | Why it exists | Probe count | Average trigger rate |
|---|---|---:|---:|
| `grounding` | prevent invented claims from leaking into outreach | 3 | 0.18 |
| `enrichment` | validate blocked, sparse, or missing source behavior | 3 | 0.19 |
| `segmentation` | protect ICP routing quality | 3 | 0.14 |
| `email_personalization` | keep copy grounded and readable | 3 | 0.16 |
| `reply_intent` | protect follow-up safety and tone | 3 | 0.15 |
| `qualification_capacity` | prevent staffing over-promises | 3 | 0.14 |
| `sms_consent` | enforce warm-lead and opt-out rules | 3 | 0.15 |
| `crm_state` | preserve CRM visibility and stop flags | 3 | 0.17 |
| `booking_handoff` | keep discovery-call transitions intact | 3 | 0.13 |
| `observability` | preserve traceability and structured failure output | 3 | 0.19 |

## How to use it

- High-trigger categories deserve the first regression tests.
- Low-trigger but high-severity categories still matter when they involve consent, handoff, or CRM state.
- Trigger rate is not business cost; combine it with the cost framing in [probe_library.json](/c:/Users/user/desktop/mll/week10/conversion-engine/probes/probe_library.json).

## Highest-risk clusters

The current library suggests the following priority order:

1. `grounding`
2. `enrichment`
3. `observability`
4. `crm_state`
5. `sms_consent`

These are the areas most likely to create silent quality loss or compliance risk before a human notices.
