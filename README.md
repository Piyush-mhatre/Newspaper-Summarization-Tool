# Newspaper pipeline (v0.3)
[![CI](https://github.com/Piyush-mhatre/Newspaper-Summarization-Tool/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Piyush-mhatre/Newspaper-Summarization-Tool/actions/workflows/ci.yml)

**New to this? Read `GUIDE.md` first.** It explains every idea, file and test from zero.

Turns a newspaper PDF into structured articles: headline, sub-headline, text, summary, bounding box.
Works offline, CPU only. See `plan.md` for the goal and roadmap.

## Setup

```bash
# 1. Tools (once per machine)
#    uv (Python + package manager):
#      Windows (PowerShell): powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
#      Linux/Mac:            curl -LsSf https://astral.sh/uv/install.sh | sh
#    Tesseract OCR engine (system program, not a Python package):
#      Windows: https://github.com/UB-Mannheim/tesseract/wiki   (tick "add to PATH" or add it yourself)
#      Linux:   sudo apt install tesseract-ocr
# 2. Project (uv downloads the right Python and installs the exact tested versions from uv.lock)
uv sync
# 3. Prove it works
uv run python scripts/check.py
# 4. Turn on the automatic checks before every commit and push (once per clone, see GUIDE.md Part 10)
uv run pre-commit install
```

Run any command inside the project's environment by putting `uv run` in front of it.

## Run

```bash
uv run python -m pipeline.run paper.pdf --pages 1 --out result.json    # CLI
uv run python -m pipeline.run paper.pdf --pages 1 --no-ocr             # layout only, fast
uv run python -m pipeline.debug paper.pdf --page 1 --out debug_out     # pictures + HTML report of what was detected
uv run uvicorn api.main:app --reload                              # API: http://127.0.0.1:8000  (docs: /docs)
```

## API

| Method and path | What it does |
|---|---|
| `POST /process_pdf` | multipart form: `pdf` (file, required), `pages` (e.g. `1,3`, optional). Returns articles as JSON. |
| `GET /health` | `{"status": "ok", "tesseract": "5.5.3"}`, or `"degraded"` / `null` if Tesseract cannot be found. |
| `GET /docs` | interactive Swagger UI, generated from the code (try the API in the browser). |
| `GET /openapi.json` | machine-readable API description. |

Every error has one shape, `{"error": "message"}`:

| Status | Meaning |
|---|---|
| 400 | no file, not a PDF, or `pages` is not a list of integers |
| 413 | file larger than the limit (default 50 MB) |
| 422 | the PDF is valid but could not be processed |
| 503 | the server is already processing another PDF (one at a time by default) |

Settings (environment variables): `NEWSPAPER_MAX_UPLOAD_MB` (default 50), `NEWSPAPER_MAX_CONCURRENT_JOBS` (default 1).

```powershell
# Windows PowerShell, from the project folder, with the server running in another window:
curl.exe -F "pdf=@C:\path\to\paper.pdf" -F "pages=1" http://127.0.0.1:8000/process_pdf
```

## Run with Docker (optional)

```powershell
docker build -t newspaper-pipeline .
docker run --rm -p 8000:8000 newspaper-pipeline      # http://127.0.0.1:8000/docs
# or:  docker compose up --build
```

The image contains the API, the pipeline, the locked Python libraries and Tesseract, runs as a non-root
user, and reports its own health. Sample PDFs are never inside it. See GUIDE.md Part 11.

## Automatic checks

| Where | When | What runs |
|---|---|---|
| your laptop, `git commit` | every commit | whitespace and file hygiene, ruff, mypy, "no PDFs" guard (a few seconds) |
| your laptop, `git push` | every push | the fast tests |
| GitHub Actions (`.github/workflows/ci.yml`) | every push and pull request | everything again on a clean machine, plus a job that builds the Docker image and smoke-tests it. Sample PDFs are not in the repo, so tests that need them are *skipped* there (expected: about 106 passed, 8 skipped) |

Once the repository is on GitHub, add this badge under the title (replace `USER` and `REPO`):
`![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)`

## Check everything (start here when something feels wrong)

```bash
uv run python scripts/check.py          # lint + types + fast tests, a few seconds
uv run python scripts/check.py --all    # also the slow real-OCR tests, minutes
```

Each line says PASS or FAIL for one tool, so you know where to look (see GUIDE.md, Part 8).

## Test only

```bash
uv run pytest                      # 100 fast tests (+1 expected failure), a few seconds
uv run pytest -m slow              # real OCR on the sample pages, several minutes
uv run pytest --cov=pipeline --cov-report=term-missing
uv run pytest -k layout -v         # only tests with "layout" in their name, verbose
uv run pytest -x --lf              # stop at first failure / rerun only last failures
```

## How it works

```
PDF page
  quality.choose_path   text_layer | hybrid | ocr
  extract               lines with box + size   (PyMuPDF text layer, or Tesseract for scans)
  layout.build_articles headline = much larger text; body = closest headline above, same columns
  run.fill_text_by_ocr  hybrid only: render each region crisply from the PDF and OCR it
  summarize             extractive, original sentence order, byline stripped
```

The three paths exist because our samples are different:

| Sample | What it is | Path |
|---|---|---|
| Times City page | one JPEG, no text at all | `ocr` |
| Indian Express pages | vector text whose fonts have no Unicode map: extractors return garbage, but boxes and font sizes are correct | `hybrid` |
| (not yet seen) clean digital PDF | normal text layer | `text_layer` |

## Where each pytest concept appears

| Concept | See |
|---|---|
| Plain `assert` tests | `tests/test_metrics.py` |
| `@pytest.mark.parametrize` | `tests/test_textutil.py`, `tests/test_quality.py` |
| Fixtures / factory fixtures | `tests/conftest.py` (`make_line`, `fake_page`) |
| Testing exceptions | `test_weighted_median_needs_lines` in `tests/test_layout.py` |
| Approximate floats | `pytest.approx` in `tests/test_metrics.py` |
| `monkeypatch` (fake the slow part) | `tests/test_api.py` |
| FastAPI `TestClient`, Pydantic models | `tests/test_api.py`, `api/schemas.py` |
| Regression tests (each one pins a real bug we hit) | `tests/test_leaks.py`, search "Regression" in `tests/` |
| Fixture scope, `xfail` | `tests/test_leaks.py`, `tests/test_textutil.py` |
| Markers (`slow`) and pytest settings | `pyproject.toml`, `tests/test_integration.py` |
| Golden tests (compare to human-read truth) | `test_ie_front_page_headlines_match_the_printed_ones` |

**Exercises to do yourself** (do these in order; each is small):
1. Add a `parametrize` case to `test_choose_path` for a page with 19 geometry lines.
2. Write a test that `Article.to_dict()` rounds the bbox to one decimal.
3. Find a headline on `ie_page5.pdf` that the pipeline gets wrong and add a failing test, then fix the code.
4. Run `pytest --cov` and write a test for a line that is not covered.

## Known limitations (honest list)

- **Pull-quotes and boxes set in the BODY font** can still sit inside a story (for example the "ONLY 2,000 of the 10,500..." quote in the Adopt WHO story). v0.2 removed boxes set in other fonts (SPORTS, kickers, captions, promos). Fix for the rest: detect drawn rectangles (milestone 3).
- **Scan path (Times City) is rough**: about 14-16 candidates for about 12 real stories. Tesseract lines cross column gutters and OCR height noise creates false headlines. Fix: OpenCV column detection (milestone 2b).
- **Editorial-page promo boxes** ("THE EDITORIAL PAGE") are reported as stories. Fix: classifier (milestone 4).
- **Speed**: about 100 s for a dense page on the sandbox CPU, because OCR runs once per text run. Fix: fewer, larger OCR regions and 2 worker processes.
- **Cross-page joining** is not done yet: v0.2 records `continues_on_page` but does not yet attach the continuation.
- **Summaries** are extractive only, and bylines only strip when printed in ALL CAPS.
