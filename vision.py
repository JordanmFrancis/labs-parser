import base64
import anthropic
from models import ExtractedRows

def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        raw_bytes = f.read()
    return base64.b64encode(raw_bytes).decode("utf-8")


def build_content(b64_image: str, prompt: str, media_type: str = "image/jpeg") -> list:
    image_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64_image
        }
    }
    text_block = {"type": "text", "text": prompt}
    return [image_block, text_block]


def analyze_image(image_path: str, prompt: str, media_type: str = "image/jpeg") -> list[dict]:
    b64 = encode_image(image_path)
    content = build_content(b64, prompt, media_type)

    client = anthropic.Client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""You are a lab result extraction assistant. Given an image of medical lab results, extract every numeric marker.

Rules:
- Do not invent values. If you cannot read a field, use null.
- Skip non-numeric rows (section headers, comments, footnotes).
- For "<100", set reference_low=null and reference_high=100.
- For ">40", set reference_low=40 and reference_high=null.
- flag: "H" for high, "L" for low, null for in-range. Do not use "normal".
- confidence: 0.0 to 1.0 — how certain you are of the extracted value. Use < 0.85 for blurry text, ambiguous characters (l vs 1, O vs 0), or partially obscured values.
- raw_text: the exact text as printed on the document before any interpretation (e.g., "9.l", "< 100", "H 142").""",
        tools=[{
            "name": "return_extracted_rows",
            "description": "Return all extracted lab values from the image",
            "input_schema": ExtractedRows.model_json_schema()
        }],
        tool_choice={"type": "tool", "name": "return_extracted_rows"},
        messages=[{"role": "user", "content": content}]
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    extracted = ExtractedRows(**tool_block.input)
    return [row.model_dump() for row in extracted.rows]