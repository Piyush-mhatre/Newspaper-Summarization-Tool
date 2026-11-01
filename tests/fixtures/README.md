# Sample PDFs (not in git)

The integration tests need three real newspaper pages. They are copyrighted, so they are **not**
committed to the repository (`tests/fixtures/*.pdf` is in `.gitignore`).

| File | What it is | Used for |
|---|---|---|
| `ie_page1.pdf` | a front page with a readable text layer (hybrid path) | layout, headlines, leak regression tests |
| `ie_page5.pdf` | an inner page with ads and a header | ad / header filtering |
| `times_city.pdf` | a pure scan, no text layer (scan path) | scan detection and OCR path |

Put files with these exact names in this folder to run the integration tests locally.
Without them those tests are **skipped** (not failed), so a fresh clone and CI stay green.
All other tests use synthetic data and need no PDFs.
