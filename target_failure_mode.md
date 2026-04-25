# Target Failure Mode

## Chosen failure

`SC-01`: cold SMS is allowed before a qualifying email reply.

## Why this one

This is the cleanest example of a failure that is:

- easy to trigger accidentally in a multichannel workflow
- high severity from a consent and brand perspective
- measurable using only the allowed Tenacious numbers
- directly addressable by centralized state gating

## Root cause

The root cause is channel state being inferred from contact existence instead of explicit conversation state.

Bad version:

- phone exists
- contact replied at some point
- system assumes SMS is safe

Chosen guarded version:

- phone exists
- mapped email has a recent `email_reply_qualified` event
- no `STOP` or `UNSUB`
- message is under 160 characters

## Business cost arithmetic

Allowed inputs:

- signal-grounded reply rate: `7-12%`
- cold-email baseline reply rate: `1-3%`
- SDR target: `~60 thoughtful touches / week`

### Replacement cost if one warm prospect is lost

If one premature SMS causes the loss of a prospect who had already reached qualified-email-reply status, replacing that opportunity requires roughly:

- best case using signal-grounded touches:
  - `1 / 0.12 = 8.33` touches
- conservative case using signal-grounded touches:
  - `1 / 0.07 = 14.29` touches

Expressed as SDR-week share:

- `8.33 / 60 = 0.14` SDR-weeks
- `14.29 / 60 = 0.24` SDR-weeks

If the mistake pushes the team back into cold-outbound behavior, the same replacement cost becomes:

- `1 / 0.03 = 33.33` touches
- `1 / 0.01 = 100` touches

Expressed as SDR-week share:

- `33.33 / 60 = 0.56` SDR-weeks
- `100 / 60 = 1.67` SDR-weeks

## Alternatives considered

### Alternative A: allow SMS after any inbound email reply

Pros:

- simple
- increases channel speed

Cons:

- treats neutral, dismissive, and pricing-sensitive replies as warm
- still risks cold-feeling SMS escalation

### Alternative B: manual approval before every SMS

Pros:

- very safe

Cons:

- too slow
- removes automation value
- adds manual load to a workflow already constrained by SDR throughput

### Chosen approach: centralized qualified-reply gate

Pros:

- fast enough for warm leads
- explicit and auditable
- compatible with STOP/UNSUB blocking
- reusable across email, SMS, and booking state transitions

Cons:

- requires state discipline and tests
- depends on clean phone-to-email mapping

## Implementation link

See:

- [agent/sms_sender.py](/c:/Users/user/desktop/mll/week10/conversion-engine/agent/sms_sender.py)
- [agent/state_manager.py](/c:/Users/user/desktop/mll/week10/conversion-engine/agent/state_manager.py)
- [tests/test_sms_warm_gate.py](/c:/Users/user/desktop/mll/week10/conversion-engine/tests/test_sms_warm_gate.py)
