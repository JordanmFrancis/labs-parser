import csv
import json
from pathlib import Path
from datetime import date
import sys
import anthropic
from dotenv import load_dotenv
import hashlib
from models import Draw, LabResult, OptimalRange
from db import init_db, insert_draw
load_dotenv()

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
CSV_FILE = Path(__file__).parent / "labs.csv"
THRESHOLD = 1.12
# Load the labs.csv file
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


def load_file(file_path: str) -> list[dict]:
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext == ".csv":
        return load_csv(path)       # ← still uses load_csv
    elif ext == ".pdf":
        from pdf_parser import parse_pdf
        return normalize_rows(parse_pdf(file_path))
    elif ext in IMAGE_EXTENSIONS:
        from image_parser import parse_image
        return normalize_rows(parse_image(file_path))
    

#Filter out the most recent lab result for each marker
def get_most_recent(labs):
    latest = {}
    for row in labs:
        marker = row["marker"]
        if marker not in latest or row["date"] > latest[marker]["date"]:
            latest[marker] = row
    return list(latest.values())
# Filter out labs that are out of range
def flag_out_of_range(labs):
    out_of_range = []
    for lab in labs:
        if lab["value"] > lab["range_high"] or lab["value"] < lab["range_low"]:
            out_of_range.append(lab)
    return out_of_range
# Calculate how far out of range a lab value is as a percentage of the reference range
def percent_out_of_range(lab):
    if lab["value"] > lab["range_high"] and lab["range_high"] != 0:
        return ((lab["value"] / lab["range_high"]) - 1) * 100
    elif lab["value"] > lab["range_high"] and lab["range_high"] == 0:
        return 100
    elif lab["value"] < lab["range_low"]:
        if lab["value"] < 0:
            return "Invalid Value"
        if lab["range_low"] == 0:
            return 100
        return ((lab["range_low"] - lab["value"]) / lab["range_low"]) * 100
    else:
        return 0
    
# Determine if a lab is trending up or down
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
    

# Agent tool runner
def run_tool(name, input, all_labs):
    if name == "get_optimal_range":
        return get_optimal_range(input["marker"])
    elif name == "calculate_ratio":
        return calculate_ratio(input["numerator_marker"], input["denominator_marker"], all_labs)
    elif name == "get_historical_values":
        return get_historical_values(input["marker"], all_labs)
    else:
        return {"error": f"Unknown tool: {name}"}


# Function to get the optimal range for a lab marker
def get_optimal_range(marker: str) -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="You are a functional medicine lab expert.",
        tools=[{
            "name": "return_optimal_range",
            "description": "Return the functional-medicine optimal range for a lab marker",
            "input_schema": OptimalRange.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "return_optimal_range"},
        messages=[{
            "role": "user",
            "content": f"What is the functional-medicine optimal range for {marker}?"
        }]
    )
    tool_block = next(b for b in response.content if b.type == "tool_use")
    return OptimalRange(**tool_block.input).model_dump()

# Function to calculate the ratio of two lab markers
def calculate_ratio(numerator_marker: str, denominator_marker: str, labs: list) -> dict:
    most_recent = get_most_recent(labs)
    
    num_matches = [lab for lab in most_recent if lab["marker"] == numerator_marker]
    den_matches = [lab for lab in most_recent if lab["marker"] == denominator_marker]
    
    if not num_matches:
        return {"error": f"{numerator_marker} not found in labs"}
    if not den_matches:
        return {"error": f"{denominator_marker} not found in labs"}
    
    num_value = num_matches[0]["value"]
    den_value = den_matches[0]["value"]
    
    if den_value == 0:
        return {"error": f"Cannot divide by zero ({denominator_marker} = 0)"}
    
    ratio = round(num_value / den_value, 2)
    
    return {
        "numerator_marker": numerator_marker,
        "numerator_value": num_value,
        "denominator_marker": denominator_marker,
        "denominator_value": den_value,
        "ratio": ratio
    }
    

def get_historical_values(marker: str, labs: list) -> dict:
    historical_values = []
    for lab in labs:
        if lab["marker"] == marker:
            historical_values.append(lab)
    historical_values = sorted(historical_values, key=lambda r: r["date"])
    historical_values = [{"date": lab["date"] if isinstance(lab["date"], str) else lab["date"].isoformat(), "value": lab["value"], "units": lab["units"]} for lab in historical_values]
    return historical_values


