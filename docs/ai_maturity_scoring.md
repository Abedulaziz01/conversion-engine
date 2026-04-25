# AI Maturity Scoring

The AI maturity subsystem converts several weighted public signals into a 0-3 score used by enrichment, segmentation, and outreach personalization.

## Weighted signals

| Signal | Weight band | Typical max contribution |
|---|---:|---:|
| AI/ML hiring signal | high | 1.0 |
| ML/AI leadership signal | high | 1.0 |
| GitHub AI activity | medium | 0.25 |
| Executive AI commentary | medium | 0.5 |
| ML stack tooling | low | 0.25 |
| Strategic/fundraising AI language | low | 0.25 |

## Score bands

The implementation first sums weighted contributions, then maps them to a score band:

| Total contribution | Score | Business meaning |
|---|---:|---|
| `< 0.75` | 0 | No credible AI adoption signal. Use non-AI messaging. |
| `0.75 - <1.75` | 1 | Weak or isolated AI evidence. Mention AI carefully, if at all. |
| `1.75 - <2.5` | 2 | Multiple AI signals. AI capacity is likely relevant to the prospect. |
| `>= 2.5` | 3 | Strong AI maturity. AI-oriented outreach and staffing positioning are justified. |

## Confidence

Confidence is derived from the count of signals marked `found`:

- `high`: 3 or more positive signals
- `medium`: 1 or 2 positive signals
- `low`: 0 positive signals

## Silent-company path

If the company is missing from the Crunchbase sample, the scorer returns a fully structured but low-confidence zero score. This avoids null-heavy downstream handling and makes the absence explicit.

## Maintenance note

If future contributors change thresholds, they should preserve the business intent of each band:

- `0` should remain a safe default for generic messaging
- `2` should remain the threshold where AI-oriented outreach becomes justified
- `3` should remain reserved for strong multi-signal evidence, not a single flashy mention
