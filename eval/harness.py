from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
import datetime
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "eval"
TAU2_SRC = EVAL_DIR / "tau2-bench" / "src"
SCORE_LOG = EVAL_DIR / "score_log.json"
TRACE_LOG = EVAL_DIR / "trace_log.jsonl"


def setup():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if str(TAU2_SRC) not in sys.path:
        sys.path.insert(0, str(TAU2_SRC))
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))


def wilson_ci(successes: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    z = 1.96
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    margin = (z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)
    return round(center - margin, 4), round(center + margin, 4)


def read_score_log() -> list:
    if not SCORE_LOG.exists():
        return []
    content = SCORE_LOG.read_text(encoding="utf-8").strip()
    if not content:
        return []
    return json.loads(content)


def write_score_log(entries: list) -> None:
    SCORE_LOG.write_text(
        json.dumps(entries, indent=2),
        encoding="utf-8"
    )


def append_trace(payload: dict) -> None:
    with TRACE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def extract_turns(simulation: Any) -> list:
    turns = []
    for msg in getattr(simulation, "messages", []):
        turns.append({
            "role": getattr(msg, "role", "unknown"),
            "input": getattr(msg, "content", ""),
            "output": ""
        })
    return turns


def run(tasks: int, trials: int, model: str) -> None:
    os.environ.setdefault("TAU2_LLM_NL_ASSERTIONS", model)

    from tau2.data_model.simulation import TextRunConfig
    from tau2.run import run_domain
    import langfuse_logger

    print(f"\nRunning tau2-bench")
    print(f"Tasks:  {tasks}")
    print(f"Trials: {trials}")
    print(f"Model:  {model}\n")

    config = TextRunConfig(
        domain="retail",
        agent="llm_agent",
        user="user_simulator",
        llm_agent=model,
        llm_user=model,
        num_tasks=tasks,
        num_trials=trials,
        seed=300,
        max_concurrency=1,
        log_level="ERROR",
        verbose_logs=False,
    )

    start_total = time.time()
    results = run_domain(config)
    total_time = time.time() - start_total

    sims = getattr(results, "simulations", [])
    successes = 0
    latencies = []
    trace_ids = []
    total_cost = 0.0

    for sim in sims:
        ri = getattr(sim, "reward_info", None)
        reward = getattr(ri, "reward", 0.0) if ri else 0.0
        passed = reward == 1.0
        if passed:
            successes += 1

        duration = getattr(sim, "duration", total_time / max(len(sims), 1))
        latency_ms = int(float(duration or 0) * 1000)
        latencies.append(latency_ms)

        agent_cost = float(getattr(sim, "agent_cost", 0.0) or 0.0)
        user_cost = float(getattr(sim, "user_cost", 0.0) or 0.0)
        sim_cost = agent_cost + user_cost
        total_cost += sim_cost

        requested_trace_id = uuid.uuid4().hex
        turns = extract_turns(sim)
        task_id = str(getattr(sim, "task_id", "unknown"))

        trace_id, trace_url = langfuse_logger.log_trace(
            trace_id=requested_trace_id,
            task_id=task_id,
            model=model,
            pass_fail=passed,
            cost=sim_cost,
            latency_ms=latency_ms,
            turns=turns
        )
        trace_ids.append(trace_id)

        append_trace({
            "trace_id": trace_id,
            "task_id": task_id,
            "model": model,
            "pass_fail": "pass" if passed else "fail",
            "cost_usd": sim_cost,
            "latency_ms": latency_ms,
            "langfuse_url": trace_url
        })

        print(f"Task {task_id}: {'PASS' if passed else 'FAIL'} | "
              f"latency={latency_ms}ms | "
              f"url={trace_url}")

    n = len(sims)
    pass_at_1 = round(successes / n, 4) if n > 0 else 0.0
    ci_low, ci_high = wilson_ci(successes, n)

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)] \
        if latencies_sorted else 0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] \
        if latencies_sorted else 0

    entry = {
        "run_id": f"run_{len(read_score_log()) + 1:03d}",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "model": model,
        "tasks_run": tasks,
        "trials": trials,
        "pass_at_1": pass_at_1,
        "ci_95_low": ci_low,
        "ci_95_high": ci_high,
        "cost_usd": round(total_cost, 4),
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "trace_ids": trace_ids
    }

    entries = read_score_log()
    entries.append(entry)
    write_score_log(entries)

    print(f"\n{'='*50}")
    print(json.dumps(entry, indent=2))
    print(f"\nSaved score to:  {SCORE_LOG}")
    print(f"Saved traces to: {TRACE_LOG}")


def main():
    parser = argparse.ArgumentParser(description="tau2-bench harness")
    parser.add_argument(
        "--tasks", type=int, default=3,
        help="Number of tasks to run"
    )
    parser.add_argument(
        "--trials", type=int, default=1,
        help="Number of trials per task"
    )
    parser.add_argument(
        "--model", type=str,
        default="openrouter/qwen/qwen3-32b",
        help="Model to use"
    )
    args = parser.parse_args()
    setup()
    run(tasks=args.tasks, trials=args.trials, model=args.model)


if __name__ == "__main__":
    main()
