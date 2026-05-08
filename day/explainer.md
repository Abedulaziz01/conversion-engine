# Explainer: Backpressure, Rate Limits, and Graceful Degradation for OpenRouter in a Conversion Engine

Meseret's question is about a classic production boundary: what should happen when the business expects every prospect reply to receive a response, but the LLM provider cannot safely serve all requests at once. I will answer this explainer as if the Week 10 artifact is exactly the one described in the question: `agent/agent_core/llm_client.py` makes a synchronous `POST` to OpenRouter's `/chat/completions` endpoint on the hot path of reply handling, and `conversation_manager.py` has no retry, queue, or breaker logic.

The short answer is:

**The backpressure mechanism you need is not "retry around `requests.post()`." It is a bounded work queue in front of the LLM, a small concurrency limit on outbound OpenRouter calls, a retry policy that distinguishes `429` from `5xx`, and a circuit breaker that stops your system from amplifying an upstream incident.**

If you do not build those pieces, then under bursty load your system does not degrade gracefully. It converts temporary provider pressure into silent business loss.

## The load-bearing mechanism

The most important design principle is this:

**Never let inbound traffic directly determine outbound concurrency to an LLM provider.**

If 40 prospect replies arrive in five minutes, and each webhook thread immediately calls OpenRouter, then your effective concurrency is 40. That means your system has outsourced admission control to the provider. In other words, you are asking OpenRouter to be your queue, your rate limiter, and your overload protection.

That is the wrong boundary.

The correct boundary is:

1. receive the inbound prospect reply
2. durably persist it
3. enqueue an LLM job
4. let only `N` workers call OpenRouter concurrently
5. if OpenRouter pushes back, reschedule the job instead of dropping it

That is what backpressure means in this context. Pressure is absorbed inside your system, where you still control the business object, not at the far end of an API call where failure becomes invisible.

## What OpenRouter and HTTP are telling you

OpenRouter's official error docs say:

- `429`: you are being rate limited
- `502`: your chosen model is down or returned an invalid response
- `503`: no available model provider meets your routing requirements

OpenRouter's API overview also says it will try to fall back to other providers or GPUs if it sees `5xx` or rate limiting upstream. That matters because it means a `429`, `502`, or `503` reaching your client is already a failure that OpenRouter could not hide internally. At that point, your application must decide whether to retry, defer, or escalate.

Sources:

- OpenRouter API Overview: https://openrouter.ai/docs/api/reference/overview
- OpenRouter Errors and Debugging: https://openrouter.ai/docs/api/reference/errors-and-debugging

HTTP semantics sharpen the distinction:

- `429 Too Many Requests` means the server is rejecting the request because the client sent too many requests in a given window. MDN says a `Retry-After` header may be included to tell the client how long to wait.
- `503 Service Unavailable` means the server is temporarily unable to handle the request, commonly because of overload or maintenance. MDN explicitly describes this as a server-side backpressure mechanism and says `Retry-After` should be used when possible.
- `Retry-After` may be either a delay in seconds or an HTTP date. MDN says clients should honor it for both `429` and `503`.

Sources:

- MDN 429: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429
- MDN 503: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503
- MDN Retry-After: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After

## The concrete difference between `429` and `5xx`

This is the heart of the question.

The difference is not:

- "`429` means retry"
- "`5xx` means fail fast"

That framing is too shallow for production work.

The real difference is:

### `429` is a client-pressure signal

`429` means your request rate is the problem, at least from the server's point of view. The provider is telling you:

- slow down
- wait before retrying
- do not keep sending requests at the same pace

So the correct response to `429` is:

- honor `Retry-After` if present
- otherwise use exponential backoff with jitter
- reduce local concurrency if 429s continue
- keep the business event alive in your queue

Operationally, a `429` usually means the request was **not processed successfully**, but it also does **not** mean the prospect reply is permanently lost unless your own system chooses to lose it. The right abstraction is "deferred," not "dropped."

### `5xx` is an upstream-health signal

`500`, `502`, `503`, and `504` mean the upstream path is unhealthy, unavailable, or timing out. The provider may be overloaded, the model may be down, routing may have failed, or the server may simply not be ready.

So the correct response to `5xx` is:

- retry only a little
- add jitter so clients do not synchronize retries
- count the failure toward a circuit breaker
- consider model/provider fallback if that is part of your business design
- stop sending fresh traffic if the incident persists

This is why "fail fast on all 5xx" is also wrong. A single `503` during a transient incident is often worth retrying. But "retry aggressively forever" is even worse, because it turns an upstream outage into a retry storm.

So the correct production rule is:

- **`429`: retry more patiently and lower pressure**
- **`5xx`: retry briefly, then open the breaker and degrade**

## What graceful degradation means in this system

For a conversion engine, graceful degradation means:

**a prospect reply is never silently lost because the LLM call failed once**

That means the reply path should become stateful:

```text
received -> queued -> processing -> completed
                     \-> retry_scheduled
                     \-> deferred_upstream_failure
                     \-> needs_human_review
```

If OpenRouter returns `429`, the job should go back to `retry_scheduled` with a next-attempt timestamp. If OpenRouter returns repeated `503`s and the circuit is open, the job should move to `deferred_upstream_failure` or `needs_human_review`. In both cases the prospect reply still exists as a tracked work item.

That is the difference between a demo and a production system. A demo treats the API response as the business event. A production system treats the API response as one attempt to advance a business event.

## The production pattern you want

The design should look like this:

```text
Inbound reply
    ->
Persist reply + create job
    ->
Queue
    ->
Bounded worker pool
    ->
OpenRouter call wrapper
    ->
Retry classifier + breaker
    ->
Completed response or deferred/manual-review state
```

