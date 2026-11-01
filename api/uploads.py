"""Safe handling of an uploaded file. Pure helpers: no routes, no pipeline, easy to test."""
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager

from starlette.datastructures import UploadFile

from api.errors import ApiError

CHUNK = 1024 * 1024  # copy the upload in 1 MB pieces; never load a whole PDF into memory


def parse_pages(raw: str | None) -> list[int] | None:
    """'1,3' -> [1, 3];  empty/missing -> None (meaning: all pages)."""
    if not raw:
        return None
    try:
        return [int(p) for p in raw.split(",")]
    except ValueError:
        raise ApiError(400, "'pages' must be comma-separated integers") from None


def require_pdf(upload: UploadFile | None) -> UploadFile:
    """The upload must exist and start with the PDF magic bytes (never trust the file name)."""
    if upload is None or not upload.filename:
        raise ApiError(400, "No file uploaded (expected form field 'pdf')")
    if upload.file.read(5) != b"%PDF-":
        raise ApiError(400, "File is not a valid PDF")
    upload.file.seek(0)
    return upload


@contextmanager
def temp_pdf(upload: UploadFile, max_bytes: int) -> Iterator[str]:
    """Save the upload to a unique temp file, yield its path, ALWAYS delete it afterwards.

    Unique per request: two simultaneous uploads can never overwrite each other.
    The size is checked while copying, so a client that lied about its size is still stopped.
    """
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        copied = 0
        with os.fdopen(fd, "wb") as out:
            while chunk := upload.file.read(CHUNK):
                copied += len(chunk)
                if copied > max_bytes:
                    raise ApiError(413, "File too large")
                out.write(chunk)
        yield path
    finally:
        os.remove(path)
