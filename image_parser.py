import tempfile
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from vision import analyze_image
register_heif_opener()

def load_image(image_path: str) -> Image.Image:
    return Image.open(image_path)


def fix_rotation(img: Image.Image) -> Image.Image:
    return ImageOps.exif_transpose(img)


def resize_image(img: Image.Image, max_size: int = 2000) -> Image.Image:
    if max(img.size) > max_size:
        img.thumbnail((max_size, max_size))
    return img


def parse_image(image_path: str) -> list[dict]:
    img = load_image(image_path)
    img = fix_rotation(img)
    img = resize_image(img)
    with tempfile.NamedTemporaryFile(suffix=".jpeg", delete=True) as tmp:
        img.save(tmp.name, format="JPEG")
        rows = analyze_image(tmp.name, "Extract the lab markers from this image.")
    return rows

def main():
    rows = parse_image("test.jpeg")
    print(rows)

if __name__ == "__main__":
    main()