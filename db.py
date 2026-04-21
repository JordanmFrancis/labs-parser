import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "labs.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS markers (
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

CREATE TABLE IF NOT EXISTS draws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,           -- ISO format YYYY-MM-DD
    source TEXT,                  -- "Quest", "LabCorp", "Manual CSV"
    file_hash TEXT UNIQUE,        -- prevents re-importing the same file
    imported_at TEXT NOT NULL     -- ISO timestamp
);

CREATE TABLE IF NOT EXISTS results (
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

CREATE INDEX IF NOT EXISTS idx_results_marker ON results(marker_id);
CREATE INDEX IF NOT EXISTS idx_results_draw ON results(draw_id);
"""

@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)


def get_marker_id(conn, name: str) -> int | None:
    """Look up a marker by name. Returns the id or None."""
    row = conn.execute(
        "SELECT id FROM markers WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return row["id"]
    return None


def insert_draw(draw, file_hash: str) -> int:
    """Insert a draw + all its results. Returns draw_id."""
    with get_conn() as conn:
        # Step 1: insert one row into the draws table
        conn.execute(
            "INSERT INTO draws (date, source, file_hash, imported_at) VALUES (?, ?, ?, ?)",
            (draw.date.isoformat(), draw.source, file_hash, datetime.now().isoformat())
        )
        # last_insert_rowid() gets the auto-generated id from the row we just inserted
        draw_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Step 2: insert one row into results for each lab value
        for result in draw.values:
            marker_id = get_marker_id(conn, result.marker)
            if marker_id is None:
                print(f"Warning: unknown marker '{result.marker}', skipping")
                continue

            # Compute flag by comparing value to the marker's ranges
            marker = conn.execute(
                "SELECT range_low, range_high FROM markers WHERE id = ?", (marker_id,)
            ).fetchone()
            flag = None
            if marker["range_high"] and result.value > marker["range_high"]:
                flag = "H"
            elif marker["range_low"] and result.value < marker["range_low"]:
                flag = "L"

            conn.execute(
                "INSERT INTO results (draw_id, marker_id, value, flag, confidence, raw_text) VALUES (?, ?, ?, ?, ?, ?)",
                (draw_id, marker_id, result.value, flag, result.confidence, result.raw_text)
            )

        return draw_id


def get_marker_history(marker_name: str) -> list[dict]:
    """Get all values for a marker across all draws, oldest first.
    
    JOINs three tables together:
      results → draws  (to get the date)
      results → markers (to match by name)
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT draws.date, results.value
            FROM results
            JOIN draws ON results.draw_id = draws.id
            JOIN markers ON results.marker_id = markers.id
            WHERE markers.name = ?
            ORDER BY draws.date ASC
            """,
            (marker_name,)
        ).fetchall()
        # Convert sqlite3.Row objects to plain dicts
        return [{"date": row["date"], "value": row["value"]} for row in rows]


def get_latest_draw() -> dict | None:
    """Get the most recent draw and all its results.
    
    Two queries:
      1. Find the draw with the latest date
      2. Get all results for that draw (joined to markers for the names)
    """
    with get_conn() as conn:
        # Step 1: get the most recent draw
        draw = conn.execute(
            "SELECT * FROM draws ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if draw is None:
            return None

        # Step 2: get all results for that draw, with marker names
        rows = conn.execute(
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
            "results": [
                {
                    "marker": row["name"],
                    "short_name": row["short_name"],
                    "unit": row["unit"],
                    "value": row["value"],
                    "flag": row["flag"],
                    "range_low": row["range_low"],
                    "range_high": row["range_high"],
                    "optimal_low": row["optimal_low"],
                    "optimal_high": row["optimal_high"],
                }
                for row in rows
            ],
        }