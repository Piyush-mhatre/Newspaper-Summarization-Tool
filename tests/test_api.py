import io

import pytest

import app as app_module


@pytest.fixture
def client():
    return app_module.create_app(max_upload_mb=1).test_client()


def pdf_bytes():
    return io.BytesIO(b"%PDF-1.7 fake but has the right header")


def test_home_page_loads(client):
    assert client.get("/").status_code == 200


def test_missing_file_is_400(client):
    r = client.post("/process_pdf")
    assert r.status_code == 400 and "No file" in r.get_json()["error"]


def test_non_pdf_is_400(client):
    r = client.post("/process_pdf", data={"pdf": (io.BytesIO(b"hello"), "x.pdf")})
    assert r.status_code == 400


def test_bad_pages_value_is_400(client):
    r = client.post("/process_pdf", data={"pdf": (pdf_bytes(), "a.pdf"), "pages": "one,two"})
    assert r.status_code == 400


def test_success_returns_pipeline_output(client, monkeypatch):
    """monkeypatch replaces the slow pipeline with a fake: the test checks only the API layer."""
    seen = {}

    def fake_process(path, pages=None, ocr=True):
        seen["pages"] = pages
        return {"file": "x", "pages": []}

    monkeypatch.setattr(app_module.pipeline_run, "process_pdf", fake_process)
    r = client.post("/process_pdf", data={"pdf": (pdf_bytes(), "a.pdf"), "pages": "1,3"})
    assert r.status_code == 200 and r.get_json() == {"file": "a.pdf", "pages": []}
    assert seen["pages"] == [1, 3]


def test_pipeline_crash_becomes_422_and_temp_file_is_removed(client, monkeypatch, tmp_path):
    paths = []

    def boom(path, pages=None, ocr=True):
        paths.append(path)
        raise RuntimeError("corrupt")

    monkeypatch.setattr(app_module.pipeline_run, "process_pdf", boom)
    r = client.post("/process_pdf", data={"pdf": (pdf_bytes(), "a.pdf")})
    assert r.status_code == 422
    import os
    assert not os.path.exists(paths[0])          # cleaned up even after a crash


def test_two_requests_use_different_temp_files(client, monkeypatch):
    """Regression for the old fixed 'temp.pdf' filename."""
    paths = []
    monkeypatch.setattr(app_module.pipeline_run, "process_pdf",
                        lambda path, pages=None, ocr=True: paths.append(path) or {"pages": []})
    for _ in range(2):
        client.post("/process_pdf", data={"pdf": (pdf_bytes(), "a.pdf")})
    assert paths[0] != paths[1]


def test_oversized_upload_is_413(client):
    big = io.BytesIO(b"%PDF-" + b"0" * (2 * 1024 * 1024))
    r = client.post("/process_pdf", data={"pdf": (big, "big.pdf")})
    assert r.status_code == 413


def test_response_shows_uploaded_filename_not_temp_path(client, monkeypatch):
    monkeypatch.setattr(app_module.pipeline_run, "process_pdf",
                        lambda path, pages=None, ocr=True: {"file": path, "pages": []})
    r = client.post("/process_pdf", data={"pdf": (pdf_bytes(), "my paper.pdf")})
    assert r.get_json()["file"] == "my paper.pdf"
