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

Two tables. One for "draws" (a single dated lab session) and one for "values" (each marker measured in that draw). Normalized so I'm not duplicating dates everywhere.

```sql
CREATE TABLE draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,           -- ISO format YYYY-MM-DD
    source TEXT,                  -- "Quest", "LabCorp", "Manual CSV"
    file_hash TEXT UNIQUE,        -- prevents re-importing the same file
    imported_at TEXT NOT NULL     -- ISO timestamp
);

CREATE TABLE lab_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draw_id INTEGER NOT NULL,
    marker TEXT NOT NULL,
    value REAL NOT NULL,
    units TEXT,
    ref_low REAL,
    ref_high REAL,
    flag TEXT,                    -- "H", "L", or NULL
    FOREIGN KEY (draw_id) REFERENCES draws(id)
);

CREATE INDEX idx_lab_values_marker ON lab_values(marker);
CREATE INDEX idx_lab_values_draw ON lab_values(draw_id);
```

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

class LabValue(BaseModel):
    marker: str
    value: float
    units: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    flag: str | None = None

class Draw(BaseModel):
    date: date
    source: str
    values: list[LabValue]
```

Now if a parser hands me a malformed value (string instead of float), Pydantic raises `ValidationError` at the boundary instead of failing 50 lines later in `flag_out_of_range`.

## CRUD Functions

```python
def insert_draw(draw: Draw, file_hash: str) -> int:
    """Insert a draw + all its values. Returns draw_id. Raises on duplicate file_hash."""

def get_all_values_for_marker(marker: str) -> list[dict]:
    """Return every historical value for a marker, oldest first."""

def get_latest_draw() -> dict:
    """Return the most recent draw + its values."""

def get_draws_in_range(start: date, end: date) -> list[dict]:
    """All draws between two dates."""

def delete_draw(draw_id: int) -> None:
    """Hard delete a draw and cascade to its values."""
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

## Edge Cases

| Case | Behavior |
|------|----------|
| Re-import same file | UNIQUE constraint fails on `file_hash`, print "Already imported on YYYY-MM-DD" |
| Marker name varies between draws (e.g., "LDL" vs "LDL Cholesterol") | Add a `markers` lookup table OR canonicalize at insert time. v5 uses canonicalization function: lowercase + strip whitespace. Real fix is v11 (semantic match). |
| Database file doesn't exist | `init_db()` creates it on first run |
| Database file corrupted | Catch `sqlite3.DatabaseError`, print recovery instructions |
| Pydantic validation fails | Print which row failed and skip it, continue with the rest |
| Date parsing fails | Skip the row, log it, continue |

## Files to Add

- `db.py` — schema, connection manager, CRUD functions
- `models.py` — Pydantic models
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
