# Grounding Commit

**Artifact updated:** [README.md](/C:/Users/user/Desktop/mll/week10/conversion-engine/README.md)

I updated the README's `Limitations` and `Next Steps` sections to name the production reliability gap more precisely. Instead of a generic note to "harden retry/backoff behavior for external APIs," the repo now explicitly states that a real LLM reply path needs a durable queue, bounded concurrency, `Retry-After` handling for `429`, jittered retries, circuit breaking, and a deferred/manual-review fallback when repeated `5xx` failures occur. This is a real portfolio improvement because it changes the project from sounding production-ready on the happy path to honestly documenting the failure-path engineering still required for bursty inbound reply handling. The edit reflects what I understand now: backpressure is an application design problem, not just an exception-handling detail inside a single HTTP call.
