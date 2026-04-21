from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from db import init_db, get_conn, get_marker_history, get_latest_draw, insert_draw
from models import LabResult, Draw
from labs_parser import run_tool, load_csv
import hashlib
import tempfile
import json as json_lib
from pathlib import Path


# --- Request/Response Models ---

class ConfirmRow(BaseModel):
    marker: str
    value: float
    status: str = "ok"

class ConfirmPayload(BaseModel):
    file_hash: str
    source: str
    date: str
    rows: list[ConfirmRow]


# --- App Setup ---

app = FastAPI(title="Labs Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()


# --- Health ---

@app.get("/health")
def health():
    return {"status": "ok"}


# --- Markers ---

@app.get("/markers")
def list_markers():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM markers ORDER BY group_name, name").fetchall()
        return [dict(row) for row in rows]


@app.get("/markers/{marker_name}/history")
def marker_history(marker_name: str):
    # Reuse db.py's function
    return get_marker_history(marker_name)


# --- Draws ---

@app.get("/draws")
def list_draws():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM draws ORDER BY date DESC").fetchall()
        return [dict(row) for row in rows]


@app.get("/draws/{draw_id}")
def get_draw(draw_id: int):
    with get_conn() as conn:
        draw = conn.execute("SELECT * FROM draws WHERE id = ?", (draw_id,)).fetchone()
        if draw is None:
            raise HTTPException(status_code=404, detail="Draw not found")

        results = conn.execute(
            """
            SELECT markers.name, markers.short_name, markers.unit,
                   results.value, results.flag,
                   markers.range_low, markers.range_high,
                   markers.optimal_low, markers.optimal_high
            FROM results
            JOIN markers ON results.marker_id = markers.id
            WHERE results.draw_id = ?
            """,
            (draw["id"],)
        ).fetchall()

        return {
            "id": draw["id"],
            "date": draw["date"],
            "source": draw["source"],
            "results": [dict(row) for row in results]
        }


# --- Dashboard ---

@app.get("/dashboard/stats")
def dashboard_stats():
    with get_conn() as conn:
        total_markers = conn.execute("SELECT COUNT(*) FROM markers").fetchone()[0]
        total_draws = conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0]
        last_draw = conn.execute("SELECT date FROM draws ORDER BY date DESC LIMIT 1").fetchone()
        flagged_count = conn.execute(
            "SELECT COUNT(*) FROM results WHERE flag IS NOT NULL"
        ).fetchone()[0]

        return {
            "total_markers": total_markers,
            "total_draws": total_draws,
            "last_draw_date": last_draw["date"] if last_draw else None,
            "flagged_count": flagged_count
        }


# --- Upload: Parse (stateless) ---

@app.post("/draws/parse")
async def parse_draw(file: UploadFile):
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    # Check for duplicate
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM draws WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="This file was already imported")

    # Write to temp file so existing parsers can read it
    suffix = Path(file.filename).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        if suffix == ".csv":
            rows = load_csv(tmp_path)
            return {
                "file_hash": file_hash,
                "source": file.filename,
                "rows": [
                    {
                        "marker": row["marker"],
                        "value": row["value"],
                        "unit": row.get("units", ""),
                        "reference_low": row.get("range_low"),
                        "reference_high": row.get("range_high"),
                        "confidence": None,
                        "raw_text": None,
                        "status": "ok"
                    }
                    for row in rows
                ]
            }
        elif suffix == ".pdf":
            from pdf_parser import parse_pdf
            rows = parse_pdf(tmp_path)
        elif suffix in {".jpg", ".jpeg", ".png", ".heic", ".webp"}:
            from image_parser import parse_image
            rows = parse_image(tmp_path)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

        staged = []
        for row in rows:
            status = "ok"
            if row.get("confidence") is not None and row["confidence"] < 0.85:
                status = "review"
            staged.append({
                "marker": row["marker"],
                "value": row.get("value"),
                "unit": row.get("unit", ""),
                "reference_low": row.get("reference_low"),
                "reference_high": row.get("reference_high"),
                "confidence": row.get("confidence"),
                "raw_text": row.get("raw_text"),
                "status": status
            })

        return {"file_hash": file_hash, "source": file.filename, "rows": staged}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# --- Upload: Confirm (saves to DB) ---

