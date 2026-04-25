# Competitor Gap Brief

`competitor_gap_brief.json` is a reviewer-friendly artifact that compares a target company with similar peers and highlights evidence-backed adoption gaps.

## Schema

| Field | Meaning |
|---|---|
| `target_company` | normalized company name used in the brief |
| `sector` | one or two high-level industries from Crunchbase |
| `size_band` | employee-range label derived from available size data |
| `target_ai_maturity` | target company's 0-3 AI maturity score |
| `competitors_scored` | peer companies with their AI maturity and employee count |
| `target_percentile` | relative standing against the peer set |
| `gaps` | up to three evidence-backed capability gaps |
| `reason` | optional fallback explanation when the peer brief is partial |

## Example

See:
- [sample_competitor_gap_brief.json](/c:/Users/user/desktop/mll/week10/conversion-engine/docs/schemas/sample_competitor_gap_brief.json)

Example gap entry:

```json
{
  "gap": "No dedicated ML/AI leadership role",
  "evidence": "Peer A: Detected leadership signal containing 'head of ai'. Peer B: Detected leadership signal containing 'head of data science'.",
  "target_signal": "No named AI/ML leader found in available Crunchbase people data"
}
```

## How to read it

- This is not a market map.
- It is a lightweight outreach aid that shows where a target appears to lag nearby peers.
- Gaps should be used as conversation starters, not as hard factual claims unless the evidence is directly cited.
