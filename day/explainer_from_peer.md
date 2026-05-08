# When Bootstrap Is Enough — and When You Need Paired Bootstrap for Agent Benchmarks

**Explainer:** Meseret Bolled
**Asker:** Abdulaziz
**Topic:** Evaluation and Statistics — Bootstrap CIs for agent benchmarks
**Date:** May 8, 2026

---

## The Gap This Closes

Your `eval/baseline.md` reports point estimates: a success rate and p50/p95 latency from a single run. When you compare two versions of the conversion agent, you write something like "version B improved success rate from 60% to 73%." That sentence is not statistically defensible as written — it does not distinguish genuine improvement from lucky task sampling. This explainer gives you the exact rule for when a simple bootstrap CI is enough and when you need a paired bootstrap, and shows how to compute both from your existing `eval/score_log.json`.

---

## The Load-Bearing Mechanism

**Bootstrap resampling** answers a single question: _if you ran this evaluation on a different random draw of tasks, how much would your metric move?_ You draw N samples with replacement from your task results, compute the metric on each resample, and take the 2.5th and 97.5th percentiles as your 95% CI.

That works for characterising a single version in isolation. It breaks for comparisons.

Here is why. Suppose you have 30 tasks. Some are hard (cold CEO outreach — 20% success for any agent). Some are easy (warm inbound reply — 90% success for any agent). If you bootstrap version A and version B independently, each resample can accidentally pick more hard tasks for one version and more easy tasks for the other. That task-sampling variance inflates your apparent difference and makes real improvements look larger or smaller than they are.

**Paired bootstrap** fixes this by always keeping versions together. For each resample you draw the _same_ task indices for both A and B, compute the _difference_ in metric for that resample, and build a CI around the difference. Now task difficulty cancels out — you are measuring whether B beats A on the _same tasks_, not on independently sampled tasks. If the 95% CI for the difference excludes zero, the improvement is real. If it includes zero, your data does not support the claim.

**The rule:**

| Situation                                                           | Use                                             |
| ------------------------------------------------------------------- | ----------------------------------------------- |
| Reporting a metric for one version (e.g. "our p95 latency is X ms") | Simple bootstrap                                |
| Comparing two versions on the same task set                         | Paired bootstrap of the difference              |
| A and B were run on different task sets                             | Paired bootstrap is invalid — redesign the eval |

---

## Show It: Both Methods on Your score_log Format

```python
import json
import numpy as np

# Load your existing score_log.json
# Expected format: list of dicts with keys: task_id, version ("A"|"B"), success (0|1), latency_ms
with open("eval/score_log.json") as f:
    logs = json.load(f)

# Build per-task arrays aligned on shared task_ids
tasks_a = {r["task_id"]: r for r in logs if r["version"] == "A"}
tasks_b = {r["task_id"]: r for r in logs if r["version"] == "B"}
shared  = sorted(set(tasks_a) & set(tasks_b))

success_a = np.array([tasks_a[t]["success"]    for t in shared])
success_b = np.array([tasks_b[t]["success"]    for t in shared])
latency_a = np.array([tasks_a[t]["latency_ms"] for t in shared])
latency_b = np.array([tasks_b[t]["latency_ms"] for t in shared])

N         = len(shared)
RESAMPLES = 10_000
rng       = np.random.default_rng(42)

# ── Simple bootstrap: characterise ONE version ────────────────────────────────
p95_dist = [
    np.percentile(latency_a[rng.integers(0, N, N)], 95)
    for _ in range(RESAMPLES)
]
lo, hi = np.percentile(p95_dist, [2.5, 97.5])
print(f"Version A  p95 latency: {np.percentile(latency_a, 95):.0f} ms "
      f"[95% CI: {lo:.0f}–{hi:.0f} ms]")

# ── Paired bootstrap: compare A vs B ─────────────────────────────────────────
diff_success, diff_p95 = [], []

for _ in range(RESAMPLES):
    idx = rng.integers(0, N, N)          # same task indices for both versions
    diff_success.append(success_b[idx].mean() - success_a[idx].mean())
    diff_p95.append(
        np.percentile(latency_b[idx], 95) - np.percentile(latency_a[idx], 95)
    )

s_lo, s_hi = np.percentile(diff_success, [2.5, 97.5])
l_lo, l_hi = np.percentile(diff_p95,     [2.5, 97.5])

obs_s = success_b.mean() - success_a.mean()
obs_l = np.percentile(latency_b, 95) - np.percentile(latency_a, 95)

print(f"\nSuccess rate  A={success_a.mean():.1%}  B={success_b.mean():.1%}")
print(f"  Difference: {obs_s:+.1%}  [95% CI: {s_lo:+.1%} to {s_hi:+.1%}]")
print(f"  {'DEFENSIBLE — CI excludes zero ✓' if s_lo > 0 or s_hi < 0 else 'NOT DEFENSIBLE — CI includes zero ✗'}")

print(f"\np95 latency   A={np.percentile(latency_a,95):.0f}ms  B={np.percentile(latency_b,95):.0f}ms")
print(f"  Difference: {obs_l:+.0f} ms  [95% CI: {l_lo:+.0f} to {l_hi:+.0f} ms]")
print(f"  {'DEFENSIBLE — CI excludes zero ✓' if l_lo > 0 or l_hi < 0 else 'NOT DEFENSIBLE — CI includes zero ✗'}")
```

