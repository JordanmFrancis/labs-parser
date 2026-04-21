from pydantic import BaseModel
from datetime import date

class MarkerDef(BaseModel):
    name: str
    short_name: str | None = None
    unit: str | None = None
    range_low: float | None = None
    range_high: float | None = None
    optimal_low: float | None = None
    optimal_high: float | None = None  
    group_name: str | None = None

class LabResult(BaseModel):
    marker: str
    value: float
    flag: str | None = None
    confidence: float | None = None
    raw_text: str | None = None

class Draw(BaseModel):
    date: date
    source: str
    values: list[LabResult]

class LabValueExtraction(BaseModel):
    marker: str
    value: float | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    flag: str | None = None
    confidence: float | None = None    # 0.0–1.0: how sure Claude is about this row
    raw_text: str | None = None        # exact text from the image before parsing

class ExtractedRows(BaseModel):
    rows: list[LabValueExtraction]

class OptimalRange(BaseModel):
    marker: str
    optimal_low: float
    optimal_high: float
    units: str
    reasoning: str