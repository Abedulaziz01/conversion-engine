import json, csv

print("\n--- Verifying data files ---\n")

try:
    with open("data/crunchbase_sample.json", encoding="utf-8") as f:
        data = json.load(f)
    count = len(data) if isinstance(data, list) else len(data.get("companies", []))
    icon = "OK" if count >= 100 else "LOW"
    print(f"crunchbase_sample.json: {count} records [{icon}]")
except Exception as e:
    print(f"crunchbase_sample.json: FAILED - {e}")

try:
    with open("data/layoffs.csv", encoding="utf-8", errors="ignore") as f:
        rows = list(csv.reader(f))
    count = len(rows) - 1
    icon = "OK" if count > 100 else "LOW"
    print(f"layoffs.csv: {count} rows [{icon}]")
except Exception as e:
    print(f"layoffs.csv: FAILED - {e}")

try:
    with open("data/job_posts_snapshot.json", encoding="utf-8") as f:
        data = json.load(f)
    count = len(data.get("companies", []))
    icon = "OK" if count > 0 else "EMPTY"
    print(f"job_posts_snapshot.json: {count} companies [{icon}]")
except Exception as e:
    print(f"job_posts_snapshot.json: FAILED - {e}")

print("\n--- Done ---\n")