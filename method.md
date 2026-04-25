# Method

This document describes the chosen control mechanism for the target failure mode in [target_failure_mode.md](/c:/Users/user/desktop/mll/week10/conversion-engine/target_failure_mode.md).

## Target failure and root cause

Target failure:

- cold or insufficiently qualified contacts receiving SMS too early

Root cause:

- multichannel state was not centralized strongly enough
- SMS eligibility was too easy to infer from weak signals

## Chosen mechanism

The chosen mechanism is a centralized state gate backed by JSONL state events plus HubSpot sync.

### Core rule

An outbound SMS is allowed only if all of the following are true:

1. the phone maps to an email
2. the mapped email has a recent `email_reply_qualified` event
3. the number is not opted out with `STOP` or `UNSUB`
4. the message length is `<= 160` characters
5. the send path passes through `state_manager.record_contact_event(...)`

## Exact thresholds and hyperparameters

- qualified-reply recency window: `30 days`
- SMS hard length limit: `160 characters`
- stop commands: exact case-insensitive `STOP`, `UNSUB`, `HELP`
- AI maturity score bands:
  - `<0.75 -> 0`
  - `0.75 - <1.75 -> 1`
  - `1.75 - <2.5 -> 2`
  - `>=2.5 -> 3`
- AI confidence:
  - `>=3 found signals -> high`
  - `1-2 -> medium`
  - `0 -> low`
- qualification handoff triggers:
  - hostile intent
  - dismissive intent
  - pricing beyond public tier
  - unconfirmed staffing capacity

## Why this mechanism

It directly addresses the root cause by making channel escalation depend on explicit state instead of weak inference. It also creates a single path for:

- contact status changes
- timeline notes
- automation stop flags
- cross-channel traceability

## Ablations

### Ablation A: any inbound email reply unlocks SMS

Expected effect:

- higher SMS volume
- more false-positive escalations
- weaker consent posture

Why it is worse:

- neutral replies would still unlock SMS
- pricing and dismissal replies could leak into the wrong channel

### Ablation B: phone mapping plus no opt-out unlocks SMS

Expected effect:

- simpler implementation
- meaningfully more cold-contact leakage

Why it is worse:

- contact existence is not proof of warm-lead status
- loses the benefit of reply qualification

### Ablation C: fully manual SMS approval

Expected effect:

- fewer compliance errors
- slower response and less automation value

Why it is worse:

- adds latency and review overhead
- undermines the point of an automated conversion engine

### Chosen baseline

Only a recent qualified email reply unlocks SMS, with centralized state logging.

## Statistical test plan

Primary metric:

- probe pass rate on the SMS-consent and CRM-state categories

Secondary metrics:

- false-positive SMS eligibility rate
- missing-state-write rate
- handoff-stop-automation consistency rate

Test type:

- paired comparison on the same probe set
- McNemar-style significance test for binary pass/fail outcomes at the probe level

Comparisons:

1. chosen mechanism vs Ablation A
2. chosen mechanism vs Ablation B
3. chosen mechanism vs Ablation C

Sample size assumption:

- at least `100` probe executions per comparison arm
- balanced across the ten probe categories, with heavier weight on `sms_consent`, `crm_state`, and `observability`

Decision threshold:

- `p < 0.05`

Success condition:

- chosen mechanism improves SMS-consent pass rate without materially worsening latency or operator visibility

## Re-implementation checklist

To recreate this mechanism in another codebase:

1. add a centralized state event writer
2. make qualification emit an explicit `email_reply_qualified` event
3. make SMS sender read eligibility from that state
4. centralize STOP/UNSUB enforcement
5. attach visible structured error output for all external-service failures
6. test the gate with both positive and negative cases
