"""
Optional OCR engine: turn a Derby Task Log screenshot into raw text.

The actual image→text step needs Pillow plus pytesseract and the Tesseract
binary. Those are heavier and platform-dependent, so they are imported lazily
and treated as entirely optional: if they're missing, the screenshot importer
simply falls back to letting the user paste text (e.g. copied via their phone's
built-in "copy text from image" / Google Lens). Nothing here is required for
the rest of the app to run.

Keeping this isolated also means the pure parsing/matching logic in
derby_ocr.py stays testable without any of these dependencies installed.
"""

import os


def ocr_available() -> tuple:
    """Return (available: bool, reason: str).

    reason is "" when available, otherwise a short human-readable explanation
    of what's missing — shown in the import dialog so the user knows whether to
    install Tesseract or just paste text instead.
    """
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False, "Pillow (PIL) is not installed."
    try:
        import pytesseract
    except ImportError:
        return False, ("pytesseract is not installed "
                       "(pip install pytesseract).")
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return False, ("The Tesseract OCR engine isn't installed or isn't on "
                       "PATH. Install it from "
                       "https://github.com/tesseract-ocr/tesseract, "
                       "or paste the text manually.")
    return True, ""


def _preprocess(image):
    """Light preprocessing that helps Tesseract read the derby table:
    convert to greyscale, upscale small screenshots, and boost contrast.
    Returns a new PIL image; the original is left untouched."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(image).convert("L")

    # upscale narrow phone screenshots so the small table text is legible
    min_width = 1000
    if img.width < min_width:
        scale = min_width / img.width
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.LANCZOS,
        )

    img = ImageOps.autocontrast(img)
    return img


def image_to_text(path: str, lang: str = "eng") -> str:
    """OCR the image at ``path`` and return the recognized text.

    Raises RuntimeError with a clear message if OCR isn't available or the
    file can't be read, so callers can surface it and offer the paste fallback.
    """
    available, reason = ocr_available()
    if not available:
        raise RuntimeError(reason or "OCR is not available.")
    if not os.path.exists(path):
        raise RuntimeError(f"File not found: {path}")

    from PIL import Image
    import pytesseract

    try:
        with Image.open(path) as raw:
            processed = _preprocess(raw)
    except Exception as exc:  # unreadable / unsupported image
        raise RuntimeError(f"Could not open image: {exc}") from exc

    # --psm 6: assume a uniform block of text (the table), which suits the log
    config = "--psm 6"
    return pytesseract.image_to_string(processed, lang=lang, config=config)
