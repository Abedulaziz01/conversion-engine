# Enrichment Failure Behaviors

This document explains how downstream consumers should interpret incomplete enrichment results.

## Why this matters

The enrichment pipeline is intentionally fail-soft. A missing source should degrade confidence rather than crash the conversion flow or fabricate certainty.

## Common failure modes

### `robots.txt` blocked

Where it appears:
- `job_posts.scraping_blocked = true`
- `job_posts.robots_respected = true`
- `job_posts.reason = "...blocked..."`

How to interpret it:
- This is not a negative hiring signal.
- It means the pipeline respected the site policy and could not collect evidence.
- Downstream systems should avoid using job volume as proof of either growth or contraction.

Recommended consumer behavior:
- lower confidence on hiring-driven segments
- keep other signals active
- avoid hard disqualification based on missing hiring data alone

### Playwright or scraper runtime failure

Where it appears:
- `job_posts.reason = "job_scraper_failed"`
- `job_posts.error = "..."`

How to interpret it:
- This is a tooling failure, not a company signal.
- Typical causes are missing browser dependencies, local event-loop issues, or blocked subprocess execution.

Recommended consumer behavior:
- continue the flow using firmographics, funding, leadership, and AI maturity
- do not infer `0` open roles as factual absence of hiring

### Sparse job market

Where it appears:
- `job_posts.roles_now` may be `0` or `1`
- `job_posts.change_pct = null`

How to interpret it:
- A null `change_pct` usually means there was no usable 60-day baseline.
- This is expected for very small companies or sparse samples.

Recommended consumer behavior:
- treat the hiring signal as low-confidence rather than negative
- prefer contextual messaging over growth claims

### Company missing from Crunchbase sample

Where it appears:
- `firmographics.found = false`
- AI maturity and competitor gap artifacts fall back to low-confidence defaults

How to interpret it:
- The current local sample did not contain the company.
- This is a data-coverage gap, not proof that the company is invalid.

Recommended consumer behavior:
- use generic outreach
- avoid segment-specific claims

## Confidence guidance

When hiring evidence is blocked or sparse, downstream consumers should read the brief this way:

- `high confidence`: multiple independent signals agree
- `medium confidence`: one or two usable signals exist, but at least one important source is missing
- `low confidence`: key evidence is blocked, unavailable, or only weakly positive

## Safe defaults

If a downstream system is unsure how to behave:

1. prefer generic outreach over aggressive personalization
2. avoid making claims that require job-post evidence
3. route pricing, capacity, or hostile conversations to human review
4. preserve the raw error or reason fields in logs for debugging
