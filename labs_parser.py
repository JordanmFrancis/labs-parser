import csv
from pathlib import Path
from datetime import date

CSV_FILE = Path(__file__).parent / "labs.csv"
THRESHOLD = 1.12

def load_csv(path):
    labs = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                labs.append({
                    "date": date.fromisoformat(row["date"]),
                    "marker": row["marker"],
                    "value": float(row["value"]),
                    "units": row["units"],
                    "range_low": float(row["range_low"]),
                    "range_high": float(row["range_high"])
                })
            except ValueError as e:
                print(f"Warning: skipping bad row — {e}")
                continue
    return labs

def get_most_recent(labs):
    latest = {}
    for row in labs:
        marker = row["marker"]
        if marker not in latest or row["date"] > latest[marker]["date"]:
            latest[marker] = row
    return list(latest.values())

def flag_out_of_range(labs):
    out_of_range = []
    for lab in labs:
        if lab["value"] > lab["range_high"] or lab["value"] < lab["range_low"]:
            out_of_range.append(lab)
    return out_of_range

def percent_out_of_range(lab):
    if lab["value"] > lab["range_high"]:
        return ((lab["value"] / lab["range_high"]) -1) *100
    elif lab["value"] < lab["range_low"]:
        if lab["value"] < 0:
            return "Invalid Value"
        return ((lab["range_low"] - lab["value"]) / lab["range_low"]) * 100
    else: return 0
    
    
def find_trends(labs, marker):
    matches = [row for row in labs if row["marker"] == marker]
    matches = sorted(matches, key=lambda r: r["date"])
    if len(matches) < 2:
        return "No Trend"
    elif matches[-1]["value"] > (matches[-2]["value"] * THRESHOLD):
        return "Up"
    elif matches[-1]["value"] < (matches[-2]["value"] * (2 - THRESHOLD)):
        return "Down"
    else: 
        return "Stable"

def main():
    all_labs = load_csv(CSV_FILE)
    latest = get_most_recent(all_labs)
    flagged = flag_out_of_range(latest)
    flagged = sorted(flagged, key=lambda lab: percent_out_of_range(lab), reverse=True)
    for lab in flagged:
        percent = percent_out_of_range(lab)
        trend = find_trends(all_labs, lab["marker"])
        if lab["value"] > lab["range_high"]:
            direction = "above upper limit"
        elif lab["value"] < lab["range_low"]:
            direction = "below lower limit"
        print(f"{lab['marker']}: {lab['value']} {lab['units']} Reference Range: {lab['range_low']} - {lab['range_high']} {round(percent, 1)}% {direction}. Trend: {trend}")

if __name__ == "__main__":
    main()