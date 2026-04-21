---
date: 2026-04-13
type: deliverable
tags: [dev, claude]
project: learning-python
---

# Lab Parser v7 Spec — FastAPI Backend

Related: [[labs_parser_roadmap]] · [[labs_parser_v6_spec]]

By v6 my parser is solid as a CLI. v7 turns it into a web service. Same logic, exposed over HTTP. Once this is done, anyone (or anything — including a frontend, an MCP client, my phone) can hit my parser as an API. This is the version where the script becomes infrastructure.

## What I Want to Learn

- FastAPI — what a web framework is, why I'd use one
- Async/await — the actual `async def` thing, not just buzzwords
- REST endpoint design — HTTP verbs, status codes, request/response shapes
- File upload handling (multipart form data)
- Pydantic in FastAPI (auto-validates request bodies, generates OpenAPI docs)
- Server-sent events (SSE) for streaming responses to a client
- CORS — letting a frontend on a different domain hit my API
- Background tasks (so a slow PDF parse doesn't block the request)

## Why FastAPI

FastAPI is async-first, uses Pydantic for validation (I already have my models from v5/v6), and auto-generates OpenAPI docs at `/docs`. That means I literally can't ship without API documentation, which is correct. Flask is older and synchronous, Django is huge, FastAPI is the right learning target.

## API Design

Fourteen endpoints. RESTful where it makes sense, RPC-style where it doesn't. Organized by the frontend screens they serve.

### Draws (Upload screen)

| Method | Path | Purpose | Priority |
|--------|------|---------|----------|
| `POST` | `/draws/parse` | Upload a CSV/PDF/image, parse it, return extracted rows with confidence scores. **Nothing saved yet.** | 🟢 MVP |
| `POST` | `/draws/confirm` | Accept reviewed/corrected rows from the parse step, write to DB. Returns `draw_id`. | 🟢 MVP |
| `GET` | `/draws` | List all draws (paginated). | 🟢 MVP |
| `GET` | `/draws/{draw_id}` | Get a single draw with all its results. | 🟢 MVP |
| `DELETE` | `/draws/{draw_id}` | Delete a draw. | 🟢 MVP |

### Markers (Dashboard + Marker Detail screens)

| Method | Path | Purpose | Priority |
|--------|------|---------|----------|
| `GET` | `/markers` | List all marker definitions (name, short_name, unit, ranges, optimal, group). | 🟢 MVP |
| `GET` | `/markers/{marker}` | Single marker definition + latest value + flag status. | 🟢 MVP |
| `GET` | `/markers/{marker}/history` | Full time-series for a marker. Shape: `[{date, value}]`. | 🟢 MVP |

### Analysis (Dashboard + Marker Detail chat)

| Method | Path | Purpose | Priority |
|--------|------|---------|----------|
| `POST` | `/analyze/{draw_id}` | Run the v3 tool use summary on a draw. Returns SSE stream. | 🟢 MVP |
| `GET` | `/dashboard/stats` | Aggregated stats: total markers, flagged count, last draw date, draws count. | 🟢 MVP |
| `GET` | `/markers/{marker}/optimal` | Look up optimal range (cached from DB, falls back to Haiku call). | 🟡 phase 2 |
| `POST` | `/chat/{marker}` | Per-marker scoped chat. SSE stream. | 🟡 phase 2 |

### System

| Method | Path | Purpose | Priority |
|--------|------|---------|----------|
| `GET` | `/health` | Healthcheck. Returns `{"status": "ok"}`. | 🟢 MVP |

Agent run and protocol endpoints are deferred to v12 — they depend on the agentic loop.

## Project Structure

The script becomes a real package.

```
labs_parser/
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, routes, middleware
│   ├── routers/
│   │   ├── draws.py
│   │   ├── markers.py
│   │   └── analyze.py
│   └── dependencies.py      # DB session injection
├── core/
│   ├── parser_csv.py        # from v1
│   ├── parser_pdf.py        # from v4
│   ├── analyzer.py          # flag_out_of_range, find_trends from v1
│   ├── summarizer.py        # tool use loop from v3/v6
│   └── tools.py             # the 3 tools from v3
├── db.py                    # from v5
├── models.py                # Pydantic from v5/v6
├── cli.py                   # original CLI still works
├── tests/
└── pyproject.toml           # real packaging
```

## Async/Await — What It Actually Is

Async lets one process handle many requests concurrently without threads. When a request is waiting on the database or the Anthropic API, the process moves on to other requests. With sync code, the process sits and twiddles its thumbs.

Practical rules I'll follow:
- All FastAPI route handlers are `async def`
- All Anthropic API calls use `AsyncAnthropic` (separate client class)
- All database calls use `aiosqlite` (async SQLite driver)
- If I have to call sync code from an async route, wrap it in `await asyncio.to_thread(sync_func, args)`

I'll need to update v5's `db.py` to async. Sync version stays for the CLI.

## Two-Step Upload Flow

The frontend prototype has a staged upload: parse → review ambiguities → save. This is a deliberate design choice — vision extraction isn't perfect (the "9.l" vs "9.1" problem from v4), and new markers might appear that aren't in the DB yet. The user needs a chance to review before anything hits the database.

### Step 1: Parse (nothing saved)

```python
from fastapi import FastAPI, UploadFile, HTTPException
import hashlib

app = FastAPI()

@app.post("/draws/parse")
async def parse_draw(file: UploadFile):
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    # Check for duplicate before doing expensive parsing
    if await file_already_imported(file_hash):
        raise HTTPException(409, "This file was already imported")

    if file.filename.endswith(".csv"):
        rows = parse_csv_bytes(contents)
    elif file.filename.endswith(".pdf"):
        rows = await parse_pdf_bytes(contents)
    elif file.filename.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic"}:
        rows = await parse_image_bytes(contents)
    else:
        raise HTTPException(400, f"Unsupported file type: {file.filename}")

    # Classify each row
    staged = []
    for row in rows:
        marker_id = await resolve_marker_name(row.marker)
        status = "ok"
        reason = None
        if marker_id is None:
            status = "review"
            reason = "New marker — map or create?"
        elif row.confidence is not None and row.confidence < 0.85:
            status = "review"
            reason = f"OCR confidence {row.confidence:.2f} — \"{row.raw_text}\" vs \"{row.value}\""
        elif await is_flagged(row.value, marker_id):
            status = "flagged"
        staged.append({**row.model_dump(), "status": status, "reason": reason, "marker_id": marker_id})

    return {"file_hash": file_hash, "source": file.filename, "rows": staged}
```

### Step 2: Confirm (save to DB)

```python
@app.post("/draws/confirm")
async def confirm_draw(payload: ConfirmPayload):
    """Accept reviewed rows from the parse step. Rows with status='skip' are dropped."""
    draw_id = await insert_draw(
        date=payload.date,
        source=payload.source,
        file_hash=payload.file_hash,
        rows=[r for r in payload.rows if r.status != "skip"]
    )
    return {"draw_id": draw_id, "rows_saved": len(payload.rows)}
```

The frontend sends back the corrected rows — user may have changed values, mapped unknown markers, or skipped rows.

## Streaming Analysis via SSE

The v6 streaming summary becomes Server-Sent Events. The client opens a connection and gets tokens as they arrive.

```python
from fastapi.responses import StreamingResponse

@app.post("/analyze/{draw_id}")
async def analyze(draw_id: int):
    async def event_generator():
        async for token in stream_analysis(draw_id):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## CORS for the v8 Frontend

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://labs.jordanfrancis.dev"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Hardcode the allowed origins. Don't `allow_origins=["*"]` even in dev — bad habit.

## Background Tasks

Vision-API PDF parsing can take 30+ seconds. Don't make the client wait synchronously. Pattern:

```python
@app.post("/draws/import-async")
async def import_draw_async(file: UploadFile, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    background_tasks.add_task(process_upload, file, job_id)
    return {"job_id": job_id, "status_url": f"/jobs/{job_id}"}
```

Plus a `/jobs/{job_id}` endpoint to poll status. For v7 this lives in memory (a dict). v9 moves it to Redis.

## Running It

```bash
uvicorn labs_parser.api.main:app --reload
```

Auto-reloads on code change. Hit `http://localhost:8000/docs` for the auto-generated Swagger UI — every endpoint has try-it-now buttons. This is the FastAPI superpower.

## Edge Cases

| Case | Behavior |
|------|----------|
| Upload >10MB PDF | Reject with 413 (config `MAX_UPLOAD_SIZE`) |
| Concurrent imports of same file | Second one fails with 409 (DB unique constraint catches it) |
| Anthropic API down during stream | Send error event in SSE stream, close connection |
| Slow PDF blocks event loop | Wrap in `asyncio.to_thread` (sync `pdfplumber`) or use background task |
| Client disconnects mid-stream | Catch `asyncio.CancelledError`, log it, clean up |
| OpenAPI docs leak in production | Set `docs_url=None, redoc_url=None` in prod env |
| Parse step returns unknown marker | Row gets `status: "review"`, frontend shows "map or create?" UI |
| Parse step returns low-confidence row | Row gets `status: "review"`, frontend shows raw OCR text + proposed value |
| User corrects a value in confirm step | Frontend sends the corrected value; backend saves it as-is |
| User skips a row in confirm step | Row excluded from DB insert |
| User closes browser after parse, before confirm | Nothing saved — parse is stateless. User re-uploads to try again. |

## Files to Add/Change

- Restructure into the package layout above
- `api/main.py`, `api/routers/*.py` — FastAPI app
- `aiosqlite` and `httpx` added to requirements
- `requirements.txt` → `pyproject.toml` (with `[project]` and `[tool.uv]` sections)

## What's New vs v6

| Concept | v6 | v7 |
|---------|----|----|
| Interface | CLI only | CLI + HTTP API |
| Concurrency | sync, one thing at a time | async, many requests |
| Validation | Pydantic in scripts | Pydantic in route handlers, automatic 422 errors |
| Documentation | README | auto-generated OpenAPI/Swagger at `/docs` |
| Streaming | terminal stdout | SSE over HTTP |

## Out of Scope for v7

- Authentication (single-user, localhost only)
- Rate limiting
- Database migrations
- Production deployment (v9)
- WebSockets (SSE is enough)
- GraphQL
