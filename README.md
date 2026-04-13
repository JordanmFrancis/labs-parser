# Labs Parser
Labs Parser was built to make reading my labs easier to understand. The program takes a CSV file with lab values and returns out of range markers, how far out of range they are, and whether they are trending up or down. Uses Anthropic API to give a summary of the out of range values. 

## How to use
Clone repo and replace labs.csv with your csv file. The CSV format should be exactly this:
```csv
date,marker,value,units,range_low,range_high
2024-02-13,Insulin,18.2,uIU/mL,2.6,24.9
2024-06-15,Insulin,22.1,uIU/mL,2.6,24.9
2024-02-13,LDL,142,mg/dL,0,100
2024-06-15,LDL,138,mg/dL,0,100
2024-02-13,HbA1c,5.4,%,4.0,5.6
```
Run the program, with `python labs_parser.py` and see your out of range labs sorted for you!

## Example output
```
Flagged Labs (out of range):
Lp(a): 125.0 nmol/L Reference Range: 0.0 - 75.0 66.7% above upper limit. Trend: No Trend
---
HDL: 41.0 mg/dL Reference Range: 45.0 - 100.0 8.9% below lower limit. Trend: Stable
---
Globulin: 2.0 g/dL Reference Range: 2.1 - 3.5 4.8% below lower limit. Trend: Stable
---

--- AI Summary ---
Your Lp(a) is significantly elevated at 125.0 nmol/L, which is 66.7% above the normal range, indicating increased cardiovascular risk. Your HDL cholesterol is slightly low at 41.0 mg/dL, falling 8.9% below the healthy range. Additionally, your globulin level is mildly decreased at 2.0 g/dL, sitting 4.8% below normal limits. Both HDL and globulin levels have remained stable over time, while Lp(a) shows no trend data.

```

## V2
Added Anthropic API for plain english summaries

## V3
Added tool calling, the agent now has access to tools to look up the optimal range of a marker, get the users historical data for a given marker, and do calculations to get marker ratios such as HDL/Total Cholesterol ratio.

## Development in progress
I plan to add new features in the future:
- **PDF/Photo Upload via Anthropic vision for easier use**
- **Multiple CSV upload for more context parsing**
- **UI frontend for non-terminal users**

