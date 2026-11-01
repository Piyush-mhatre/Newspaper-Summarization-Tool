"""The routes. Validation in, typed JSON out. All real work lives in pipeline/."""
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from api import health, uploads
from api.errors import ApiError, register_error_handlers
from api.schemas import ErrorResponse, HealthResponse, ProcessResponse
from api.settings import Settings
from pipeline import run as pipeline_run

log = logging.getLogger("newspaper.api")

INDEX_HTML = """<!doctype html><title>Newspaper reader</title>
<h1>Upload a newspaper PDF</h1>
<form action="/process_pdf" method="post" enctype="multipart/form-data">
<input type="file" name="pdf" accept="application/pdf"> <button>Process</button></form>
<p>API documentation: <a href="/docs">/docs</a></p>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an app. Tests call this with their own Settings; uvicorn uses the `app` below."""
    settings = settings or Settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024

    app = FastAPI(
        title="Newspaper reader",
        version="0.4.0",
        description="Upload a newspaper PDF, get structured articles (headline, text, summary, box).",
    )
    register_error_handlers(app)

    # At most N PDFs processed at once: OCR is heavy and a laptop has little RAM.
    app.state.job_gate = threading.BoundedSemaphore(settings.max_concurrent_jobs)

    @app.middleware("http")
    async def reject_huge_bodies(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Refuse an oversized upload from its Content-Length header, before reading all of it."""
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            return JSONResponse({"error": "File too large"}, status_code=413)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> str:
        return INDEX_HTML

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def get_health() -> HealthResponse:
        version = health.tesseract_version()
        return HealthResponse(status="ok" if version else "degraded", tesseract=version)

    @app.post(
        "/process_pdf",
        response_model=ProcessResponse,
        tags=["pipeline"],
        responses={
            400: {"model": ErrorResponse, "description": "no file, not a PDF, or bad 'pages'"},
            413: {"model": ErrorResponse, "description": "file too large"},
            422: {"model": ErrorResponse, "description": "the PDF could not be processed"},
            503: {"model": ErrorResponse, "description": "server is busy with another PDF"},
        },
    )
    # A plain `def` (not `async def`) on purpose: processing blocks for a minute or more, and FastAPI
    # runs plain `def` routes in a worker thread so the server keeps answering other requests.
    def process_pdf(
        pdf: Annotated[UploadFile | None, File(description="the newspaper PDF")] = None,
        pages: Annotated[str | None, Form(description="e.g. '1,3'; default: all pages")] = None,
    ) -> ProcessResponse:
        upload = uploads.require_pdf(pdf)
        wanted = uploads.parse_pages(pages)

        gate: threading.BoundedSemaphore = app.state.job_gate
        if not gate.acquire(blocking=False):
            raise ApiError(503, "Server is busy processing another PDF, try again shortly")
        try:
            with uploads.temp_pdf(upload, max_bytes) as path:
                try:
                    result = pipeline_run.process_pdf(path, pages=wanted)
                except Exception:  # corrupt PDF, OCR failure, etc.
                    log.exception("processing failed")
                    raise ApiError(422, "Could not process this PDF") from None
                result["file"] = upload.filename  # show the user's name, not our temp path
                return ProcessResponse.model_validate(result)
        finally:
            gate.release()

    return app


app = create_app()
