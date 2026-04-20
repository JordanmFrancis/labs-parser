---
date: 2026-04-13
type: deliverable
tags: [dev, claude]
project: learning-python
---

# Lab Parser v4 Spec — PDF + Image Parsing + Vision API

Related: [[labs_parser_roadmap]] · [[labs_parser_v3_spec]]

In v3 my input is a CSV I had to type up by hand. That sucks. Real labs come at me three ways: PDFs from Quest/LabCorp/Boston Heart, screenshots from patient portals on my phone, and photos I take of paper printouts at the doctor's office. v4 makes the parser eat all three.

## What I Want to Learn

- Binary file I/O (PDFs and images are not text files)
- A PDF parsing library (`pypdf` or `pdfplumber`) and how they differ
- Regex for pulling structured data out of messy text
- The vision API — sending images directly to Claude for structured extraction
- HEIC handling (iPhone screenshots are HEIC by default, not PNG)
- A "fallback chain" pattern: try cheap method first, fall back to expensive method only when needed
- Dispatch by file type — one entry point, three input formats, same output shape

## Architecture: Three Input Paths, One Output Shape

Three file types, dispatched by extension. All paths return the same `list[dict]` shape that v1's CSV loader returns. Drop-in replacement everywhere.

```
.csv                    → load_csv()                              [v1, unchanged]
.pdf                    → parse_pdf()  → tier1: pdfplumber+regex
                                       → tier2: vision fallback
.png/.jpg/.jpeg/.heic   → parse_image() → vision API directly
```

Images skip the two-tier dance because there's no cheap text-extraction path — it's a picture, you have to look at it. Goes straight to the vision API.

### Why This Matters

PDFs from Quest/LabCorp are usually structured enough that `pdfplumber` + regex wins. Cheap, deterministic, no API call. Phone screenshots and photos have no text layer at all — vision API is the only option, but it's also the right tool for the job (Sonnet's vision is excellent at lab tables).

## New Module: `pdf_parser.py`

Keep it separate from `labs_parser.py`. The main script just imports `parse_pdf()` and gets back the same list of dicts the CSV loader returns.

```python
def parse_pdf(path: str) -> list[dict]:
    text_rows = parse_with_pdfplumber(path)
    if len(text_rows) >= MIN_EXPECTED_ROWS:
        return text_rows
    print("Tier 1 yielded too few rows. Falling back to vision API.")
    return parse_with_vision(path)
```

`MIN_EXPECTED_ROWS = 5` — if I got fewer than 5 lab values out of the PDF, something's wrong, fall back.

## Tier 1: `pdfplumber` + Regex

```python
import pdfplumber
import re

def parse_with_pdfplumber(path: str) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            rows.extend(extract_rows_from_text(text))
    return rows
```

The regex is the hard part. Most lab reports have lines like:

```
LDL Cholesterol         145    mg/dL    0-99      H
```

Pattern that handles most of it:

```python
ROW_PATTERN = re.compile(
    r"^(?P<marker>[A-Za-z][A-Za-z0-9 ,/\-\(\)]+?)\s+"
    r"(?P<value>[\d.]+)\s+"
    r"(?P<units>[a-zA-Z%/]+)\s+"
    r"(?P<low>[\d.]+)\s*-\s*(?P<high>[\d.]+)"
)
```

I'll iterate, find matches per line, and return a list of dicts. Lines that don't match get skipped silently (header/footer/legal text).

## Tier 2: Vision API Fallback

Convert each PDF page to an image, base64 encode, send to Claude with a prompt asking for structured JSON.

```python
import base64
from pdf2image import convert_from_path

def parse_with_vision(path: str) -> list[dict]:
    images = convert_from_path(path, dpi=200)
    all_rows = []
    for i, img in enumerate(images):
        b64 = image_to_base64(img)
        page_rows = extract_rows_with_claude(b64)
        all_rows.extend(page_rows)
    return all_rows
```

The Claude call:

```python
def extract_rows_with_claude(b64_image: str) -> list[dict]:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64_image}},
                {"type": "text", "text": EXTRACTION_PROMPT}
            ]
        }]
    )
    raw = response.content[0].text
    return json.loads(strip_code_fences(raw))
```

`EXTRACTION_PROMPT` asks for a JSON array with marker, value, units, ref_low, ref_high, date. Same JSON-fences trap from v3 — same fix. (v6 will replace this hack with `tool_choice` structured outputs.)

## Image Parsing — `parse_image()`

Screenshots from patient portals, photos of paper printouts, AirDropped iPhone images. The vision API handles all of them — the only work is normalizing the input format and base64-encoding it.

```python
from PIL import Image
import pillow_heif      # registers HEIC support with Pillow
import io

pillow_heif.register_heif_opener()

def parse_image(path: str) -> list[dict]:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")     # vision API wants RGB

    # Resize if huge — Sonnet caps at ~8000px on the long edge,
    # and bigger images cost more tokens for no extra accuracy.
    MAX_DIM = 2000
    if max(img.size) > MAX_DIM:
        img.thumbnail((MAX_DIM, MAX_DIM))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    return extract_rows_with_claude(b64)
```

