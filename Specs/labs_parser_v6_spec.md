---
date: 2026-04-13
type: deliverable
tags: [dev, claude]
project: learning-python
---

# Lab Parser v6 Spec — Streaming + Structured Outputs

Related: [[labs_parser_roadmap]] · [[labs_parser_v5_spec]]

By v5 the program is functional but the API patterns I'm using are old-school. v6 modernizes them. Two upgrades:

1. **Streaming responses** — Claude's summary prints token-by-token instead of the whole 4-second wait followed by a wall of text.
2. **Structured outputs** — Get rid of the `strip_code_fences` hack from v3. Use Pydantic schemas + `tool_choice` to guarantee Claude returns valid JSON every time.

Both are worth learning because they're the patterns I'll use in every API call going forward.

## What I Want to Learn

- Streaming responses (`client.messages.stream()`)
- Async iteration (the `with ... as stream` pattern, `for event in stream`)
- Pydantic models as JSON schemas — same models from v5, now driving the API
- `tool_choice={"type": "tool", "name": "..."}` — forcing Claude to use a specific tool, which forces structured output
- The "single-tool extraction" pattern for replacing `json.loads` parsing

## Streaming

In v3 I called `client.messages.create()` and waited. The whole response came back at once. v6 changes the summary call to:

```python
def summarize_labs_streaming(flagged_text):
    client = anthropic.Anthropic()
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=tools,
        messages=[{"role": "user", "content": flagged_text}]
    ) as stream:
        for text_chunk in stream.text_stream:
            print(text_chunk, end="", flush=True)
        print()
        return stream.get_final_message()
```

`text_stream` yields strings as they arrive. `flush=True` makes them appear immediately. `get_final_message()` returns the full message object after streaming finishes — needed for the tool use loop because I still need to check `stop_reason`.

### Streaming + Tool Use Loop

The v3 loop still applies. The only change: each iteration of the loop streams its text output. When Claude calls a tool, no text streams that iteration (just tool use blocks), I run the tool, loop again, and the next iteration streams the next chunk of reasoning + the final summary.

## Structured Outputs — Replacing `strip_code_fences`

v3's `lookup_optimal_range` calls Haiku, gets back markdown-fenced JSON, strips fences, parses. That's a hack. The right way: define a Pydantic model and force Claude to return it via tool use.

### The "Output as Tool" Pattern

```python
from pydantic import BaseModel

class OptimalRange(BaseModel):
    marker: str
    optimal_low: float
    optimal_high: float
    units: str
    reasoning: str

def lookup_optimal_range(marker: str) -> OptimalRange:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        tools=[{
            "name": "return_optimal_range",
            "description": "Return the functional-medicine optimal range",
            "input_schema": OptimalRange.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "return_optimal_range"},
        messages=[{
            "role": "user",
            "content": f"What is the functional-medicine optimal range for {marker}?"
        }]
    )
    tool_use_block = next(b for b in response.content if b.type == "tool_use")
    return OptimalRange(**tool_use_block.input)
```

What changed:
- No more JSON-in-text. Claude is FORCED to call the `return_optimal_range` tool because of `tool_choice`.
- `OptimalRange.model_json_schema()` auto-generates the input schema from the Pydantic model. One source of truth.
- The return is a typed `OptimalRange` object, not a dict. IDE autocomplete works. Typos throw errors.
- `strip_code_fences` is deleted. It was a workaround for a problem this pattern eliminates.

### Apply Same Pattern to `extract_rows_with_claude` (from v4)

The vision-API row extraction in v4 also returns JSON. Same fix:

```python
class LabValueExtraction(BaseModel):
    marker: str
    value: float
    units: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    date: str | None = None
    confidence: float | None = None   # 0.0–1.0 extraction confidence
    raw_text: str | None = None       # original OCR text before parsing (e.g., "9.l")

class ExtractedRows(BaseModel):
    rows: list[LabValueExtraction]
```

Force Claude to return `ExtractedRows`. No more `json.loads(strip_code_fences(...))`.

The `confidence` and `raw_text` fields are critical for the frontend's Upload screen. When vision extraction confidence is below 0.85, the frontend flags the row for human review and shows the raw OCR text side-by-side with the proposed parsed value (e.g., "9.l" → proposed "9.1 umol/L"). The system prompt for the vision call needs to be updated to instruct Claude to return a confidence score per row and the raw text it read from the image. Example system prompt addition: "For each row, include a confidence score (0.0 to 1.0) for how certain you are of the extracted value, and include the raw text exactly as printed on the document in `raw_text`."

## What Stays the Same

- The 3 tools from v3 (`lookup_optimal_range`, `calculate_ratio`, `get_historical_values`)
- The tool use loop in `summarize_labs`
- The database from v5

## Files Touched

- `labs_parser.py` — replace `client.messages.create` calls with `client.messages.stream` for the summary
- `tools.py` (extract from labs_parser.py) — rewrite `lookup_optimal_range` with structured output pattern
- `pdf_parser.py` — rewrite `extract_rows_with_claude` with structured output
- `models.py` — add `OptimalRange`, `LabValueExtraction`, `ExtractedRows`
- delete `strip_code_fences` — no longer needed

## Edge Cases

| Case | Behavior |
|------|----------|
| Stream interrupted mid-token | `with` block handles cleanup, partial output already printed |
| Tool call mid-stream | Stream yields tool_use blocks, loop continues normally |
| Pydantic validation fails on Claude's tool input | Catch `ValidationError`, return error to Claude in next loop iteration so it can retry |
| Network timeout during stream | Catch in the `with` block, fall back to non-streaming |
| `tool_choice` forced but Claude returns text anyway | Shouldn't happen with `tool_choice` set, but defensively check `stop_reason == "tool_use"` |

## What's New vs v5

| Concept | v5 | v6 |
|---------|----|----|
| Output | wait for full response | stream token-by-token |
| Structured data from Claude | parse JSON from text + strip fences | force tool call, get typed object |
| Pydantic role | input validation only | input validation + API output schemas |
| API patterns | basic `messages.create` | `messages.stream` + `tool_choice` |

## Out of Scope for v6

- Async streaming (sync version is fine until v7 when FastAPI forces async)
- Streaming the tool reasoning thinking blocks separately (Claude 4.5+ extended thinking) — nice to have, not core
- Server-sent events to a frontend (v8)
- Caching tool call results (v11 with embeddings)
