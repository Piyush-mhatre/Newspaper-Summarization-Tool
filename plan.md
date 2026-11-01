# Newspaper Understanding Pipeline: Project Plan

Single source of truth for scope and goals. If a decision changes, edit this file first, then the code.

## 1. Goal

Take a newspaper page PDF (scanned or digital) and return, for every item on the page:

- the correct **headline** (as printed),
- the **article text**, in correct reading order,
- a **type**: `news`, `advertisement`, `infographic/sidebar`, or `furniture` (masthead, weather box, page number),
- a **summary** grounded only in that article's text,
- **where it came from** (page, bounding box) and **how confident** we are.

Success is measured on a hand-labeled test set (section 8), not by "it runs without crashing".

## 2. Constraints (non-negotiable)

| Constraint | Consequence |
|---|---|
| Free to use | No paid APIs as a dependency. Free-tier APIs are an optional bonus only. |
| Works offline and online | Every stage has an offline default. Online is an upgrade, never a requirement. |
| 8 GB laptop, ~1-2 GB free RAM | Core pipeline target: **under ~1 GB peak**. One page at a time. Never load OCR and an LLM together. |
| Intel i3-1115g4, integrated GPU | CPU only. No Detectron2, no large PyTorch layout models, no GPU assumptions. |
| Learning pytest | Pure logic is separated from I/O so most code is testable without a PDF, OCR or network. |

## 3. Key finding: our samples are two different kinds of PDF (corrected after testing)

Checked directly with `pdfinfo`, `pdffonts` and PyMuPDF:

| Sample | Pages | Content | Text layer |
|---|---|---|---|
| `News.pdf` (Times City, 8 Sep 2023) | 1 | One 1786x2781 JPEG | **None** (no fonts). Pure scan. |
| `IE_Mumbai-_-03-08-2023.pdf` (Indian Express, 3 Aug 2023) | 18 | **Vector text** drawn with embedded fonts, plus a full-page JPEG holding photos and graphics | **Present but unreadable to extractors.** Fonts have no Unicode mapping, so characters come out as glyph IDs (control characters). Boxes and font sizes are correct. |

**Correction:** an earlier version of this plan called the Indian Express pages scans with a hidden text layer. That was wrong. The headlines are real vector text, and the embedded JPEG does not contain them (cropping it gave a blank image). This is good news: any region can be rendered crisply at high zoom straight from the PDF, with no upscaling blur.

The second file's text layer is unreadable but has **accurate geometry**: on page 1, the span boxes line up with the printed headlines, bylines, body columns and ads when overlaid on the page image. Font sizes and names are also real (headlines roughly 40-85 pt in Poynter/ScoutCondensed fonts, body in Gulliver at small sizes).

Consequences:

- **Never trust `get_text()` blindly.** Each page needs a text-quality check (share of alphanumeric characters, control-character ratio). A page can "have text" and still be unusable.
- **Three extraction paths**, chosen per page:
  1. *Clean text layer*: use PyMuPDF text and boxes directly.
  2. *Scrambled text layer (hybrid)*: use the layer's **geometry and font sizes** for layout and headline detection, then **render and OCR only the regions** it identifies (headline, sub-headline, body runs) at about 2.5x zoom. Region OCR also avoids the column-interleaving problem.
  3. *No text layer*: OCR plus image-based layout analysis (OpenCV), as in `News.pdf`.
- Do **not** crop the embedded JPEG for vector pages (it does not contain the text). Render clips from the PDF instead. For a true scan (Times City), page size in points equals the scan's pixels, so rendering at zoom 1.0 reproduces it, and OCR upscales 1.5x.
- Tesseract's `image_to_data` gives per-word boxes and confidence for the OCR paths.
- Possible later optimisation: glyph IDs map consistently to characters within one font, so OCR output could build a per-document decode table and replace most OCR calls with a lookup. Worth trying if speed becomes the bottleneck.
- The Indian Express pages carry "CONTINUED ON PAGE 2" markers, so stories span pages. Cross-page joining is a real requirement (milestone 3).

## 4. Architecture