`pillow_heif` is the trick for iPhone screenshots — they default to HEIC, which Pillow doesn't read natively. One `register_heif_opener()` call and it Just Works.

The same `extract_rows_with_claude()` function from Tier 2 gets reused. That's the architectural win — once you have the vision call working, every image-based input path is just "get bytes → encode → call".

### Multi-Image Inputs

Sometimes a lab report is 4 screenshots stitched together in my Photos app. Two ways to handle:

1. **Pass them all in one API call** as a list of image blocks. Sonnet sees them as one document, cross-references across pages, returns a unified row list. Cleaner output.
2. **Loop and call once per image.** Simpler code, easier to debug, but Sonnet might duplicate header rows or miss cross-page references.

v4 uses option 1 when given multiple image paths. The CLI accepts globs (`labs/*.png`) for this.

```python
def parse_images(paths: list[str]) -> list[dict]:
    image_blocks = []
    for path in paths:
        b64 = encode_image(path)
        image_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": b64}
        })
    image_blocks.append({"type": "text", "text": EXTRACTION_PROMPT})
    # one API call, all images in one message
    return call_claude_vision(image_blocks)
```

## Edge Cases

| Case | Behavior |
|------|----------|
| Scanned PDF, no extractable text | Tier 1 returns 0 rows, vision fallback fires |
| Multi-page PDF | Loop pages, accumulate rows |
| Date is in the header, not per-row | Vision prompt says "infer date from page header, apply to all rows" |
| Vision returns non-JSON | Same `strip_code_fences` + try/except as v3 |
| `pdf2image` requires `poppler` system dep | README documents `brew install poppler` step |
| Encrypted PDF | Catch the exception, print "encrypted PDF not supported, decrypt first" |
| Mixed CSV + PDF + image input in one run | `main()` checks file extension and dispatches to the right loader |
| iPhone HEIC screenshot | `pillow_heif.register_heif_opener()` at module import — no special-case needed downstream |
| Blurry / low-quality photo | Vision returns rows but with low confidence; prompt asks Claude to flag uncertain values with `confidence: "low"` field |
| Image is rotated (landscape phone shot of portrait page) | Pillow auto-rotation via EXIF orientation tag (`ImageOps.exif_transpose(img)`) before encoding |
| Image too large (>20MB) | Resize to MAX_DIM=2000px before encoding; reject only if still >20MB after |
| Multiple screenshots of same report | CLI accepts globs; all images sent in one API call as a multi-image message |

## CLI Update

`main()` accepts one or more file paths and globs. Sniffs the extension on each:

```python
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp"}

def load_input(paths: list[str]) -> list[dict]:
    # Group images so they can go in a single multi-image API call
    images, others = [], []
    for path in paths:
        ext = Path(path).suffix.lower()
        if ext in IMAGE_EXTS:
            images.append(path)
        else:
            others.append((ext, path))

    rows = []
    if images:
        rows.extend(parse_images(images))
    for ext, path in others:
        if ext == ".csv":
            rows.extend(load_csv(path))
        elif ext == ".pdf":
            rows.extend(parse_pdf(path))
        else:
            raise ValueError(f"Unsupported file type: {path}")
    return rows
```

CLI usage:

```bash
python labs_parser.py labs/2026-04.csv                          # CSV
python labs_parser.py labs/quest-2026-04-12.pdf                 # PDF
python labs_parser.py labs/portal-screenshot.png                # single image
python labs_parser.py labs/page1.heic labs/page2.heic           # multi-image (one API call)
python labs_parser.py "labs/*.png"                              # glob expanded by shell
python labs_parser.py labs/                                     # whole directory
```

Bonus: directory mode loops all supported files inside, merges, dedupes by (marker, date, value).

## Files to Add

- `pdf_parser.py` — PDF tier 1 + tier 2 logic
- `image_parser.py` — image normalization (HEIC, EXIF rotation, resize) + multi-image API call
- `vision.py` — shared `extract_rows_with_claude()` used by both parsers
- `requirements.txt` — `pdfplumber`, `pdf2image`, `pillow`, `pillow-heif`, `anthropic`, `python-dotenv`
- README — add PDF + image parsing sections + `brew install poppler` instructions

## What's New vs v3

| Concept | v3 | v4 |
|---------|----|----|
| File I/O | text (CSV) | binary (PDF + images, including HEIC) |
| API call types | text-only | text + single image + multi-image messages |
| Parsing | `csv.DictReader` | `pdfplumber` + regex + vision (PDFs) + vision-only (images) |
| Architecture | one input format | dispatch by file type, fallback chain inside PDF path |
| Input variety | typed-up CSV | whatever the doctor's office gives me — PDF, screenshot, or photo |

## Out of Scope for v4

- OCR for old scanned faxes (Tesseract) — vision API handles it
- Auto-detecting which lab the PDF came from (Quest vs LabCorp templates)
- Email-in-a-PDF flow (v7+)
- Storing the parsed file in a database (v5)
- Live phone capture (open camera in browser → upload) — that's v8 frontend territory
- Video / animated input — vision API supports it but not relevant here
