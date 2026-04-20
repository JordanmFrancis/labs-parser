# Lab Parser v3 Spec — Tool Use

v2 sent the flagged labs to the Anthropic API and got a plain-English summary back. That was one call, one response. In v3 I want Claude to actually investigate the labs — look up optimal ranges, compute ratios between markers, and pull historical values when it thinks it needs them. To do that I need to give Claude tools it can call on its own.

## What Changes from v2

- Define 3 tools (Python functions + JSON schemas)
- Pass the tool definitions into `messages.create()`
- Add a loop: call API → if Claude asks for a tool, run it, feed the result back, call again → repeat until Claude returns a final text answer

The loop is the new concept. In v2 I called the API once. In v3 I might call it 3-5 times in a single run because Claude is using the tools to dig deeper before summarizing.

## Tool 1: `lookup_optimal_range`

I don't want to hardcode optimal ranges. They're opinionated and vary by practitioner, and maintaining a table would suck. Instead this tool is itself an API call — a cheap one to Haiku — asking it to return the optimal range as JSON.

So the outer Sonnet call uses tools. When it calls `lookup_optimal_range("Lp(a)")`, my Python function fires a separate API call to Haiku, which returns structured JSON, which gets handed back to Sonnet. LLM as a function.

### Function
```python
def lookup_optimal_range(marker: str) -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="You are a functional medicine lab expert. Return optimal ranges as JSON only, no prose.",
        messages=[{
            "role": "user",
            "content": f'Return the optimal functional-medicine range for "{marker}". Respond with JSON only: {{"marker": "...", "optimal_low": number, "optimal_high": number, "units": "...", "reasoning": "brief why"}}. If you do not know the marker, return {{"error": "unknown marker"}}.'
        }]
    )
    return json.loads(response.content[0].text)
```

### Schema
```python
{
    "name": "lookup_optimal_range",
    "description": "Look up the functional-medicine optimal range for a lab marker. Optimal ranges are usually tighter than standard reference ranges. Use this to assess whether a marker is truly optimal even if it is inside the lab's normal range.",
    "input_schema": {
        "type": "object",
        "properties": {
            "marker": {"type": "string", "description": "Lab marker name (e.g., LDL, HDL, Lp(a))"}
        },
        "required": ["marker"]
    }
}
```

## Tool 2: `calculate_ratio`

Pure Python. Finds the most recent value of each marker and divides them. Returns the ratio rounded to 2 decimals plus a short interpretation for the ratios I actually care about (LDL/HDL, TG/HDL, ApoB/ApoA1).

### Function
```python
def calculate_ratio(numerator_marker: str, denominator_marker: str, labs: list) -> dict:
    # Find most recent value for each marker in labs
    # Compute numerator / denominator
    # Return {numerator, denominator, ratio, interpretation}
    # If either marker missing: return {"error": "..."}
```

### Known ratio interpretations
- **LDL/HDL**: <2.5 ideal, >3.5 elevated cardio risk
- **TG/HDL**: <1.5 ideal, >3.0 insulin resistance marker
- **ApoB/ApoA1**: <0.8 ideal

If the ratio isn't one I've flagged, interpretation is just "No interpretation defined."

### Schema
```python
{
    "name": "calculate_ratio",
    "description": "Calculate the ratio between two lab markers using their most recent values. Clinically meaningful ratios include LDL/HDL, TG/HDL (insulin resistance), and ApoB/ApoA1 (atherosclerosis risk).",
    "input_schema": {
        "type": "object",
        "properties": {
            "numerator_marker": {"type": "string"},
            "denominator_marker": {"type": "string"}
        },
        "required": ["numerator_marker", "denominator_marker"]
    }
}
```

## Tool 3: `get_historical_values`

Pure Python. Returns every value for a given marker across all draws. v1's trend logic only looks at the last 2 points — this lets Claude see the full picture when the 2-point trend isn't enough.