```
PDF
 1. ingest        validate, detect digital vs scanned (per page), pull page image
 2. extract       digital: PyMuPDF words+boxes | scanned: OCR words+boxes+conf
 3. layout        columns, lines -> blocks, drawn boxes/rules, image regions
 4. assemble      headline -> claims body blocks beneath it within its x-range
 5. classify      news / ad / sidebar / furniture (+ uncertain)
 6. summarize     extractive by default, optional local/remote LLM
 7. output        JSON per item: bbox, confidence, method, warnings
```

Every item records `method` (`text_layer`, `ocr`, `extractive`, `llm_local`, `llm_remote`) so we can always tell what produced a result.

### Stage notes

**Extract.** Tesseract is the baseline. RapidOCR (ONNX, CPU) is a candidate upgrade, adopted only if it beats Tesseract on our test set within the memory budget. Preprocessing (grayscale, upscale, deskew, contrast) is applied only where measurement shows it helps.

**Layout.** Classical computer vision first: OpenCV for rules/box lines and image regions, projection profiles or morphology for column gutters, OCR box heights for headline candidates. Headlines span N columns, and body blocks directly beneath within that x-range belong to them. Boxed sidebars attach to a parent story as sub-items. A small ONNX layout model is evaluated only if geometry plateaus. Heavy options (Detectron2, LayoutParser with big backbones, VLMs) are out of scope for this hardware.

**Classify.** Rule features (byline present, sentence density, phone numbers, prices, "T&C", image-area ratio, border, promotional words) feed a small scikit-learn model. Output includes an `uncertain` state instead of forcing a binary choice. Public notices, tenders and sponsored content are known hard cases.

**Summarize.**
- Default: improved extractive (TextRank or position-weighted scoring, sentences kept in original order).
- Optional offline: small quantized model via `llama-cpp-python` (about 0.5-1.5B parameters, roughly 0.4-1 GB). Slow on this CPU, so it runs as a background "quality mode" job.
- Optional online: a free-tier LLM API with timeouts and retries. Limits change, so check them before relying on it.
- Fallback chain: remote, then local, then extractive. The app never fails because a model is missing.
- All LLM summaries are grounded in the extracted article text only, with a check that numbers and names in the summary appear in the source.

**Headlines.** Return the printed headline when found. If missing or unreliable, mark it as missing, or give a clearly labeled generated title (`headline_source: "generated"`). Never present an invented headline as the original.

**"Up to date".** Default is **document-only mode**: the summary reflects what the newspaper reported. Checking claims against the live web is a possible later feature and is not in v1.

## 5. Output schema (target)

```json
{
  "page": 1,
  "type": "news",
  "headline": "City gets soaked again; IMD says rain intensity to drop from today",
  "headline_source": "printed",
  "byline": "Richa Pinto",
  "text": "...",
  "summary": "...",
  "bbox": [x0, y0, x1, y1],
  "method": {"extraction": "ocr", "summary": "extractive"},
  "confidence": {"headline": 0.0, "segmentation": 0.0, "classification": 0.0},
  "warnings": []
}
```

Confidence values are heuristic until calibrated against the test set. The OCR engine's confidence is not the probability that the final headline is correct.

## 6. Target repo layout

```
project/
  app.py                  # Flask: routes, validation, JSON only
  pipeline/
    ingest.py             # I/O: PDF -> page images / text
    extract.py            # I/O: OCR / PyMuPDF words+boxes
    layout.py             # pure: boxes -> columns -> blocks
    assemble.py           # pure: blocks -> articles
    classify.py           # pure/mockable
    summarize.py          # Summarizer interface + implementations
    schema.py
  tests/
    conftest.py
    test_layout.py  test_assemble.py  test_classify.py
    test_summarize.py  test_api.py  test_regression.py
    fixtures/             # small sample pages + verified expected JSON
  eval/
    labels/               # hand-annotated ground truth
    run_eval.py
  plan.md
```

## 7. Milestones (each ends with passing tests and a measurement)

