import base64
import anthropic
import json

# Read the image file and encode it in base64
def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        raw_bytes = f.read()
    image = base64.b64encode(raw_bytes).decode("utf-8")
    return image

# API call to send the image to the model
def build_content(b64_image: str, prompt: str, media_type: str = "image/jpeg") -> list:
    image_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,   # or image/png, image/webp
            "data": b64_image
        }
    }
    text_block = {"type": "text", "text": prompt}

    return [image_block, text_block]


def strip_code_fences(text: str) -> str:
    # handle ```json ... ``` and ``` ... ```
    text = text.strip()
    if text.startswith("```"):
        # split off first line (```json or ```), drop last line (```)
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return text.strip()


# High level function to analyze the image with the given prompt
def analyze_image(image_path: str, prompt: str, media_type: str = "image/jpeg") -> list[dict]:
    b64 = encode_image(image_path)
    content = build_content(b64, prompt, media_type)

    client = anthropic.Client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system = """You are a lab result extraction assistant. Given an image of medical lab results, extract every numeric marker into JSON.
            Return a JSON array. Each object must have exactly these keys:
            - marker (str): the marker name exactly as printed
            - value (number or null): numeric value, not a string. null if unreadable.
            - unit (str or null): unit as printed (e.g. "mg/dL", "nmol/L")
            - reference_low (number or null): lower bound of the reference range. null if one-sided.
            - reference_high (number or null): upper bound. null if one-sided.
            - flag (str or null): "H" for high, "L" for low, null for in-range or unflagged. Do not use "normal".

            Rules:
            - Do not invent values. If you cannot read a field, use null.
            - Skip non-numeric rows (section headers, comments, footnotes).
            - For "<100", set reference_low=null and reference_high=100. For ">40", set reference_low=40 and reference_high=null.
            - Return the JSON array only. No prose, no markdown fences.""",
        messages=[{"role": "user", "content": content}]
    )
    text = response.content[0].text
    text = strip_code_fences(text)
    rows = json.loads(text)
    return rows




def main():
    image_path = "test.jpeg"
    prompt = "Extract the lab markers from this image."
    rows = analyze_image(image_path, prompt)
    print(rows)

if __name__ == "__main__":
    main()