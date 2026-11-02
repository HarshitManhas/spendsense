"""Untrusted image/PDF decoding runs in a short-lived, time-bounded subprocess."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings

from PIL import Image, ImageOps


def render_upload(content: bytes, max_pages: int):
    with tempfile.TemporaryDirectory(prefix="spendsense-") as temporary:
        root = Path(temporary)
        (root / "input").write_bytes(content)
        result = subprocess.run([sys.executable, "-m", "ai_expense_scanner.render", str(root), str(max_pages)],
                                capture_output=True, timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("Use a valid JPG, PNG, or unencrypted PDF within the page and image limits")
        return [(path.name, path.read_bytes()) for path in sorted(root.glob("page-*"))]


def render(root, max_pages):
    content = (root / "input").read_bytes()
    Image.MAX_IMAGE_PIXELS = 25_000_000
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    if content.startswith(b"%PDF-"):
        import pymupdf
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.is_encrypted or not 1 <= len(document) <= max_pages:
                raise ValueError("Invalid PDF")
            for index, page in enumerate(document):
                zoom = min(1.5, 2200 / max(page.rect.width, page.rect.height))
                if zoom <= 0 or page.rect.width * page.rect.height * zoom**2 > 25_000_000:
                    raise ValueError("Oversized page")
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                pixmap.save(str(root / f"page-{index:02}.png"))
    else:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG"} or image.width * image.height > 25_000_000:
                raise ValueError("Unsupported image")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2200, 3000))
            image.save(root / "page-00.png")
    # A small compressed upload can expand beyond Vercel's response limit.
    for path in root.glob('page-*.png'):
        if path.stat().st_size > 4 * 1024**2:
            with Image.open(path) as image:
                image = image.convert('RGB')
                destination = path.with_suffix('.jpg')
                image.save(destination, quality=85)
                while destination.stat().st_size > 4 * 1024**2:
                    image.thumbnail((max(1, image.width // 2), max(1, image.height // 2)))
                    image.save(destination, quality=85)
            path.unlink()


if __name__ == "__main__":
    render(Path(sys.argv[1]), int(sys.argv[2]))