| # | Milestone | pytest skills practiced |
|---|---|---|
| 0 | **Baseline.** Run the old code on `News.pdf`, save its output, hand-label the page (headlines, boxes, types). | Basic `assert`, test discovery |
| 1 | **Ingest + extraction.** Per-page text-quality check, choose clean / scrambled-hybrid / OCR path, extract native-res image, OCR to word boxes. Fix temp-file, NLTK-at-import and upload-validation issues. | Unit tests, `tmp_path`, `monkeypatch` to fake OCR |
| 2 | **Layout + articles.** Column detection, headline detection by box height, body claimed by x-range. This is where most accuracy gain comes from. | Fixtures with synthetic boxes, `parametrize` |
| 3 | **Sidebars, infographics, furniture, continuations.** Boxed regions, charts, mastheads excluded from news; join 'continued on page N' stories across pages. | Edge-case parametrization |
| 4 | **Classifier.** Ad vs news vs sidebar with an uncertain state. Needs extra sample pages that contain ads. | Parametrized feature tests, minimum-accuracy test |
| 5 | **Summarizer.** Better extractive first, then optional LLM tiers with the fallback chain. | Fake implementations, failure injection (timeout, missing model) |
| 6 | **Flask API + jobs.** Unique temp files, size limit, caching by file hash (SQLite), extractive result first, refined result later. | `app.test_client()`, bad/empty uploads |
| 7 | **Evaluation + regression.** Full benchmark, golden-file tests, time and memory guards. | Markers (`slow`), `--cov`, golden files |

Rule: no milestone starts until the previous one has tests and a recorded metric.

## 8. How accuracy is measured

Build a small labeled set first, on the order of 5-10 varied pages from these samples (a front page, an inner page, an ad-heavy page, the Times City scan), and keep it fixed.

| Aspect | Metric |
|---|---|
| OCR quality | Character and word error rate on a few hand-typed paragraphs |
| Headlines | Exact match and normalized text similarity |
| Segmentation | IoU between predicted and labeled article boxes; share of body text assigned to the right story |
| News vs ad | Precision, recall, F1, with hard cases reported separately |
| Summaries | Spot-checked for coverage and unsupported claims, plus the automated number/name grounding check |
| Resources | Seconds per page and peak RAM |

Numeric targets (for example "headline match above X%") are set **after** milestone 0 produces a baseline. Until then, no accuracy claims.

## 9. Out of scope for v1

- Live web fact-checking of article content
- Training our own deep layout model
- GPU or paid cloud services
- Rich frontend redesign (keep the existing upload page; improve later)
- Languages other than English (revisit after v1, since the Tesseract language data would need adding)

## 10. Risks and open questions

- **OCR quality on small body text** at this scan resolution is the biggest risk, and the reason OCR options are measured rather than assumed.
- **Test data:** we now have 19 pages from two newspapers, covering a pure scan and a scrambled-text-layer file, with ads on the Indian Express pages. Still needed: the labeled set (milestone 0) and ideally one clean-text-layer sample.
- **Original frontend files** (HTML/CSS/JS): do they still exist? If not, we build a minimal upload page.
- **Typical upload size:** one page or many? This affects batching and the job queue.
- **LLM speed:** is a few minutes of background summarizing acceptable, or should extractive be the default for everything?

## 11. Definition of done (v1)

1. `News.pdf` and at least 4 other labeled pages run end to end offline within the memory budget.
2. Headlines, boundaries and types beat the milestone 0 baseline by a clear, recorded margin.
3. The pytest suite passes, with unit, API, and golden-file regression tests.
4. Every output item carries bbox, method, confidence and warnings.
5. The README explains how to run it, how to run the tests, and the measured results.


## 12. Status: v0.5 (engineering track in progress)

Covers milestones 0-2 in a first form, plus the engineering track (typed API, tooling, automatic checks). See README.md and GUIDE.md.

