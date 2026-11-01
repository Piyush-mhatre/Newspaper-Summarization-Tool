"""Flask API. Routes only: validation in, JSON out. All real work lives in pipeline/."""
from __future__ import annotations

import os
import tempfile

from flask import Flask, jsonify, request

from pipeline import run as pipeline_run

INDEX_HTML = """<!doctype html><title>Newspaper reader</title>
<h1>Upload a newspaper PDF</h1>
<form action="/process_pdf" method="post" enctype="multipart/form-data">
<input type="file" name="pdf" accept="application/pdf"> <button>Process</button></form>"""


def create_app(max_upload_mb: int = 50) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = max_upload_mb * 1024 * 1024
    app.json.sort_keys = False  # type: ignore[attr-defined]  # temporary: keep our field order (headline first) in the JSON

    @app.get("/")
    def home():
        return INDEX_HTML

    @app.post("/process_pdf")
    def process_pdf():
        upload = request.files.get("pdf")
        if upload is None or upload.filename == "":
            return jsonify(error="No file uploaded (expected form field 'pdf')"), 400
        if upload.stream.read(5) != b"%PDF-":
            return jsonify(error="File is not a valid PDF"), 400
        upload.stream.seek(0)

        try:
            pages = request.form.get("pages")
            wanted = [int(p) for p in pages.split(",")] if pages else None
        except ValueError:
            return jsonify(error="'pages' must be comma-separated integers"), 400

        # unique temp file per request: concurrent uploads can't overwrite each other
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            upload.save(path)
            result = pipeline_run.process_pdf(path, pages=wanted)
            result["file"] = upload.filename   # show the user's name, not our temp path
            return jsonify(result)
        except Exception:  # corrupt PDF, OCR failure, etc.
            app.logger.exception("processing failed")
            return jsonify(error="Could not process this PDF"), 422
        finally:
            os.remove(path)

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="File too large"), 413

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
