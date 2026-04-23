import json
from pathlib import Path


def main() -> None:
    score_path = Path(__file__).with_name("score_log.json")

    with score_path.open("r", encoding="utf-8") as f:
        log = json.load(f)

    print(f"Total entries: {len(log)}")
    print()

    total_cost = 0.0
    pass_rates = []
    p50s = []
    p95s = []

    for entry in log:
        print(f"Run: {entry['run_id']}")
        print(f"  pass@1:   {entry.get('pass_at_1', 'N/A')}")
        print(f"  ci_low:   {entry.get('ci_95_low', 'N/A')}")
        print(f"  ci_high:  {entry.get('ci_95_high', 'N/A')}")
        print(f"  cost_usd: {entry.get('cost_usd', 'N/A')}")
        print(f"  p50_ms:   {entry.get('p50_latency_ms', 'N/A')}")
        print(f"  p95_ms:   {entry.get('p95_latency_ms', 'N/A')}")
        print()

        total_cost += float(entry.get("cost_usd") or 0)
        pass_rates.append(float(entry.get("pass_at_1") or 0))
        p50s.append(int(entry.get("p50_latency_ms") or 0))
        p95s.append(int(entry.get("p95_latency_ms") or 0))

    mean_pass = sum(pass_rates) / len(pass_rates) if pass_rates else 0
    avg_cost = total_cost / len(log) if log else 0
    avg_p50 = sum(p50s) // len(p50s) if p50s else 0
    avg_p95 = sum(p95s) // len(p95s) if p95s else 0

    print(f"Mean pass@1: {round(mean_pass, 4)}")
    print(f"Total cost: ${round(total_cost, 4)}")
    print(f"Avg cost per run: ${round(avg_cost, 4)}")
    print(f"Avg p50: {avg_p50}ms")
    print(f"Avg p95: {avg_p95}ms")


if __name__ == "__main__":
    main()