| Area | State | Evidence |
|---|---|---|
| Path selection (text_layer / hybrid / ocr) | Working | `tests/test_quality.py` |
| Headline + sub-headline detection (size-based) | Working on IE pages | IE page 1: 11 candidates for 10 real stories (the extra one is an editorial-page promo box); IE page 5: exactly the 3 real stories |
| Hybrid OCR of regions | Working | Golden test: 4 printed headlines matched at 0.9+ similarity |
| Scan path (Times City) | **Rough** | 14-16 candidates for about 12 real stories; false headlines from OCR noise and gutter-crossing lines |
| Text leaking between stories | **Mostly fixed in v0.2** | Font-family filter, column-slot ownership, OCR with other stories painted out. On IE page 1: SPORTS / TRAIN KILLINGS / EDITORIAL PAGE / foreign byline now appear in 0 of 10 stories; promo box no longer a story; `&amp;` and `|` removed; `continues_on_page` recorded. Remaining: pull-quotes set in the body font |
| Extractive summary + byline strip | Basic | Summary quality unchanged; judged weak (Judge story summary misses the key fact) |
| API | **FastAPI** (was Flask) | Pydantic response models, one error shape, `/health`, `/docs`, one job at a time (503 when busy), strict typing; `tests/test_api.py` (23 tests) |
| Tooling | Done | uv + lock file, ruff, mypy, `scripts/check.py`, pre-commit (commit and push stages), GitHub Actions CI, Dependabot |
| Docker | Written; commands verified in a non-root imitation, `hadolint` clean | `Dockerfile`, `.dockerignore`, `compose.yaml`, CI job `docker` builds and smoke-tests the real image. Not yet built on the i3 |
| Tests | 114 fast (+1 documented xfail) and 8 slow; 122 pass with `check.py --all`; coverage 94% locally | `pytest`, `pytest -m slow`. On CI (no sample PDFs): 106 passed, 8 skipped |
| Debug overlay | Built | `python -m pipeline.debug`; shows lines, ownership and articles on the page, plus an HTML report |
| Memory | **Measured**: peak about 210 MB (Python + Tesseract) on IE page 1, sampled every 0.5 s on the sandbox | meets the "under ~1 GB" target; `compose.yaml` limit is 1 GB |
| Speed | **Slow** | Roughly 100 s for a dense IE page, 50 s for the scan page, on the sandbox CPU; not yet measured on the i3 |

Generalization check (Bombay Times, 4 scanned pages): **weak.** Ads reported as news, story boxes spanning whole pages, garbled headlines on busy layouts. The scan path needs real column/region detection.

Not yet done: job queue and database (engineering sprint 2), labeled benchmark set (milestone 0), boxed-region detection, ad classifier, cross-page joining, LLM summaries.

Engineering roadmap: sprint 1 = FastAPI (done), tooling (done), pre-commit + CI (done), Docker (written, awaiting first real build); sprint 2 = PostgreSQL + job queue + caching; sprints 3-4 = the ML track in section 14, then search and monitoring.

## 13. AI/ML track (first draft; superseded by section 14)

Honest framing: the baseline is mostly classical CV and heuristics. The ML work comes next, and each item produces a measurable result:

1. **Labeling and evaluation** (milestone 0): build a ground-truth set, compute headline similarity, CER and IoU (`eval/metrics.py` already has them).
2. **Ad vs news vs sidebar classifier** (milestone 4): feature engineering from text and geometry, scikit-learn model, train/test split, precision/recall/F1, error analysis on a confusion matrix.
3. **Summarizer evaluation** (milestone 5): compare the baseline extractive method against TextRank and an optional small LLM, using ROUGE plus a manual factual-consistency check.
4. **OCR engine comparison** (milestone 2b): Tesseract vs RapidOCR on the same regions, with time and memory recorded.
5. **Document layout model** (stretch): try a small ONNX layout detector against the geometry baseline and report whether it beats it.


## 14. AI/ML roadmap (the honest version)

**The rule:** a topic belongs on your resume only when this project contains a working, measured
version of it that you can explain without notes. Five topics done properly with numbers beat twelve
buzzwords, because interviewers will ask "how did you evaluate it?" about every line you list.

Every topic below becomes one small **experiment** with one results table in the README:
*baseline vs new method, on the same labeled pages, with numbers.*

