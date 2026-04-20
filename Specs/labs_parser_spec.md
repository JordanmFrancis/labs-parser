# Lab Result Parser Spec

Tool that inputs lab results and outputs out of range values and determines trend direction(up/down/stable)

## Inputs

### CSV: 
| Column | Data Format | Valid Input |
|--------|-------------|-------------|
|date|YYYY-MM-DD|Must be in YYYY-MM-DD format, or else rejected with clear error message|
|marker|str|A string of text naming the marker|
|value|float|Must be a float, or else rejected with error message|
|units|str|Must be units/unit, e.g. ng/dL|
|range_low|float|Required for v1|
|range_high|float|Required for v1|

## Sample input CSV

```csv
date,marker,value,units,range_low,range_high
2024-02-13,Insulin,18.2,uIU/mL,2.6,24.9
2024-06-15,Insulin,22.1,uIU/mL,2.6,24.9
2024-02-13,LDL,142,mg/dL,0,100
2024-06-15,LDL,138,mg/dL,0,100
2024-02-13,HbA1c,5.4,%,4.0,5.6
```

## Outputs

Outputs in terminal out of range markers, their values, and how much above reference range they are as a percentage. Outputs trend direction for out of range markers if applicable in % away from upper or lower limit. Must be at least 12% out of range(away from upper limit if higher, lower limit if low). Output is sorted by severity(how out of range it is).

## Example Output

```
LDL: 142 mg/dL on 2024-06-15 — 42.0% above upper limit. Trend: down (from 148 on 2024-02-13).
```

## Constraints/Edge Cases:

- **Missing columns:** All columns are required, output a clear error. 
- **Empty CSV:** Print error and do nothing else. 
- **Markers with only one data point:** Print "No Trend"
- **How is trend calculated?** Trend is calculated using the last 2 points, and a 12% move constitutes a trend
- **Invalid data in a row** (non-numeric value, bad date format, missing required column value):
  print a warning like `⚠️  Row 7: invalid date "02/13/24", skipping` and continue processing other rows.
- **Missing required columns** (e.g., no "date" column at all in the header):
  print a clear error and abort the whole run.
- **Completely empty CSV** (header only or no rows): print "No data in file" and exit cleanly (not an error).

## Out of Scope:
- One-sided reference ranges (<200, >40) — v2
- Unit conversion (mg/dL vs mmol/L) — v2
- PDF input — v4
- Anthropic API / AI summary — v2
- Multiple CSV input — v2
- Patient-specific reference ranges (age/sex adjusted) — out of scope entirely
