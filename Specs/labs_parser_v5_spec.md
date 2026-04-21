---
date: 2026-04-13
type: deliverable
tags: [dev, claude]
project: learning-python
---

# Lab Parser v5 Spec — SQLite + History Database

Related: [[labs_parser_roadmap]] · [[labs_parser_v4_spec]]

By v4 I can ingest CSV and PDF. But every run is fresh — I lose everything when the script ends. v5 makes the parser remember. Every lab value gets written to a SQLite database. I can ingest a new lab draw and see it in context with everything before it. v3's `find_trends` only sees one CSV at a time; v5's trend logic sees my entire history.

## What I Want to Learn

- SQLite (file-based SQL database, no server needed)
- Schema design — what tables, what columns, what relationships
- CRUD: Create, Read, Update, Delete with SQL
- Pydantic models — typed Python objects that validate themselves
- Transactions and uniqueness constraints (so I can't double-insert the same lab draw)
- The `with` statement and context managers (database connections)

## Why SQLite First, Not Postgres

SQLite is one file. No server. Ships with Python (`import sqlite3`). Perfect for learning. When I deploy in v9 and need real Postgres, the schema migrates cleanly.

## Schema

Three tables. One for "markers" (canonical definitions with ranges and grouping), one for "draws" (a single dated lab session), and one for "results" (each marker measured in that draw). The markers table is what the frontend needs to render KPI cards, sparkline groups, flagged lists, and range cards — without it, there's no place to store optimal ranges or marker groups.

```sql
CREATE TABLE markers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,     -- canonical name: "LDL-C", "HDL", "HbA1c"
    short_name TEXT,               -- display name: "LDL", "HDL", "HbA1c"
    unit TEXT,                     -- "mg/dL", "%", "nmol/L"
    range_low REAL,                -- lab reference range low bound
    range_high REAL,               -- lab reference range high bound
    optimal_low REAL,              -- functional medicine optimal low
    optimal_high REAL,             -- functional medicine optimal high
    group_name TEXT                -- "lipids", "metabolic", "inflammation", "thyroid", etc.
);

CREATE TABLE draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,           -- ISO format YYYY-MM-DD
    source TEXT,                  -- "Quest", "LabCorp", "Manual CSV"
    file_hash TEXT UNIQUE,        -- prevents re-importing the same file
    imported_at TEXT NOT NULL     -- ISO timestamp
);

CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_id INTEGER NOT NULL,
    marker_id INTEGER NOT NULL,
    value REAL NOT NULL,
    flag TEXT,                    -- "H", "L", or NULL (computed at insert from marker ranges)
    confidence REAL,              -- vision extraction confidence 0.0–1.0 (NULL for CSV)
    raw_text TEXT,                -- original OCR text before parsing (e.g., "9.l")
    FOREIGN KEY (draw_id) REFERENCES draws(id),
    FOREIGN KEY (marker_id) REFERENCES markers(id)
);

CREATE INDEX idx_results_marker ON results(marker_id);
CREATE INDEX idx_results_draw ON results(draw_id);
```

Why three tables instead of two:
- **markers** holds the canonical definitions — lab ref ranges, optimal ranges, groups, display names. The frontend's Dashboard, Marker Detail, and Upload screens all need this data. Without it, optimal range lookups would require a Haiku API call every time (expensive and slow). Seeded once from a JSON file or hardcoded dict, updated when new markers are discovered.
- **results** references `marker_id` instead of storing a raw marker string. This solves the canonicalization problem: "LDL Cholesterol" and "LDL-C" both map to the same marker row. Matching happens at insert time.
- **confidence** and **raw_text** support the Upload screen's ambiguity resolution UI. When vision extraction isn't sure about a value (confidence < 0.85), the frontend shows the raw OCR text and lets the user correct it before saving.

`file_hash` is a SHA-256 of the source file. If I import the same CSV twice, the second import fails with a unique constraint error. I want that — no silent duplicates.

## New Module: `db.py`

All database access lives here. The rest of the program never touches SQL directly.

```python
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("labs.db")

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row     # return dicts, not tuples
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Run schema if tables don't exist yet."""
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)
```

## Pydantic Models

Replace raw dicts with typed objects. Validation happens at the boundary (when data comes in from CSV/PDF). After that, everything is type-safe.

```python
from pydantic import BaseModel
from datetime import date

class MarkerDef(BaseModel):
    """Canonical marker definition — lives in the markers table."""
    name: str                          # "LDL-C"
    short_name: str | None = None      # "LDL"
    unit: str | None = None            # "mg/dL"
    range_low: float | None = None     # lab reference low
    range_high: float | None = None    # lab reference high
    optimal_low: float | None = None   # functional medicine optimal low
    optimal_high: float | None = None  # functional medicine optimal high
    group_name: str | None = None      # "lipids", "metabolic", etc.

class LabResult(BaseModel):
    """A single measured value from a draw."""
    marker: str
    value: float
    flag: str | None = None            # "H", "L", or None
    confidence: float | None = None    # vision extraction confidence 0.0–1.0
    raw_text: str | None = None        # original OCR text before parsing

class Draw(BaseModel):
    date: date
    source: str
    values: list[LabResult]
```

`MarkerDef` is the model for the markers reference table. Seeded from a JSON file or dict on first run. `LabResult` replaces the old `LabValue` — it drops `units`/`ref_low`/`ref_high` because those now live on the marker definition, not on each individual result. It adds `confidence` and `raw_text` to support the frontend's ambiguity resolution UI (flagging rows where vision extraction confidence < 0.85).

Now if a parser hands me a malformed value (string instead of float), Pydantic raises `ValidationError` at the boundary instead of failing 50 lines later in `flag_out_of_range`.

## CRUD Functions

```python
# --- Marker definitions ---
def get_all_markers() -> list[dict]:
    """Return all marker definitions (for frontend marker list, KPI cards, groups)."""

def get_marker_by_name(name: str) -> dict | None:
    """Look up a single marker definition by canonical name."""

def upsert_marker(marker: MarkerDef) -> int:
    """Insert or update a marker definition. Returns marker_id."""

def resolve_marker_name(raw_name: str) -> int | None:
    """Canonicalize a raw marker name (from OCR/CSV) to a marker_id. Returns None if no match."""

# --- Draws ---
def insert_draw(draw: Draw, file_hash: str) -> int:
    """Insert a draw + all its results. Returns draw_id. Raises on duplicate file_hash."""

def get_latest_draw() -> dict:
    """Return the most recent draw + its results."""

def get_draws_in_range(start: date, end: date) -> list[dict]:
    """All draws between two dates."""

def delete_draw(draw_id: int) -> None:
    """Hard delete a draw and cascade to its results."""

# --- Results / History ---
def get_marker_history(marker: str) -> list[dict]:
    """Return every historical value for a marker, oldest first. Shape: [{date, value}]."""

def get_flagged_markers() -> list[dict]:
    """Return markers from the latest draw that are out of range, sorted by severity."""

def get_dashboard_stats() -> dict:
    """Return aggregated stats: total_markers, flagged_count, last_draw_date, draws_count."""
```

## v3 Tools Get Rewritten

The tool use loop from v3 stays. But the tools now read from the database instead of the in-memory CSV.

- `get_historical_values(marker)` → SQL query, not list comprehension over `all_labs`
- `calculate_ratio` → SQL query for most recent value of each marker
- `lookup_optimal_range` → unchanged (Haiku call)

This is a big simplification. The tools no longer need `all_labs` passed in — they just hit the DB. So `summarize_labs` no longer needs to thread `all_labs` through everything.

## CLI Changes

```bash
# Import a new draw
python labs_parser.py import labs/2026-04-12.csv

# Show summary of latest draw with v3 tool use
python labs_parser.py analyze --latest

# Show full history of a marker
python labs_parser.py history "LDL"

# List all draws on file
python labs_parser.py list
```

This means I need real CLI argument parsing. Use `argparse` (stdlib) — don't pull in `click` or `typer` yet, that's another concept I haven't learned.

## Marker Seeding

The `markers` table needs initial data. On first run, seed from a hardcoded dict or JSON file with the ~18 markers I track (matching the frontend prototype's `MARKERS` array). Structure:

```python
SEED_MARKERS = [
    {"name": "LDL-C", "short_name": "LDL", "unit": "mg/dL", "range_low": 0, "range_high": 100, "optimal_low": 70, "optimal_high": 100, "group_name": "lipids"},
    {"name": "HDL", "short_name": "HDL", "unit": "mg/dL", "range_low": 45, "range_high": 100, "optimal_low": 55, "optimal_high": 80, "group_name": "lipids"},
    # ... etc for all tracked markers
]
```

New markers discovered during parsing (e.g., "Vitamin D 25-OH" shows up in a PDF but isn't in the seed) get flagged as `status: 'review'` in the upload flow — the user decides whether to create a new marker entry or skip it.

## Edge Cases

| Case | Behavior |
|------|----------|
| Re-import same file | UNIQUE constraint fails on `file_hash`, print "Already imported on YYYY-MM-DD" |
| Marker name varies between draws (e.g., "LDL" vs "LDL Cholesterol") | `resolve_marker_name()` does case-insensitive fuzzy match against the `markers` table. If no match found, flag the row for review (frontend shows "new marker — map or create?"). Real semantic matching deferred to v11. |
| Unknown marker in parsed results | Return it with `marker_id=None` and `status='review'` — frontend Upload screen shows ambiguity banner |
| Database file doesn't exist | `init_db()` creates it + seeds markers on first run |
| Database file corrupted | Catch `sqlite3.DatabaseError`, print recovery instructions |
| Pydantic validation fails | Print which row failed and skip it, continue with the rest |
| Date parsing fails | Skip the row, log it, continue |

## Files to Add

- `db.py` — schema, connection manager, CRUD functions, marker seeding
- `models.py` — Pydantic models (`MarkerDef`, `LabResult`, `Draw`)
- `seed_markers.json` — initial marker definitions (name, short_name, unit, ranges, optimal, group)
- `cli.py` — argparse-based CLI dispatcher
- `requirements.txt` — add `pydantic>=2.0`
- `.gitignore` — add `labs.db` (don't commit my health data)

## What's New vs v4

| Concept | v4 | v5 |
|---------|----|----|
| Storage | none (one CSV/PDF per run) | SQLite database, persistent |
| Data validation | trust the parser | Pydantic at the boundary |
| Trend logic | last 2 points in current file | full history across all draws |
| CLI | run the script | `import` / `analyze` / `history` / `list` subcommands |
| Architecture | functions over dicts | typed models + repository pattern |

## Out of Scope for v5

- Postgres (v9, when I deploy)
- Multi-user data isolation (single-user only)
- Soft deletes (hard delete is fine for now)
- Migrations framework (Alembic) — schema is small enough that a single `init_db` works
- Backup/export tools (just copy `labs.db`)
