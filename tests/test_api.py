"""Tests for the FastAPI layer. The slow pipeline is replaced by fakes: these test ONLY the API."""
import io
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import main as api_main
from api.main import create_app
from api.schemas import ArticleOut, ProcessResponse
from api.settings import Settings
from pipeline.run import process_pdf
from pipeline.schema import Article, Line


@pytest.fixture
def client():
    return TestClient(create_app(Settings(max_upload_mb=1)))


def pdf_file(name="a.pdf", body=b"%PDF-1.7 fake but has the right header"):
    """The `files=` argument of TestClient.post: {form field: (filename, bytes, content type)}."""
    return {"pdf": (name, io.BytesIO(body), "application/pdf")}


def fake_pipeline(monkeypatch, fn):
    monkeypatch.setattr(api_main.pipeline_run, "process_pdf", fn)


# ---------------------------------------------------------------- the original Flask test cases, ported
def test_home_page_loads(client):
    assert client.get("/").status_code == 200


def test_missing_file_is_400(client):
    r = client.post("/process_pdf")
    assert r.status_code == 400 and "No file" in r.json()["error"]


def test_non_pdf_is_400(client):
    r = client.post("/process_pdf", files=pdf_file(body=b"hello"))
    assert r.status_code == 400 and "not a valid PDF" in r.json()["error"]


def test_bad_pages_value_is_400(client):
    r = client.post("/process_pdf", files=pdf_file(), data={"pages": "one,two"})
    assert r.status_code == 400


def test_success_returns_pipeline_output(client, monkeypatch):
    seen = {}

    def fake_process(path, pages=None, ocr=True):
        seen["pages"] = pages
        return {"file": "x", "pages": []}

    fake_pipeline(monkeypatch, fake_process)
    r = client.post("/process_pdf", files=pdf_file(), data={"pages": "1,3"})
    assert r.status_code == 200 and r.json() == {"file": "a.pdf", "pages": []}
    assert seen["pages"] == [1, 3]


def test_pipeline_crash_becomes_422_and_temp_file_is_removed(client, monkeypatch):
    paths = []

    def boom(path, pages=None, ocr=True):
        paths.append(path)
        raise RuntimeError("corrupt")

    fake_pipeline(monkeypatch, boom)
    r = client.post("/process_pdf", files=pdf_file())
    assert r.status_code == 422 and r.json() == {"error": "Could not process this PDF"}
    assert not os.path.exists(paths[0])          # cleaned up even after a crash


def test_temp_file_is_removed_after_success(client, monkeypatch):
    paths = []
    fake_pipeline(monkeypatch, lambda path, pages=None, ocr=True: paths.append(path) or {"pages": []})
    client.post("/process_pdf", files=pdf_file())
    assert paths and not os.path.exists(paths[0])


def test_two_requests_use_different_temp_files(client, monkeypatch):
    """Regression for the old fixed 'temp.pdf' filename."""
    paths = []
    fake_pipeline(monkeypatch, lambda path, pages=None, ocr=True: paths.append(path) or {"pages": []})
    for _ in range(2):
        client.post("/process_pdf", files=pdf_file())
    assert paths[0] != paths[1]


def test_oversized_upload_is_413(client):
    r = client.post("/process_pdf", files=pdf_file(body=b"%PDF-" + b"0" * (2 * 1024 * 1024)))
    assert r.status_code == 413 and r.json() == {"error": "File too large"}


def test_response_shows_uploaded_filename_not_temp_path(client, monkeypatch):
    fake_pipeline(monkeypatch, lambda path, pages=None, ocr=True: {"file": path, "pages": []})
    r = client.post("/process_pdf", files=pdf_file(name="my paper.pdf"))
    assert r.json()["file"] == "my paper.pdf"


# ---------------------------------------------------------------- new behaviour
def test_oversized_body_without_honest_content_length_is_still_413(monkeypatch):
    """The size is also checked while copying, for clients whose Content-Length header is wrong."""
    from starlette.datastructures import UploadFile

    from api.errors import ApiError
    from api.uploads import temp_pdf

    upload = UploadFile(io.BytesIO(b"%PDF-" + b"0" * 5000), filename="a.pdf")
    with pytest.raises(ApiError) as err, temp_pdf(upload, max_bytes=1000):
        pass
    assert err.value.status_code == 413


