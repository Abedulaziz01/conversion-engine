from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "eval"
TAU2_ROOT = EVAL_DIR / "tau2-bench"
TAU2_SRC = TAU2_ROOT / "src"
ENV_PATH = ROOT / ".env"
SCORE_LOG_PATH = EVAL_DIR / "score_log.json"
TRACE_LOG_PATH = EVAL_DIR / "trace_log.jsonl"
DEFAULT_MODEL = "openrouter/qwen/qwen3-32b"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def ensure_tau2_importable() -> None:
    if str(TAU2_SRC) not in sys.path:
        sys.path.insert(0, str(TAU2_SRC))


def read_score_log() -> list[dict[str, Any]]:
    if not SCORE_LOG_PATH.exists():
        return []

    content = SCORE_LOG_PATH.read_text(encoding="utf-8").strip()
    if not content:
        return []

    data = json.loads(content)
    if not isinstance(data, list):
        raise RuntimeError("eval/score_log.json must contain a JSON array.")
    return data


def write_score_log(entries: list[dict[str, Any]]) -> None:
    SCORE_LOG_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def next_run_id(entries: list[dict[str, Any]]) -> str:
    return f"run_{len(entries) + 1:03d}"


def calc_pass_at_1(results: Any) -> float:
    simulations = getattr(results, "simulations", [])
    if not simulations:
        return 0.0

    rewards = []
    for simulation in simulations:
        reward_info = getattr(simulation, "reward_info", None)
        reward = getattr(reward_info, "reward", 0.0) if reward_info else 0.0
        rewards.append(1.0 if reward == 1.0 else 0.0)
    return sum(rewards) / len(rewards)


def calc_total_cost(results: Any) -> float:
    total = 0.0
    for simulation in getattr(results, "simulations", []):
        total += float(getattr(simulation, "agent_cost", 0.0) or 0.0)
        total += float(getattr(simulation, "user_cost", 0.0) or 0.0)
    return total


def should_null_cost(results: Any, total_cost: float, model_name: str) -> bool:
    simulations = getattr(results, "simulations", [])
    if not simulations:
        return False

    if total_cost != 0.0:
        return False

    # LiteLLM reports unknown-model pricing as 0 cost, which looks exact but is not.
    openrouter_model = model_name.startswith("openrouter/")
    any_llm_usage = any(
        len(getattr(simulation, "get_messages", lambda: [])()) > 0
        for simulation in simulations
    )
    return openrouter_model and any_llm_usage


def append_trace_log(results: Any, run_id: str) -> None:
    with TRACE_LOG_PATH.open("a", encoding="utf-8") as handle:
        for simulation in getattr(results, "simulations", []):
            payload = simulation.model_dump(mode="json")
            payload["run_id"] = run_id
            handle.write(json.dumps(payload))
            handle.write("\n")


def build_run_config() -> Any:
    from tau2.data_model.simulation import TextRunConfig

    model = os.getenv("TAU2_BASELINE_MODEL", DEFAULT_MODEL)
    num_tasks = int(os.getenv("TAU2_BASELINE_NUM_TASKS", "3"))
    num_trials = int(os.getenv("TAU2_BASELINE_NUM_TRIALS", "1"))
    seed = int(os.getenv("TAU2_BASELINE_SEED", "300"))

    return TextRunConfig(
        domain="retail",
        agent="llm_agent",
        user="user_simulator",
        llm_agent=model,
        llm_user=model,
        num_tasks=num_tasks,
        num_trials=num_trials,
        seed=seed,
        max_concurrency=1,
        log_level="ERROR",
        verbose_logs=False,
    )


def main() -> int:
    load_env_file(ENV_PATH)
    ensure_tau2_importable()

    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is required in .env for the baseline run.")

    from tau2.run import run_domain

    score_entries = read_score_log()
    run_id = next_run_id(score_entries)
    config = build_run_config()

    results = run_domain(config)
    total_cost = round(calc_total_cost(results), 4)
    cost_value = None if should_null_cost(results, total_cost, config.llm_agent) else total_cost

    score_entry = {
        "run_id": run_id,
        "domain": config.domain,
        "num_tasks": config.num_tasks,
        "num_trials": config.num_trials,
        "model": config.llm_agent,
        "pass_at_1": round(calc_pass_at_1(results), 4),
        "cost_usd": cost_value,
    }

    score_entries.append(score_entry)
    write_score_log(score_entries)
    append_trace_log(results, run_id)

    print(json.dumps(score_entry, indent=2))
    print(f"Saved score log to {SCORE_LOG_PATH}")
    print(f"Appended traces to {TRACE_LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