| # | Topic | Where it genuinely fits here | What you measure | Hardware (8 GB, i3) |
|---|---|---|---|---|
| 1 | **Supervised classification** (scikit-learn) | ad / news / advertorial / sidebar classifier. The Bombay Times pictures show why it is needed. Compare logistic regression, random forest, gradient boosting against a hand-written rule baseline | precision, recall, F1 per class, confusion matrix | fine |
| 2 | **Feature engineering + explainability** | features per region: size statistics, font variety, phone/price/QR patterns, text density, image coverage. Then permutation importance or SHAP, and an ablation (drop a feature, see the score fall) | feature importance table, ablation table | fine |
| 3 | **Unsupervised learning** | cluster line x-positions (DBSCAN / k-means) to find columns; Gaussian mixture on log font sizes to discover headline/sub/body tiers. Replaces two hand-tuned rules with data-driven ones | agreement with the rules, box IoU against labels | fine |
| 4 | **Classical computer vision** (OpenCV) | thresholding, morphology, connected components, Hough lines for column rules and box borders, deskew. This is the fix for the scan path and for boxed pull-quotes | box precision/recall (IoU) against labeled boxes | fine |
| 5 | **OCR engineering** | Tesseract vs RapidOCR; zoom sweep; preprocessing ablations | character error rate, word error rate, seconds per page, RAM | fine |
| 6 | **NLP summarization** | lead-sentence baseline vs TF-IDF vs TextRank (a graph algorithm) vs sentence embeddings (small MiniLM model) | ROUGE plus **key-fact recall** (your Judge-story checklist: "judge", "daughter", "41 FIRs", "workshop") | fine |
| 7 | **Information extraction** | offline NER (spaCy small) for people, places, dates, numbers -> `key_points`; **grounding check**: every number and name in a summary must appear in the source text | grounding rate | fine |
| 8 | **Local LLM** (llama.cpp, quantized 0.5-1.5B) | abstractive summary with JSON output; compare with extractive on the same checklist; measure hallucinations with the grounding check | key-fact recall, grounding rate, seconds per story | slow on this CPU; background job only |
| 9 | **Weak supervision (stretch, distinctive)** | the Indian Express fonts map glyph IDs to letters. Use OCR output as automatic labels to *learn* a per-font decoder, then read text without OCR. **Unverified:** I have not checked that glyph IDs are consistent across the document | decoder accuracy vs OCR (CER), speed-up | fine if it works |
| 10 | **Pretrained layout detector (stretch)** | run a small ONNX document-layout model and compare with our geometry method. Training one is out of reach on this laptop | IoU against labels | inference maybe; training no (a free cloud notebook could do it, but free tiers change, so check first) |
| 11 | **ML engineering** | **split data by newspaper/page, never by line** (lines on one page are near-duplicates, so a random line split gives a falsely high score); experiment log (CSV or MLflow); fixed random seeds; model card; confidence calibration; error-analysis write-up; CI that runs pytest on every push | reproducibility, calibration plot | fine |
| 12 | **Active learning (stretch)** | pick the regions the classifier is least sure about and label those first, using the debug overlay as the labeling picture | score vs number of labels | fine |

### Suggested order (each step feeds the next)
1. **Labeling tool + benchmark** (extend the debug overlay so you click/mark region types) -> unlocks everything.
2. **#1 and #2**: classifier with explainability. First real ML result.
3. **#3**: clustering vs the hand-written column rule.
4. **#4**: OpenCV boxes (fixes the pull-quote leak and the scan path).
5. **#6 and #7**: summarization comparison with key-fact recall and grounding.
6. **#11** woven through all of it (page-level splits, experiment log, CI).
Then, if time remains: **#5, #8, #9**.

### Things to be careful about
- With about 20 labeled pages, scores are noisy. Report that honestly, and use cross-validation grouped by page.
- Do not list a topic until its results table exists.
- Keep newspaper PDFs and page images out of a public repo (copyright); share only your code, label files and metrics.

### Resume bullets you can write AFTER the numbers exist (fill the brackets with measured values only)
- "Built an offline document-understanding pipeline (PyMuPDF, Tesseract, OpenCV) that segments newspaper pages into articles; headline accuracy [X%] on [N] hand-labeled pages."
- "Trained and compared [3] classifiers to separate advertisements from editorial content; F1 [X] vs [Y] for a rule baseline; page-grouped cross-validation; explained with permutation importance."
- "Cut text leakage between articles from [A] to [B] stories per page via font-family and column-ownership rules, enforced by [N] pytest regression tests."
- "Compared [lead / TextRank / embedding / local-LLM] summarizers on key-fact recall and hallucination rate; [method] won on [metric]."
