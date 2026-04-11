---
date: 2026-04-10
type: deliverable
tags: [dev, health, research]
project: learning-python
---

# Lab Parser v2 Spec — Anthropic API Integration

v1 flags out-of-range markers and shows trends. v2 takes that output and sends it to Claude via the Anthropic API to get a plain-English summary a normal person can actually read.

## What Changes from v1

v1's `main()` prints flagged labs to the terminal. v2 keeps all of that, but adds a step after: collect the flagged output into a string, send it to the Anthropic API as a user message, and print Claude's response below the raw output.

## New Dependency

`anthropic` — the official Python SDK. Install with `pip install anthropic`.

## API Key Handling

Store the API key in an environment variable: `ANTHROPIC_API_KEY`. The program reads it with `os.environ.get("ANTHROPIC_API_KEY")`. If the key is missing, print a clear error and fall back to v1 behavior (raw output only, no crash).

**Never hardcode the key. Never commit it to git.**

## New Function: `summarize_labs(flagged_text)`

### Input
A string containing the formatted flagged lab output — the same lines v1 prints to the terminal. Example:

```
Lp(a): 125.0 nmol/L Reference Range: 0.0 - 75.0 66.7% above upper limit. Trend: No Trend
HDL: 41.0 mg/dL Reference Range: 45.0 - 100.0 8.9% below lower limit. Trend: Stable
Globulin: 2.0 g/dL Reference Range: 2.1 - 3.5 4.8% below lower limit. Trend: Stable
```

### What It Does
1. Creates an Anthropic client: `client = anthropic.Anthropic()`
2. Sends a `messages.create()` call with:
   - `model`: `"claude-sonnet-4-20250514"`
   - `max_tokens`: `1024`
   - `system`: A system prompt telling Claude it's a lab analyst summarizing blood work for someone who understands health but wants a concise plain-English read
   - `messages`: One user message containing the flagged lab text
3. Returns the response text: `response.content[0].text`

### System Prompt
```
You are a lab result analyst. The user will give you a list of out-of-range blood markers with their values, reference ranges, percent deviation, and trend direction. Summarize the findings in plain English. Be specific — name the markers, state whether they're high or low, and note any trends. Keep it to 2-4 sentences. No disclaimers, no "consult your doctor."
```

### Output
The plain-English summary string. Printed below the raw flagged output, separated by a blank line and a header like:

```
--- AI Summary ---
Your Lp(a) is significantly elevated at 66.7% above the upper limit. This is a genetic cardiovascular risk marker...
```

## Updated `main()` Flow

```
1. Load CSV (unchanged)
2. Get most recent per marker (unchanged)
3. Flag out of range (unchanged)
4. Sort by severity (unchanged)
5. Print each flagged lab (unchanged)
6. NEW: Collect all printed lines into a single string
7. NEW: Pass that string to summarize_labs()
8. NEW: Print the summary below a separator
```

## Edge Cases

- **No API key set:** Print `"No ANTHROPIC_API_KEY found — skipping AI summary."` and show raw output only. Don't crash.
- **API call fails** (network error, bad key, rate limit): Catch the exception, print `"AI summary unavailable: {error}"`, show raw output only. Don't crash.
- **No flagged labs:** Skip the API call entirely. Print `"All markers within reference range."` — no need to waste a call.
- **API returns empty response:** Print `"AI summary returned empty."` and continue.

## Example Full Output

```
Lp(a): 125.0 nmol/L Reference Range: 0.0 - 75.0 66.7% above upper limit. Trend: No Trend
HDL: 41.0 mg/dL Reference Range: 45.0 - 100.0 8.9% below lower limit. Trend: Stable
Globulin: 2.0 g/dL Reference Range: 2.1 - 3.5 4.8% below lower limit. Trend: Stable

--- AI Summary ---
Your Lp(a) is significantly elevated at 66.7% above the upper limit — this is a
genetic cardiovascular risk marker that doesn't respond to lifestyle changes and
is worth discussing with a lipid specialist. HDL is mildly low at 8.9% below
range and holding stable, which typically responds to exercise and diet changes.
Globulin is just barely below range and stable — not concerning on its own but
worth watching over time.
```

## Files to Change

- `labs_parser.py` — add `import os`, `import anthropic`, the `summarize_labs()` function, and update `main()`
- `.gitignore` — add `.env` (in case you use a `.env` file later)

## Out of Scope for v2

- Sending historical data (all draws) to the API — v2 only sends the flagged most-recent values
- Tool use / function calling — that's v3
- PDF input — that's v4
- Streaming the API response — keep it simple, just wait for the full response