### Function
```python
def get_historical_values(marker: str, labs: list) -> dict:
    # Filter labs to matching marker
    # Sort by date ascending
    # Convert date to ISO string (dates aren't JSON-serializable — same trap as v2)
    # Return {"marker": ..., "history": [{"date": "...", "value": ..., "units": "..."}, ...]}
```

### Schema
```python
{
    "name": "get_historical_values",
    "description": "Return the full historical values for a specific lab marker across all dates in the CSV. Use when the simple up/down trend from the summary is not enough context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "marker": {"type": "string"}
        },
        "required": ["marker"]
    }
}
```

## The Tool Use Loop

This replaces v2's single `summarize_labs()` call.

```python
def summarize_labs_with_tools(flagged_text, all_labs):
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": flagged_text}]
    tools = [OPTIMAL_RANGE_TOOL, RATIO_TOOL, HISTORY_TOOL]
    
    MAX_ITERATIONS = 10
    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages
        )
        
        messages.append({"role": "assistant", "content": response.content})
        
        if response.stop_reason == "end_turn":
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
        
        return f"Unexpected stop_reason: {response.stop_reason}"
    
    return "Tool loop exceeded max iterations"
```

### `run_tool` dispatcher
```python
def run_tool(name, input, all_labs):
    if name == "lookup_optimal_range":
        return lookup_optimal_range(input["marker"])
    elif name == "calculate_ratio":
        return calculate_ratio(input["numerator_marker"], input["denominator_marker"], all_labs)
    elif name == "get_historical_values":
        return get_historical_values(input["marker"], all_labs)
    else:
        return {"error": f"Unknown tool: {name}"}
```

## System Prompt

```
You are a lab result analyst with access to tools for looking up optimal ranges, calculating clinically meaningful ratios, and inspecting historical values. Use these tools proactively to give a deeper analysis than just reading the out-of-range list.

Guidelines:
- For each out-of-range marker, call lookup_optimal_range to see if there is a stricter optimal range worth mentioning.
- If multiple related markers are flagged (e.g., lipids), call calculate_ratio for clinically meaningful combinations (LDL/HDL, TG/HDL, ApoB/ApoA1).
- If a marker's trend is "Stable" but the value is concerning, call get_historical_values to check whether it has been persistently out of range.
- Final summary is 4-6 sentences. No disclaimers. Name specific markers and values.
```

## Edge Cases

| Case | Behavior |
|------|----------|
| Tool returns `error` | Send error back to Claude — it handles gracefully |
| Claude calls unknown tool | `run_tool` returns `{"error": "Unknown tool"}` |
| Infinite tool loop | Hard cap of 10 iterations, then return error string |
| API fails mid-loop | Wrap whole function in try/except, fall back to raw flagged output |
| No API key | Warn + skip summary, show raw v1 output only |
| Haiku returns non-JSON | Catch `json.JSONDecodeError` in `lookup_optimal_range`, return `{"error": "Haiku returned non-JSON"}` |

## Files to Change

- `labs_parser.py` — add `import json`, the 3 tool functions, their schemas, `run_tool`, `summarize_labs_with_tools`. Replace the v2 call in `main()`.

## Example Expected Flow

1. Run the program
2. v1 logic prints flagged: Lp(a) high, HDL low, Globulin low
3. `summarize_labs_with_tools()` kicks in
4. Sonnet sees flagged list, calls `lookup_optimal_range("Lp(a)")` → Haiku returns `{optimal_high: 30, reasoning: "..."}`
5. Sonnet calls `lookup_optimal_range("HDL")` → `{optimal_low: 60, ...}`
6. Sonnet notices HDL and sees lipids in my stack, calls `calculate_ratio("LDL", "HDL")`
7. Sonnet calls `get_historical_values("HDL")` to see if it's been persistently low
8. Sonnet returns final text weaving all this together

## Out of Scope for v3

- Web search tool (live research) — v4+
- Protocol recommendation engine ("if HDL low, suggest niacin") — v4
- PDF parsing — v4
- Dynamic tool registration from config — v3 hardcodes the 3 tools
- Caching tool results across runs — every run is fresh