# Summarize the findings   
def summarize_labs(flagged_text, all_labs):
    client = anthropic.Anthropic()

    OPTIMAL_RANGE_TOOL = {
        "name": "get_optimal_range",
        "description": "Look up the functional-medicine optimal range for a lab marker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker": {"type": "string", "description": "Lab marker name"}
            },
            "required": ["marker"]
        }
    }

    GET_RATIO_TOOL = {
        "name": "calculate_ratio",
        "description": "Calculate the ratio between two lab markers using their most recent values.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numerator_marker": {"type": "string"},
                "denominator_marker": {"type": "string"}
            },
            "required": ["numerator_marker", "denominator_marker"]
        }
    }

    GET_HISTORICAL_VALUES_TOOL = {
        "name": "get_historical_values",
        "description": "Return the full historical values for a specific lab marker across all dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "marker": {"type": "string"}
            },
            "required": ["marker"]
        }
    }

    messages = [{"role": "user", "content": flagged_text}]
    tools = [OPTIMAL_RANGE_TOOL, GET_RATIO_TOOL, GET_HISTORICAL_VALUES_TOOL]
    
    MAX_ITERATIONS = 10
    for _ in range(MAX_ITERATIONS):
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system="You are a lab result analyst with access to tools for looking up optimal ranges, calculating clinically meaningful ratios, and inspecting historical values. Use these tools proactively to give a deeper analysis than just reading the out-of-range list. Guidelines: For each out-of-range marker, call lookup_optimal_range to see if there is a stricter optimal range worth mentioning. If multiple related markers are flagged (e.g., lipids), call calculate_ratio for clinically meaningful combinations (LDL/HDL, TG/HDL, ApoB/ApoA1). If a marker's trend is 'Stable' but the value is concerning, call get_historical_values to check whether it has been persistently out of range. Final summary is 4-6 sentences. No disclaimers. Name specific markers and values.",
            tools=tools,
            messages=messages
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            print()
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "(no text returned)"

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input, all_labs)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result)
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

    return "Tool loop exceeded max iterations"

def normalize_rows(rows: list[dict]) -> list[dict]:
    normalized = []
    for row in rows:
        normalized.append({
            "date": date.today(),
            "marker": row["marker"],
            "value": row["value"] if row["value"] is not None else 0,
            "units": row.get("unit", row.get("units", "")),
            "range_low": row.get("reference_low", row.get("range_low", 0)) or 0,
            "range_high": row.get("reference_high", row.get("range_high", 0)) or 0,
        })
    return normalized


# Main function to run the analysis
def main():
    if len(sys.argv) < 2:
        file_path = str(CSV_FILE)
    else:
        file_path = sys.argv[1]
    all_labs = load_file(file_path)

    init_db()
    file_hash = hashlib.md5(Path(file_path).read_bytes()).hexdigest()
    draw = Draw(
        date=all_labs[0]["date"],
        source=Path(file_path).name,
        values=[
            LabResult(marker=row["marker"], value=row["value"])
            for row in all_labs
        ]
    )
    try:
        draw_id = insert_draw(draw, file_hash)
        print(f"Saved to database as draw #{draw_id}")
    except Exception as e:
        print(f"DB save skipped: {e}")

    latest = get_most_recent(all_labs)
    flagged = flag_out_of_range(latest)
    flagged = sorted(flagged, key=lambda lab: percent_out_of_range(lab), reverse=True)
    print(f"Flagged Labs (out of range):")
    lines = []
    for lab in flagged:
        percent = percent_out_of_range(lab)
        trend = find_trends(all_labs, lab["marker"])
        if lab["value"] > lab["range_high"]:
            direction = "above upper limit"
        elif lab["value"] < lab["range_low"]:
            direction = "below lower limit"
        line = f"{lab['marker']}: {lab['value']} {lab['units']} Reference Range: {lab['range_low']} - {lab['range_high']} {round(percent, 1)}% {direction}. Trend: {trend}"
        lines.append(line)
        print(line)
        print("---")

    try:
        print("\n--- AI Summary ---")
        summarize_labs("\n".join(lines), all_labs)
    except Exception as e:
        print(f"\nAI summary unavailable: {e}")


if __name__ == "__main__":
    main()