def test_oversized_copy_removes_its_temp_file(monkeypatch):
    import tempfile

    from starlette.datastructures import UploadFile

    from api.errors import ApiError
    from api.uploads import temp_pdf

    made = []
    real_mkstemp = tempfile.mkstemp
    monkeypatch.setattr(tempfile, "mkstemp", lambda **kw: made.append(real_mkstemp(**kw)) or made[-1])
    upload = UploadFile(io.BytesIO(b"%PDF-" + b"0" * 5000), filename="a.pdf")
    with pytest.raises(ApiError), temp_pdf(upload, max_bytes=1000):
        pass
    assert not os.path.exists(made[0][1])


def test_busy_server_answers_503_then_recovers(client, monkeypatch):
    fake_pipeline(monkeypatch, lambda path, pages=None, ocr=True: {"pages": []})
    gate = client.app.state.job_gate
    assert gate.acquire(blocking=False)          # pretend another PDF is being processed
    try:
        r = client.post("/process_pdf", files=pdf_file())
        assert r.status_code == 503 and "busy" in r.json()["error"]
    finally:
        gate.release()
    assert client.post("/process_pdf", files=pdf_file()).status_code == 200


def test_gate_is_released_even_when_processing_crashes(client, monkeypatch):
    def boom(path, pages=None, ocr=True):
        raise RuntimeError("x")

    fake_pipeline(monkeypatch, boom)
    assert client.post("/process_pdf", files=pdf_file()).status_code == 422
    fake_pipeline(monkeypatch, lambda path, pages=None, ocr=True: {"pages": []})
    assert client.post("/process_pdf", files=pdf_file()).status_code == 200   # not stuck on 503


def test_every_error_has_the_same_shape(client):
    for r in (client.get("/nope"), client.get("/process_pdf"), client.post("/process_pdf")):
        assert set(r.json()) == {"error"}


def test_health_ok_and_degraded(client, monkeypatch):
    monkeypatch.setattr(api_main.health, "tesseract_version", lambda: "5.5.0")
    assert client.get("/health").json() == {"status": "ok", "tesseract": "5.5.0"}
    monkeypatch.setattr(api_main.health, "tesseract_version", lambda: None)
    assert client.get("/health").json() == {"status": "degraded", "tesseract": None}


def test_openapi_documents_the_endpoint(client):
    spec = client.get("/openapi.json").json()
    assert "/process_pdf" in spec["paths"] and "/health" in spec["paths"]
    assert set(spec["paths"]["/process_pdf"]["post"]["responses"]) >= {"200", "400", "413", "422", "503"}


def test_settings_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("NEWSPAPER_MAX_UPLOAD_MB", "7")
    assert Settings().max_upload_mb == 7


# ---------------------------------------------------------------- the contract with pipeline/
def sample_article() -> Article:
    line = Line((10, 20, 110, 40), 12.0, "text", "Body")
    return Article(page=1, headline_lines=[line], body_lines=[line], headline="Head", text="Body text",
                   summary="Sum", method={"path": "hybrid", "summary": "extractive"})


def test_models_have_exactly_the_fields_pipeline_produces():
    """If someone adds or renames a field in Article.to_dict(), this fails and says so."""
    assert list(ArticleOut.model_fields) == list(sample_article().to_dict())


def test_models_accept_what_pipeline_produces():
    page = {"page": 1, "path": "hybrid", "seconds": 0.1, "articles": [sample_article().to_dict()]}
    parsed = ProcessResponse.model_validate({"file": "f.pdf", "pages": [page]})
    assert parsed.pages[0].articles[0].bbox == (10.0, 20.0, 110.0, 40.0)


def test_models_reject_output_that_breaks_the_contract():
    bad = sample_article().to_dict() | {"method": {"path": "telepathy", "summary": "x"}}
    with pytest.raises(ValidationError):
        ArticleOut.model_validate(bad)


@pytest.mark.parametrize("name", ["ie_page1.pdf", "ie_page5.pdf"])
def test_models_accept_real_pipeline_output(fixtures_dir, name):
    """Real pages (layout only, no OCR, fast) go through the real models."""
    result = process_pdf(str(fixtures_dir / name), ocr=False)
    parsed = ProcessResponse.model_validate(result)
    assert parsed.pages and parsed.pages[0].articles
