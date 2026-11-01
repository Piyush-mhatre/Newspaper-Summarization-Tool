"""Can this machine do the work? Used by /health (and later by Docker and monitoring)."""
import pytesseract


def tesseract_version() -> str | None:
    """Version string of the Tesseract program, or None if it is missing or broken."""
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:  # not installed / not on PATH / crashes: all mean "cannot OCR"
        return None