@app.post("/draws/confirm")
def confirm_draw(payload: ConfirmPayload):
    kept = [r for r in payload.rows if r.status != "skip"]

    if not kept:
        raise HTTPException(status_code=400, detail="No rows to save")

    draw = Draw(
        date=payload.date,
        source=payload.source,
        values=[LabResult(marker=r.marker, value=r.value) for r in kept]
    )

    try:
        draw_id = insert_draw(draw, payload.file_hash)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"draw_id": draw_id, "rows_saved": len(kept)}


# --- Analysis (SSE streaming) ---

@app.post("/analyze/{draw_id}")
def analyze_draw(draw_id: int):
    # Load draw + flagged results from DB
    with get_conn() as conn:
        draw = conn.execute("SELECT * FROM draws WHERE id = ?", (draw_id,)).fetchone()
        if draw is None:
            raise HTTPException(status_code=404, detail="Draw not found")

        results = conn.execute(
            """
            SELECT markers.name, results.value, markers.unit,
                   markers.range_low, markers.range_high, results.flag
            FROM results
            JOIN markers ON results.marker_id = markers.id
            WHERE results.draw_id = ?
            """,
            (draw_id,)
        ).fetchall()

    # Build flagged text
    lines = []
    for row in results:
        if row["flag"]:
            direction = "above upper limit" if row["flag"] == "H" else "below lower limit"
            lines.append(f"{row['name']}: {row['value']} {row['unit']} Reference Range: {row['range_low']} - {row['range_high']} {direction}")

    if not lines:
        return {"summary": "All markers are within reference ranges."}

    flagged_text = "\n".join(lines)

    # Load all labs for the tool runner (reuses labs_parser.run_tool)
    all_labs = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT markers.name as marker, results.value,
                   markers.unit as units, markers.range_low, markers.range_high,
                   draws.date
            FROM results
            JOIN markers ON results.marker_id = markers.id
            JOIN draws ON results.draw_id = draws.id
            """
        ).fetchall()
        for r in rows:
            all_labs.append({
                "marker": r["marker"], "value": r["value"],
                "units": r["units"], "range_low": r["range_low"],
                "range_high": r["range_high"], "date": r["date"]
            })

    def event_stream():
        import anthropic

        client = anthropic.Anthropic()
        tools = [
            {"name": "get_optimal_range", "description": "Look up the functional-medicine optimal range for a lab marker.", "input_schema": {"type": "object", "properties": {"marker": {"type": "string"}}, "required": ["marker"]}},
            {"name": "calculate_ratio", "description": "Calculate the ratio between two lab markers.", "input_schema": {"type": "object", "properties": {"numerator_marker": {"type": "string"}, "denominator_marker": {"type": "string"}}, "required": ["numerator_marker", "denominator_marker"]}},
            {"name": "get_historical_values", "description": "Return historical values for a lab marker.", "input_schema": {"type": "object", "properties": {"marker": {"type": "string"}}, "required": ["marker"]}}
        ]
        messages = [{"role": "user", "content": flagged_text}]

        for _ in range(10):
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system="You are a lab result analyst with access to tools for looking up optimal ranges, calculating clinically meaningful ratios, and inspecting historical values. Use these tools proactively. Final summary is 4-6 sentences. No disclaimers. Name specific markers and values.",
                tools=tools,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json_lib.dumps({'token': text})}\n\n"
                response = stream.get_final_message()

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                yield "data: [DONE]\n\n"
                return

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        # Reuse labs_parser.run_tool
                        result = run_tool(block.name, block.input, all_labs)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json_lib.dumps(result)
                        })
                messages.append({"role": "user", "content": tool_results})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