Each part solves a different problem:

- **Persistence** protects the business event.
- **Queue** absorbs bursts.
- **Bounded concurrency** prevents self-inflicted overload.
- **Retry classifier** distinguishes transient from permanent failures.
- **Circuit breaker** stops outage amplification.
- **Deferred/manual-review state** preserves business continuity when automation cannot proceed safely.

## A concrete retry policy

A professional first-pass policy for `llm_client.py` would classify failures like this:

### Retryable with backoff

- `429 Too Many Requests`
- `408 Request Timeout`
- `500 Internal Server Error`
- `502 Bad Gateway`
- `503 Service Unavailable`
- `504 Gateway Timeout`
- network timeouts
- connection resets
- transient DNS / transport failures

### Not retryable without a code or config change

- `400 Bad Request`
- `401 Unauthorized`
- `402 Payment Required` or insufficient credits
- `403 Forbidden` / moderation rejection
- malformed payloads from your own code

Then apply different retry behavior:

### Policy for `429`

- first choice: use `Retry-After`
- if absent: exponential backoff with full jitter
- allow a somewhat larger retry budget because the provider is explicitly telling you the request may succeed later
- reduce worker concurrency if 429s become frequent

Example:

```text
max attempts: 5
base delay: 1s
cap: 60s
respect Retry-After: yes
counts toward breaker: yes, but lower severity than 5xx
```

### Policy for `5xx`

- retry a few times only
- use shorter capped backoff with jitter
- count failures aggressively toward the breaker
- if breaker opens, stop issuing new OpenRouter calls for a cool-down interval

Example:

```text
max attempts: 2 or 3
base delay: 500ms to 1s
cap: 10-15s
respect Retry-After on 503: yes, if present
counts toward breaker: yes, high severity
```

This is the subtle but important answer to the user's wording. `5xx` should not usually "fail fast" on the first error, but it **should fail fast at the system level** after a small retry budget is exhausted. That is what the circuit breaker is for.

## Why exponential backoff alone is insufficient

Suppose all 40 requests fail with `429`, and every worker retries after exactly 2 seconds, then 4, then 8. If those retries are synchronized, you have created another traffic spike at each retry boundary.

That is why you need **jitter**.

Instead of:

```text
wait = 2^attempt
```

use something like full jitter:

```text
wait = random(0, min(cap, base * 2^attempt))
```

Jitter spreads retries across time so your clients do not all collide with the same limiter again.

But even perfect backoff is not enough if your concurrency is unbounded. If the queue can release 40 fresh requests while 20 retries are also pending, you still create overload. That is why **concurrency control is the first backpressure mechanism** and retries are only the second.

## How to choose the concurrency limit

Do not start with provider maximums. Start with business safety.

For a conversion engine, a conservative configuration might be:

- queue all inbound replies
- allow only `3-5` in-flight OpenRouter completions
- monitor queue age and retry volume
- raise concurrency only after measuring stable provider behavior

This is the right instinct because the business cost of a short queue is much lower than the business cost of silent drops and cascading failures.

## Circuit breaker behavior

A circuit breaker exists to answer one question:

**When should the application stop treating the provider as healthy?**

One reasonable policy:

- open after 5 transient upstream failures in 60 seconds
- while open, do not send new LLM traffic
- keep accepting and queueing replies
- mark newly blocked jobs as `deferred_upstream_failure`
- probe again after 30 seconds

That gives the provider time to recover and protects your own worker pool.

Without a breaker, every new prospect reply during an outage becomes another doomed API call. With a breaker, every new reply becomes a durable job waiting for the dependency to recover.

## What you must log

Your current concern is silent failure, so observability is part of the answer, not an afterthought.

At minimum, `llm_client.py` and `conversation_manager.py` should emit:

- request ID / reply ID
- attempt number
- HTTP status code
- whether the failure was classified retryable
- chosen backoff delay
- breaker state
- queue length
- age of oldest queued reply
- terminal outcome: completed, deferred, manual review, permanently failed

If you do not log these, you cannot tell the difference between:

- a normal morning burst
- a rate-limit collision
- an upstream outage
- a code bug producing malformed requests

And if you cannot distinguish those, you cannot defend the system as production-ready.

## The answer to the original question

When `llm_client.py` makes concurrent OpenRouter calls under bursty load, the backpressure mechanism you need is:

- a **durable queue** for inbound replies
- a **bounded concurrency limit** for outbound LLM calls
- a **status-aware retry wrapper**
- a **circuit breaker**
- a **deferred/manual-review path** instead of silent loss

The concrete difference between `429` and `5xx` is:

- **`429`** means the provider is telling your client to slow down. Treat it as a temporary, retryable rate-limit rejection. Honor `Retry-After`, use exponential backoff with jitter, and lower concurrency if it persists.
- **`5xx`** means the upstream path is unhealthy or unavailable. Retry only briefly, count it toward opening the circuit breaker, and stop hammering the provider if the incident continues.

So the business-safe rule is:

**Do not drop the reply on either one.**  
`429` should become **defer and retry more patiently**.  
`5xx` should become **retry briefly, then degrade visibly**.

That is what graceful degradation means here. The prospect reply remains a tracked unit of work even when the model call fails. The system may get slower, defer automation, or escalate to manual review, but it does not pretend nothing happened.

## Pointers

- OpenRouter API Overview: https://openrouter.ai/docs/api/reference/overview
- OpenRouter Errors and Debugging: https://openrouter.ai/docs/api/reference/errors-and-debugging
- OpenRouter Limits: https://openrouter.ai/docs/api/reference/limits
- MDN 429 Too Many Requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429
- MDN 503 Service Unavailable: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503
- MDN Retry-After: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
