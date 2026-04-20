import re
import pdfplumber
from vision import analyze_image
import tempfile
from pdf2image import convert_from_path

def extract_with_pdfplumber(pdf_path: str) -> list[list]:
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                rows.extend(table[1:])  # skip header row
    return rows


def extract_with_vision(pdf_path: str) -> list[dict]:
    images = convert_from_path(pdf_path)
    all_rows = []
    for i, img in enumerate(images):
        print(f"Processing page {i+1}/{len(images)}...")
        with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=True) as tmp:
            img.save(tmp.name, format="JPEG")
            rows = analyze_image(tmp.name, "Extract the lab markers from this image.")
            all_rows.extend(rows)
    return all_rows


def deduplicate_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for row in rows:
        key = (row["marker"], row["value"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def parse_pdf(pdf_path: str) -> list[dict]:
    rows = extract_with_pdfplumber(pdf_path)
    if len(rows) < 5:
        rows = extract_with_vision(pdf_path)
    rows = deduplicate_rows(rows)
    return rows


def main():
    rows = parse_pdf("test.pdf")
    print(rows)
    print(len(rows))

if __name__ == "__main__":
    main()