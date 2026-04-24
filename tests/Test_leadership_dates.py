import json
from pathlib import Path
from datetime import datetime, timezone

rows = json.loads(Path("data/crunchbase_sample.json").read_text(encoding="utf-8"))
today = datetime.now(timezone.utc).date()

results = []

for row in rows:
    leadership = row.get("leadership_hire")
    if not leadership:
        continue
    try:
        events = json.loads(leadership) if isinstance(leadership, str) else leadership
        if not isinstance(events, list):
            continue
        for event in events:
            date_text = str(event.get("key_event_date", ""))[:10]
            if not date_text:
                continue
            event_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            days_ago = (today - event_date).days
            label = event.get("label", "")
            name = row.get("name", "")
            results.append((days_ago, name, date_text, label))
    except Exception:
        continue

results.sort()

print(f"Total leadership events found: {len(results)}")
print()
print("Most recent 10:")
for days_ago, name, date_text, label in results[:10]:
    print(f"{name} | {date_text} | {days_ago} days ago")
    print(f"  {label}")
    print()