**What the output tells you:**

- CI excludes zero → write "version B improved by +13 pp [95% CI: +4 to +22 pp]" — defensible.
- CI includes zero → write "version B showed a +13 pp point estimate but the 95% CI [−2 to +28 pp] does not exclude zero; the improvement may be noise from task sampling." Do not drop the CI and report only the point estimate.

---

## How This Changes Your Evaluation Narrative

**Before (not defensible):**

> "Version B improved success rate from 60% to 73% and reduced p95 latency from 820 ms to 710 ms."

**After (defensible):**

> "Version B improved success rate by +13 pp over version A [paired bootstrap 95% CI: +4 to +22 pp, N=30 tasks]. p95 latency fell by 110 ms [95% CI: −180 to −40 ms]. Both CIs exclude zero, supporting the claim that the improvement is real rather than a sampling artifact."

If a client engineer asks "how do you know this isn't noise?" — that sentence is your answer.

---

## Adjacent Concepts

**Why 30 tasks is borderline.** Bootstrap CIs narrow as N grows. With 30 tasks, even a real +15 pp improvement may produce a CI that includes zero. If your `score_log.json` has fewer than 50 tasks, report CIs and name the sample size as a limitation. With 100+ tasks, CIs become tight enough that real improvements are reliably detectable.

**p-value vs CI.** The paired bootstrap also gives you a one-sided p-value: `(np.array(diff_success) <= 0).mean()`. A CI is more informative because it shows the magnitude of uncertainty, not just a binary pass/fail. Report the CI in your write-up; add the p-value only if a reviewer asks.

**When pairing is impossible.** If version A and version B were evaluated on different task sets, paired bootstrap is invalid. Both versions must run on the same tasks before you compare. This is a constraint on your `harness.py` design — run both versions in the same harness execution so task IDs are shared.

---

## Sources

1. **Efron, B. & Tibshirani, R. (1993). _An Introduction to the Bootstrap_.** Chapman and Hall. — The foundational text. Chapter 6 defines the bootstrap CI; Chapter 11 covers the two-sample comparison that underpins paired bootstrap. [doi:10.1007/978-1-4899-4541-9](https://doi.org/10.1007/978-1-4899-4541-9)

2. **Berg-Kirkpatrick, T., Burkett, D., & Klein, D. (2012). An Empirical Investigation of Statistical Significance in NLP.** _EMNLP 2012._ — The canonical paper showing that unpaired significance tests overstate certainty in NLP evaluation and that paired bootstrap corrects this. Directly applicable to agent benchmark comparisons. [aclanthology.org/D12-1091](https://aclanthology.org/D12-1091/)

**Tool used:** `numpy.random.default_rng` with manual resampling loop. This avoids `scipy.stats.bootstrap`'s IID assumption, which does not hold for paired data where task difficulty is a confounding variable.
