# GUIDE: how this project works, from zero

Read this top to bottom once. Every idea is introduced before it is used.
When a word is in `code style`, it is a real name you can search for in the project.

---

## Start here: the whole project in four questions

For **every line of text on the page**, the program asks four questions, in this order:

| # | Question | How it is answered | If the answer is... |
|---|---|---|---|
| 1 | **How big is it?** | compare its font size to the page's normal text size | much bigger = probably a headline; normal = story text; tiny = ignore |
| 2 | **What font is it?** | compare to the page's main text font | same font = story text; a different font = caption, kicker, byline, box |
| 3 | **Where is it?** | which headline is above it and covers its column? | that headline "owns" it |
| 4 | **What does it say?** | only now read the letters (OCR), only for lines we kept | the story text |

Everything in the code is one of these four questions. The rest of the project is cleaning the
result, testing it and measuring it.

## See it before you read it

Run this (add `--no-ocr` to skip reading letters and get the pictures in a few seconds):

```bash
python -m pipeline.debug "paper.pdf" --page 1 --out debug_out
```

It makes three pictures and one report page. Example numbers are from Indian Express page 1
(`debug_examples/indian_express_p1/`):

| Picture | Shows | What it says for IE page 1 |
|---|---|---|
| `page1_1_lines.png` | **Question 1.** Every line found. Red = big text, green = body-sized. | 582 lines: 39 big, 543 body-sized |
| `page1_2_ownership.png` | **Questions 2 and 3.** One colour per article. Grey = ignored. | 493 lines used by 10 articles, 89 ignored |
| `page1_3_articles.png` | The final article boxes, numbered. | 10 articles |
| `page1_report.html` | **Question 4.** A table: number, printed headline, line counts, words, continues-on-page, summary. | e.g. #10 Judge story: 554 words |

Things worth noticing in the pictures:
- In picture 1 the red boxes include things that are NOT headlines: the little kickers ("TRAIN KILLINGS"),
  and the giant "E" of an "EXPLAINED" graphic. Being big only makes a line a *candidate*.
- In picture 2 those same kickers are grey, because no body text sits under them. They never become articles.
  The SPORTS box, the promo box and the photo captions are grey too: different font, so ignored.
- Compare with `debug_examples/bombay_times_p3/`: the scan path finds the real story (#1) but its box
  runs far too long, and four **ads** (#2 to #5) are reported as articles. That is the picture to
  keep in mind when we build the ad classifier.

---

## Part 1: The problem

A newspaper page looks simple to a human: you see headlines, columns, photos, ads.
To a computer, a PDF page is **not** "headlines and articles". It is just a list of
drawing instructions: "draw these letters here, draw this picture there".

Our job: from those instructions, recover **which text is a headline, which text is the
story under it, and which text is something else** (ad, caption, box).

### Three kinds of PDF (this is the most important idea in the project)

| Kind | What it contains | Example we have | What a program can read |
|---|---|---|---|
| **Scan** | One big photo of the page. No letters at all, just pixels. | Times City, Bombay Times | Nothing, until we run OCR |
| **Clean digital** | Real letters, with a map from each drawing-shape to a character (`A`, `B`...) | (we have no sample yet) | Text directly |
| **Broken digital** | Real letters drawn on the page, but the map from shapes to characters is missing | Indian Express | Garbage characters, BUT the positions and font sizes are correct |

The third kind is why this project has three "paths" (see `quality.py`).

---

## Part 2: Words you need

**Text layer**: the invisible list of characters a PDF stores so you can select and copy text.
Scans have none. Broken digital PDFs have a useless one.

**Vector vs raster**: raster = pixels (a photo). Vector = shapes described by math ("draw an `A`
at this spot, this big"). Vector text can be drawn at any zoom and stays sharp. A photo gets blurry
when zoomed. This matters: for Indian Express we can re-draw any small area at 2.5x zoom and get
crisp letters for OCR.

**Bounding box (bbox)**: the rectangle around something, written `(x0, y0, x1, y1)` =
(left, top, right, bottom). On a PDF page, y grows **downward** (top of page is y=0). Almost every
decision in this project is made by comparing bounding boxes.

**Font size**: how big letters are. Headlines are much bigger than body text. We use that.

**OCR (Optical Character Recognition)**: software that looks at a picture of text and returns the
letters. We use **Tesseract**, a free OCR engine, through a Python wrapper called `pytesseract`.
OCR is slow (seconds per region) and makes mistakes (`Regimentas a soldier` instead of
`Regiment as a soldier`).

**Zoom**: how many pixels we draw per PDF unit. Zoom 1.0 = same size as the page. Zoom 2.5 = 2.5x
bigger, so small text is large enough for Tesseract to read reliably.

**Heuristic**: a practical rule that works most of the time but is not guaranteed. Example: "a
headline is a line with text at least 1.6x bigger than normal body text". Most of this project is
heuristics. That is not bad: heuristics are fast, explainable and testable. But each one has cases
where it fails, and finding those is the real work.

**Ratio instead of fixed numbers**: we never say "headline = 40 points". We say "1.6x the body
size of THIS page". Different newspapers use different sizes, but the ratio idea transfers.

**Median**: the middle value when you sort numbers. Better than the average because one huge
headline can't drag it up. **Weighted median** (`weighted_median_size`): each line counts in
proportion to its width, so a few long body lines outvote many tiny big-text fragments.

**Regression**: something that used to work breaking again. A **regression test** is a test written
so a bug you already fixed cannot come back unnoticed.

---

## Part 3: What happens to one page (follow the numbers)

We follow Indian Express page 1. Each step names the file that does it.

**Step 0: Which path?** (`quality.py`, called from `run.py`)
Ask the PDF for its text. Does it look like English? `is_text_usable` checks two things:
(a) are the characters letters/digits/punctuation, (b) are common words ("the", "of", "and")
present? Indian Express fails both, because its text is control characters. But it has 582 lines
with sensible boxes, so `choose_path` returns **`hybrid`**.
A scan has no text and no boxes, so it returns **`ocr`**. Real text returns **`text_layer`**.

**Step 1: Get lines with geometry** (`extract.py`)
`text_layer_lines` asks PyMuPDF for every line: its box, its font size, its font name. We ignore the
unreadable characters (`keep_text=False`) and keep only geometry. Each line becomes a `Line`
object (defined in `schema.py`).

**Step 2: Find normal text size** (`layout.weighted_median_size`)
Result for this page: **12.8**. That is "body size".

**Step 3: Find headlines** (`layout.find_headline_groups`)
Any line at least 1.6 x 12.8 = 20.5 big is a headline *candidate*. Candidates that are stacked
(similar size, touching vertically, overlapping horizontally) are merged into one headline.
For example "Opposition meets President, presses" and "demand for PM statement on Manipur" are two
lines at size 85.2 and become one headline group.
Groups narrower than 6x body size are rejected (so the giant letter "E" of an "EXPLAINED"
graphic is not a headline).

**Step 4: Sub-headlines** (`layout.attach_subheads`)
A smaller big-text group right under a much bigger one (at least 2x smaller) is that headline's
sub-headline: "Asks Murmu to step in..." (22.4) under the 85.2 headline.
Why 2x? We learned this from a bug: a 78pt page header "MAHARASHTRA" swallowed a 45pt
headline (ratio 1.75) as its "subhead". Real subheads are 2x or more smaller.

**Step 5: Decide which lines are body text** (`layout.assign_body_lines`)
Three rules:
1. **Size**: between 0.6x and 1.5x body size.
2. **Font**: the same font *family* as the page's main body font (`dominant_body_family`).
   On this page that is "Gulliver". Captions, kickers ("TRAIN KILLINGS"), bylines and teaser boxes
   use other fonts ("Scout"), so they are excluded.
3. **Owner**: a body line belongs to the **closest headline above it whose width covers the
   line's column**. Note "column", not "line": a short byline line is treated as if it were a full
   column wide. (This fixed the bug where the Judge story's byline went to the wrong story.)

**Step 6: Reading order** (`layout.order_lines`)
Newspapers are read column by column, top to bottom, then the next column. We group lines into
columns by their left edge (x0) and sort each column top to bottom.

**Step 7: Throw away non-stories** (`layout.build_articles`)
A headline with fewer than 3 body lines is not an article (it's a masthead, an ad slogan, a
promo box). This is why "THE COURT'S QUESTIONS" disappeared after we added the font rule.

**Step 8: Read the letters** (`run.fill_text_by_ocr`, `extract.ocr_text`)
Only for `hybrid`. For each article we OCR: the headline, the sub-headline, and each **run** of
body lines (a run = lines of one column with no big gap; `split_runs`).
Important trick: before OCR, `render_clip` **paints white over every line that belongs to a
different story**. Without this, OCR reads everything inside the rectangle, including a neighbour's
text. This is what removed "SPORTS", "TRAIN KILLINGS" and the other leaks.

**Step 9: Clean the text** (`textutil.py`)
- `clean_ocr_line`: turn `&amp;` into `&`, remove `|` (the thin line between columns that OCR
  reads as a letter).
- `join_lines`: join lines into one paragraph; repair `govern-` + `ment` into `government`.
- `extract_continued`: remove "CONTINUED ON PAGE 2" from the text and save `2` in
  `continues_on_page`. (`run.find_continued_marker` OCRs the tiny area under each column's last line
  to find it, because it is in a different font and was excluded from the body.)

**Step 10: Summary** (`summarize.py`)
Split into sentences, score each by how many of the story's important words it contains (divided
by its length), keep the top 3, and show them in original order. `bylines.strip_byline` first
removes the "ALL-CAPS NAME CITY, AUGUST 2" opening.
This is the weakest part and will be replaced later.

**Step 11: Output** (`schema.Article.to_dict`) is the JSON you paste back to me.

### The scan path is different
For a pure scan (`ocr` path) there are no boxes to start from. We OCR the **whole page** with
Tesseract (`extract.ocr_lines`), which gives words with positions; we group them into lines, treat
"line height" as "font size", then run the same Steps 2-7. It works worse because Tesseract's
lines are noisier than real font data. This is where most remaining work is.

---

## Part 4: Every file, one by one

### `pipeline/` (the actual program)

| File | Job | Touches PDFs/OCR? |
|---|---|---|
| `schema.py` | Defines `Line` (one printed line: box, size, text, font) and `Article` (headline + body lines + result fields). Also box helpers `union_bbox`, `x_overlap`. Everything else passes these around. | No |
| `quality.py` | Decides `text_layer` / `hybrid` / `ocr`. | No |
| `layout.py` | **The brain.** Lines in, articles out: body size, headlines, sub-headlines, ownership, reading order. | No |
| `textutil.py` | Small string cleaners: `join_lines`, `clean_ocr_line`, `extract_continued`. | No |
| `bylines.py` | Strips the byline from the start of a story. | No |
| `summarize.py` | Baseline extractive summary. | No |
| `extract.py` | **The hands.** Talks to PyMuPDF and Tesseract: read lines, render a region, OCR a region. | Yes |
| `run.py` | **The conductor.** Chooses the path, calls everything in order, builds the JSON. Also the command line (`python -m pipeline.run`). | Yes |

**Why split "brain" and "hands"?** Code that touches PDFs and OCR is slow and hard to test.
Code that only compares numbers is instant to test. So we keep every decision in the files marked
"No" and keep the "Yes" files as thin as possible. This single design choice is what makes the
fast test suite possible.

### Other files

| File | Job |
|---|---|
| `api/` | The FastAPI web layer (see Part 9). Receives an uploaded PDF, checks it, saves it to a **unique** temp file, calls the pipeline, deletes the temp file, returns typed JSON. Contains no newspaper logic. |
| `pipeline/debug.py` | Draws the three pictures and the HTML report (see "See it before you read it"). Its pure helpers (`size_class`, `line_roles`, `summary_counts`) are unit-tested; the drawing code is checked by one test that confirms the files are written. |
| `eval/metrics.py` | Measuring tools: `cer` (character error rate), `headline_similarity`, `iou` (box overlap). Not used by the app; used to *score* it. |
| `tests/` | See Part 5. |
| `tests/fixtures/` | Small real PDFs the tests use. |
| `pyproject.toml` | All settings in one file: dependencies, ruff, mypy, pytest, coverage (see Part 8). |
| `uv.lock` | Exact versions of every library that was tested. Commit it, never edit it by hand. |
| `scripts/check.py` | One command that runs lint, types and tests and says which one failed. |
| `plan.md` | The goal and roadmap. `README.md` = how to run. `GUIDE.md` = this file. |

---

## Part 5: Testing and pytest from zero

### What is a test?
A small function that runs your code with a known input and checks the output is what you expect.
If you change code later, tests tell you in under a second whether you broke something. Without
tests, every change is a gamble.

### How pytest works
1. You run `pytest`.
2. It finds files named `test_*.py` and inside them functions named `test_*`.
3. It runs each one. A test **passes** unless something inside it fails.
4. `assert something` fails the test when `something` is False. That is the whole mechanism.

```python
def test_join_lines():
    assert join_lines(["govern-", "ment"]) == "government"
```

### Reading the output
```
90 passed, 8 deselected, 1 xfailed in 0.68s
```
- `passed`: good. `failed`: a test caught a problem, and pytest prints exactly which line and values.
- `deselected`: skipped on purpose (our slow tests, see below).
- `xfailed`: "expected failure". A known limitation we wrote down instead of hiding.

### Tools pytest gives us (each used somewhere in this project)

| Tool | In plain words | Where to see it |
|---|---|---|
| **`parametrize`** | Run one test with many inputs. Each input shows as its own pass/fail. | `test_textutil.py`, `test_quality.py` |
| **fixture** | A reusable piece of setup. A test asks for it by writing its name as a parameter. | `conftest.py` |
| **factory fixture** | A fixture that gives you a function to build things (`make_line`). | `conftest.py` |
| **fixture scope** | How long a fixture lives: per test (default), per file (`module`), whole run (`session`). Sharing a slow result across tests saves minutes. | `ie1_result` in `test_leaks.py` runs OCR once for 6 tests |
| **`monkeypatch`** | Temporarily replace a function with a fake during one test. | `test_api.py` fakes the slow pipeline |
| **`pytest.raises`** | Check that code fails in the right way. | `test_weighted_median_needs_lines` |
| **`pytest.approx`** | Compare decimals safely (`0.1+0.2` is not exactly `0.3` in computers). | `test_metrics.py` |
| **marker** (`@pytest.mark.slow`) | A label. `pyproject.toml` says skip `slow` by default; `pytest -m slow` runs only those. | `test_integration.py`, `test_leaks.py` |
| **`xfail`** | "This should fail today; we know why." | `test_textutil.py` |
| **FastAPI `TestClient`** | Pretend to be a browser, with no real server. | `test_api.py` |

### Every test file

| File | What it protects | Idea it teaches |
|---|---|---|
| `conftest.py` | Not tests. Shared fixtures: `fixtures_dir`, `make_line`, and `fake_page` (a tiny two-story page built from 15 fake lines). pytest finds it automatically. | Fixtures, scope |
| `test_quality.py` | The path chooser: real English passes; control-character garbage fails; "looks printable but isn't English" fails; empty input is safe. | `parametrize`, edge cases |
| `test_textutil.py` | Joining lines, hyphen repair. | `parametrize`, `xfail` |
| `test_layout.py` | The brain: body size, headline grouping, sub-headlines, ownership, reading order, "a masthead with no body is not a story". Mostly uses `fake_page`, so it needs **no PDF and no OCR**. | Testing logic with fake data |
| `test_summarize.py` | Summaries keep original order, never invent sentences, handle empty text; byline stripping. | Testing properties, not exact text |
| `test_metrics.py` | The measuring tools themselves, plus `split_on_gaps`. | Plain `assert`, `approx` |
| `test_api.py` | Missing file -> 400, non-PDF -> 400, bad page list -> 400, too big -> 413, crash -> 422 **and temp file deleted**, two uploads never share a temp file. | `monkeypatch`, `test_client` |
| `test_debug.py` | The overlay helpers: size classes at the boundaries, every line gets a role, counts add up; one test makes real pictures into a `tmp_path` folder. | `tmp_path` |
| `test_integration.py` | Real sample PDFs: IE page 1 uses `hybrid`; page 5 finds exactly 3 stories; Times City is a scan; slow golden tests compare OCR headlines to human-read ones. | Fast vs slow, golden tests |
| `test_leaks.py` | Text leaking between stories (see below). | Regression tests, red-green, module fixtures |

### Why some tests have "Regression" in them
Each one pins a real bug we hit, so it cannot silently return:
- giant drop-cap "E" read as a headline
- page header "MAHARASHTRA" swallowing a story's headline
- Judge byline stolen by the story above
- two uploads overwriting `temp.pdf` (old code)

### The red-green cycle (how we just fixed the leaks)
1. **Red**: we wrote `test_leaks.py` *first*, from the leaks in your JSON. It failed (it could not
   even import functions that did not exist yet).
2. **Green**: we wrote the minimum code to make it pass (font family, column slots, masking OCR).
3. **Refactor / check**: we ran everything, then compared real output to what you had pasted.
That order is called test-driven development (TDD). It forces you to define "correct" before coding.

### Commands
```bash
pytest                         # all fast tests (about 1 second)
pytest -m slow                 # real OCR tests (minutes)
pytest tests/test_layout.py -v # one file, show every test name
pytest -k judge                # only tests with "judge" in the name
pytest -x                      # stop at the first failure
pytest --lf                    # rerun only what failed last time
pytest --cov=pipeline          # which lines of code do tests actually run?
```

---

## Part 6: What is still wrong (honest list)

1. **Pull-quotes and boxes set in the body font** stay inside a story (for example the "ONLY 2,000
   of the 10,500..." quote in the Adopt WHO story). A font rule cannot catch them. Fix: detect
   drawn rectangles/backgrounds.
2. **Some wrap-around text still mixes** ("violence in the whose wife Was state" in the Kargil story).
3. **OCR drops spaces** in small text ("Regimentas a soldier").
4. **Scans** (Times City, Bombay Times) are weak: ads look like headlines, boxes swallow whole
   pages. Needs real column and region detection.
5. **Ads are not classified yet.** Everything says `"type": "news"`.
6. **Summaries** are the baseline scorer and will often miss the key facts.

## Part 7: Suggested way to learn from this

1. Run `pytest -v` and read the names of the tests. They read like a list of promises.
2. Open `layout.py` and `test_layout.py` side by side. For each function, find its tests.
3. Break something on purpose: change `0.3` to `0.9` in `assign_body_lines` and see which tests fail.
   Which test caught it? That is what tests are *for*.
4. Do the four exercises in `README.md`.
5. Pick one remaining problem from Part 6, write a **failing test first**, then fix it.

---

## Part 8: The safety net (how we keep a growing project under control)

The project will get much bigger: a web API, a database, a job queue, machine learning. The danger
is not the size. The danger is **not knowing what broke**. So before adding anything, we built a
small safety net that answers three different questions, each with its own tool.

### The three questions

| Tool | Question it answers | What it reads | Example of what it catches |
|---|---|---|---|
| **ruff** (lint) | Is the code written safely and tidily? | the source text, without running it | a variable assigned and never used; an import nobody needs; `zip()` that would silently drop items |
| **mypy** (types) | Do the type hints agree with how values are really used? | the hints like `x: int`, without running it | passing a string where a number is expected; a value that might be `None` used as text |
| **pytest** (tests) | Does the program still **behave** the way we decided? | runs the code against examples | the hyphen repair stops working; a story's text leaks into its neighbour |

They fail in different ways, so **which one is red tells you where to look**. One command runs all three:

```bash
uv run python scripts/check.py          # a few seconds
uv run python scripts/check.py --all    # plus the slow real-OCR tests
```

Output looks like this (this is the real "known-good" state of the project right now):

```
  PASS  lint   (ruff,  0.0s)  All checks passed!
  PASS  types  (mypy,  0.3s)  Success: no issues found in 13 source files
  PASS  tests  (pytest,  3.3s)  100 passed, 8 deselected, 1 xfailed
        coverage: 83%
```

**"Perfect condition" is defined**: 100 passed, 1 expected failure (`xfailed`), all three PASS.
If a number changes, something changed. 8 *deselected* are the slow tests, skipped on purpose.

### How to read a failure

| You see | Meaning | First move |
|---|---|---|
| `FAIL lint` only | The code probably still works, but something is sloppy or risky | Read the rule name (e.g. `F841`); `uv run ruff check . --fix` repairs many automatically |
| `FAIL types` only | A value is used in a way its hint says is wrong; may be a real bug, may be a wrong hint | Read the file and line; decide whether the hint or the code is wrong |
| `FAIL tests` only | Behaviour changed | Run just that test with `uv run pytest -x -k name -v`; compare expected and actual |
| Several `FAIL` | Often one root cause | Fix in this order: tests, then types, then lint |
| `xfailed` | A test we **expect** to fail (a known limit, written in its reason text) | Nothing. If it turns into `xpassed`, the limit was fixed: promote it to a normal test |

### `pyproject.toml`: one file for all settings

Before, settings were spread over `requirements.txt` and `pytest.ini`. Now one file, in sections:

| Section | What it does |
|---|---|
| `[project]` `dependencies` | libraries the program needs **to run** (PyMuPDF, Tesseract wrapper, Pillow, FastAPI, uvicorn) |
| `[dependency-groups]` `dev` | libraries only **we** need (pytest, ruff, mypy); never needed by someone just running the program |
| `[tool.ruff.lint]` | which families of rules to apply (`E`/`W` style, `F` real errors, `I` import order, `B` likely bugs, `UP` modern syntax, `SIM` simplifications) |
| `[tool.mypy]` | `check_untyped_defs` also checks functions that have no hints; `warn_unused_ignores` stops stale `# type: ignore` comments piling up |
| `[tool.pytest.ini_options]` | `-m 'not slow'` skips slow OCR tests unless you ask; `--strict-markers` turns a typo in a marker name into an error instead of a silently skipped test |
| `[tool.coverage.run]` | measure only our own code (`pipeline`, `eval`), not the libraries |

Two rules are deliberately **switched off**, with the reason written next to them in the file:
`E501` (line length) because we do not auto-format yet, and `E741` because `l` means "line"
everywhere in the geometry code and renaming 37 uses would add risk for no benefit.

### `uv`: Python and its libraries

- A **virtual environment** (the `.venv/` folder) is a private copy of Python plus this project's
  libraries, so this project cannot disturb other projects and vice versa. Never commit it.
- `uv sync` builds `.venv/` from `pyproject.toml` and `uv.lock`. It downloads the right Python too.
- `uv run <command>` runs a command **inside** that environment. No activating, no "which Python is this?".
- `uv add <package>` adds a library to `pyproject.toml` and updates the lock file in one step.
- **`uv.lock`** records the exact version of every library, including libraries of libraries. This is
  what makes "it works on my machine" also true on your other laptop, in CI and in Docker.
  Commit it. Never edit it by hand.

Why not just `pip install -r requirements.txt`? That file had six unpinned lines; a new release of any
library could silently change behaviour next month. The lock file prevents that.

### What we changed in the existing code (and why it is safe)

The first run of ruff and mypy found 8 + 8 findings. We fixed them without changing behaviour; the
100 tests were re-run and give the same result as before.

| Where | Finding | Fix |
|---|---|---|
| `layout.py` | variable `g` assigned, never used | removed |
| `layout.py` | `zip(headlines, bodies)` silently stops at the shorter list | `strict=True`: a length mismatch now raises an error instead of hiding a bug |
| `layout.py` | `join_lines([l.text ...])`: text is `str or None` | inside the "all texts exist" guard we use `l.text or ""`, which tells the type checker what we already know |
| `layout.py` | font width totals typed as whole numbers but they are decimals | `dict[str, float]` |
| `extract.py` | Pillow wants a tuple `(w, h)`, not a list; old `Image.LANCZOS` name | tuple; `Image.Resampling.LANCZOS` |
| `run.py` | a helper function defined in a loop uses the loop variable (a classic source of bugs) | passed explicitly as a default argument |
| `app.py` | Flask's type does not declare `sort_keys` | temporary `# type: ignore`; the whole file was replaced by FastAPI in Part 9 |
| tests | unsorted/unused imports | fixed automatically by `ruff --fix` |

### Three house rules

1. **Never commit red.** Run `scripts/check.py` before every commit. (Since Part 10, pre-commit does the
   quick checks automatically and GitHub Actions does everything again on every push.)
2. **New code gets a test in the same change.** A bug fix gets a regression test first, red, then the fix, green.
3. **The bar only goes up (the "ratchet").** Today mypy is moderate. New packages (the API in the next
   step) will use the strict setting `disallow_untyped_defs`. Old code is tightened a module at a time,
   never loosened.


---

## Part 9: The API layer (Flask replaced by FastAPI)

### Words you need

| Word | Plain meaning |
|---|---|
| **API** | A program other programs talk to over the network. Ours: "send me a PDF, I send back JSON". |
| **HTTP, route, status code** | HTTP is the conversation format. A *route* is an address (`POST /process_pdf`). The *status code* is the one-number verdict: 200 fine, 400 your mistake, 413 too big, 422 could not process, 503 busy. |
| **FastAPI** | The framework: it receives HTTP requests and calls our Python functions. Chosen because it validates input and output from type hints and writes the documentation by itself. |
| **uvicorn** | The server program that listens on a port and hands requests to FastAPI. FastAPI is the application; uvicorn is what runs it. |
| **Pydantic** | A library that checks data against a description written as a Python class (a *model*) and refuses data that does not fit. |
| **OpenAPI / Swagger (`/docs`)** | A standard machine-readable description of an API. FastAPI builds it from our code, and `/docs` shows it as a page where you can try every endpoint. It cannot go out of date because it IS the code. |

### Files in `api/` (one job each, so a failure points at one file)

| File | Job | Open it when... |
|---|---|---|
| `main.py` | the routes only: `/`, `/health`, `/process_pdf` | a URL answers the wrong thing |
| `schemas.py` | the JSON contract as Pydantic models | the response shape is wrong or a field is missing |
| `uploads.py` | check it is a PDF, parse `pages`, save to a unique temp file and always delete it, enforce the size limit | uploads are rejected or temp files pile up |
| `errors.py` | one error shape, `{"error": "..."}`, for every failure | an error looks different from the others |
| `health.py` | "can this machine do OCR?" (is Tesseract found?) | `/health` says `degraded` |
| `settings.py` | configuration from environment variables | you want to change the size limit or concurrency |

The rule of the package: **no newspaper logic in `api/`**. It validates, calls `pipeline/`, and returns.

### Decisions worth knowing (each is also an interview answer)

1. **The route is a plain `def`, not `async def`.** Processing blocks for a minute or more. An `async def`
   route that blocks freezes the whole server, because all async routes share one thread. A plain `def`
   route is run by FastAPI in a worker thread, so other requests (like `/health`) still answer.
2. **Only one PDF is processed at a time** (`NEWSPAPER_MAX_CONCURRENT_JOBS=1`). OCR needs a lot of memory
   and CPU. Without a limit, five simultaneous uploads would start five OCR jobs and crash an 8 GB laptop.
   A second request now gets `503 busy`. The semaphore that does this is released in a `finally`, so even a
   crash cannot leave the server stuck (there is a test for exactly that). This is a stopgap: in the next
   sprint a job queue replaces "try again" with "your job is queued".
3. **Models validate our own output.** `ProcessResponse.model_validate(result)` checks what the pipeline
   returned before it reaches a client. Two tests protect the contract: one asserts the model fields equal
   `Article.to_dict()` keys in the same order, one pushes real pages through the models. Rename a field
   in the pipeline and a test fails and tells you.
4. **Size is checked twice.** The `Content-Length` header is checked first, cheaply, before the body is
   read. But a client can lie or omit it, so the size is also counted while copying to disk.
5. **One error shape.** FastAPI's own errors (404, 405) normally look different from ours. `errors.py`
   makes every error `{"error": "..."}`, and a test checks it.
6. **Settings from the environment** (`pydantic-settings`), so Docker, CI and your laptop can differ
   without code changes.

### Strict typing starts here (the ratchet from Part 8)

`pyproject.toml` now holds `api.*` to the strict mypy standard: every function needs type hints
(`disallow_untyped_defs`). `pipeline/` and `eval/` keep the moderate setting until we tighten them.

### What changed in the tests

The 9 Flask tests were ported one-to-one (same cases, same expectations; only the client changed) and 14
new tests were added: health, busy server and recovery, size limit when the header lies, temp file removed
after an oversized upload, one error shape, OpenAPI documents all status codes, settings from environment,
and the four contract tests. Total: 114 fast tests (was 100). The dev dependency `httpx2` is the HTTP
client the test client uses.

### How to run and what you should see

```
uv run uvicorn api.main:app --reload       # --reload restarts the server when you save a file
```

Open `http://127.0.0.1:8000/docs`, click `POST /process_pdf`, "Try it out", pick a PDF, fill `pages` with `1`.
`GET /health` should answer `{"status":"ok","tesseract":"5.5.3"}`.


---

## Part 10: Automatic checks (pre-commit and CI)

### The idea: catch every problem at the earliest, cheapest place

A mistake costs more the later it is found. Typing an unused import and seeing a red mark costs
seconds. Finding it after the code is on GitHub and someone else has built on it costs hours. So we
put a check at every stage, each one slower and stricter than the last:

| Stage | Runs when | Takes | Protects against | Can you skip it? |
|---|---|---|---|---|
| `scripts/check.py` | when you run it | ~15 s | anything, on demand | it is optional |
| **pre-commit** hooks | every `git commit` | ~5 s | sloppy code entering history | yes (`--no-verify`) |
| **pre-push** hook | every `git push` | ~10 s | broken behaviour leaving your laptop | yes (`--no-verify`) |
| **CI** (GitHub Actions) | every push and pull request | ~2 min | "works on my machine", skipped hooks | **no**: it runs on GitHub's machines |

The last row is the important one: laptop checks are a *convenience* (fast feedback); CI is the
*guarantee*, because nobody can bypass it.

### Words you need

| Word | Plain meaning |
|---|---|
| **git hook** | A small script that git runs automatically at an event (before a commit, before a push). They live in `.git/hooks/`, which is **not** part of the repository, so each fresh clone must install them again. |
| **pre-commit** (the tool) | Manages hooks for you: reads `.pre-commit-config.yaml`, installs the hook scripts, runs the checks, and downloads other people's checks. |
| **CI (continuous integration)** | A robot that runs your checks on a clean computer every time code is pushed, and reports PASS or FAIL next to the commit. |
| **GitHub Actions** | GitHub's CI service. Configured by YAML files in `.github/workflows/`. |
| **workflow / job / step** | A workflow is one YAML file. It has jobs (each runs on its own fresh machine). A job is a list of steps (a shell command, or a reusable *action*). |
| **runner** | The machine that runs a job. `ubuntu-latest` = a fresh Linux virtual machine, thrown away afterwards. |
| **action** | A reusable step written by someone else, referenced as `owner/name@version` (for example `actions/checkout`). |

### `.pre-commit-config.yaml`, hook by hook

| Hook | Does | Why |
|---|---|---|
| `trailing-whitespace`, `end-of-file-fixer` | remove invisible spaces; make files end with one newline | noisy diffs and merge conflicts come from these. **It already found one in `api/uploads.py` the first time it ran.** |
| `check-yaml`, `check-toml` | the config files parse | a typo in `ci.yml` would otherwise only show up after pushing |
| `check-merge-conflict` | no leftover `<<<<<<<` markers | |
| `check-added-large-files` | nothing over 1 MB | keeps accidental PDFs and data dumps out |
| `no-sample-pdfs` (ours) | refuses any `.pdf` | `.gitignore` can be bypassed with `git add -f`; this cannot. It guards the copyright decision |
| `ruff` (ours) | lint, with `--fix` | same rules as `check.py` |
| `mypy` (ours) | types | same rules as `check.py` |
| `pytest-fast` (ours) | the fast tests, **on push only** | slower than the rest, so it waits for `git push` (`stages: [pre-push]`) |

Settings worth understanding:

- **`repo: local` + `language: system` + `entry: uv run ...`**: our own hooks call the tools through `uv run`, so they use the exact versions pinned in `uv.lock`. If the hooks carried their own copy of ruff, the hook and `check.py` could disagree. One source of truth.
- **`rev: v6.0.0`**: the downloaded hook collection is pinned to a version, so its behaviour cannot change under you. `uv run pre-commit autoupdate` moves it forward deliberately.
- **`pass_filenames: false`** (mypy, pytest): they must look at the whole project, not just the changed files.
- **`default_install_hook_types`**: lets one command, `uv run pre-commit install`, set up both the commit and push hooks.

**When a hook "fails" because it fixed a file** (whitespace, `ruff --fix`): that is normal. The commit is refused, the file is already corrected, you run `git add` on it again and commit again.

I tested all of this against real git: a forced PDF was refused, an unused import was refused, a
change that broke 3 tests was refused on `git push`, and after reverting it the push went through.

### `.github/workflows/ci.yml`, line by line (the ideas, not the syntax)

| Piece | Meaning |
|---|---|
| `on: push (main), pull_request` | when to run |
| `concurrency ... cancel-in-progress` | if you push twice quickly, the older run is cancelled; no wasted minutes |
| `permissions: contents: read` | **least privilege**: this workflow can read the code and nothing else, so even a compromised step cannot change your repository |
| `timeout-minutes: 15` | a hung job cannot run for hours |
| `actions/checkout@v5` | downloads your code onto the fresh runner (it starts empty) |
| `apt-get install tesseract-ocr` | the OCR *program* is not a Python package, so the clean machine needs it installed (same as you did on Windows) |
| `astral-sh/setup-uv@07a047e...  # v10.3.2` | installs uv. **Pinned to an exact commit**, not a tag: tags can be moved later, commits cannot, so a hijacked third-party action cannot change what runs. The comment tells humans which release it is |
| `enable-cache: true` | keeps downloaded libraries between runs; later runs are much faster |
| `uv sync --locked` | install exactly what `uv.lock` says, and **fail** if `uv.lock` and `pyproject.toml` disagree (catches "I changed a dependency but forgot to update the lock") |
| pre-commit step with `SKIP: ruff,mypy` | runs the hygiene hooks; ruff and mypy are skipped here only because the next step runs them |
| `uv run python scripts/check.py` | the same single command you run locally. Local and CI agree because they run the same thing |

`.github/dependabot.yml` makes GitHub open a pull request when a newer version of a GitHub Action or
a library exists (weekly), so versions never go stale silently. CI then tests that pull request.

### Two files that make everything reproducible

- **`.python-version`** (contains `3.12`): uv, CI and later Docker all use the same Python. Without it, CI could pick 3.13 and a bug would appear only there.
- **`.gitattributes`**: tells git how to treat line endings (Windows `CRLF` versus Linux `LF`) and that PDFs and images are binary. It removes the "LF will be replaced by CRLF" warnings and stops line endings from showing up as fake changes.

### What CI will show for this project, and why

On GitHub the sample PDFs do not exist (they are copyrighted and kept local), so the tests that need
them are *skipped*, not failed:

| Where | Result |
|---|---|
| your laptop | 114 passed, 8 deselected, 1 xfailed (with `--all`: 122 passed) |
| GitHub CI (no PDFs) | **106 passed, 8 skipped, 8 deselected, 1 xfailed**, coverage about 64% |

Coverage is lower on CI only because the PDF-based tests are skipped there. So there is deliberately
no minimum-coverage rule yet: it would fail on CI for a reason that is not a bug.

### Reading a red CI run

1. On GitHub open the **Actions** tab and click the failed run, then the red step.
2. The step name tells you the layer: "Hygiene hooks" (file hygiene), or "Lint, types and tests" (then read which of the three lines says FAIL, exactly like locally).
3. If it fails on CI but passes on your laptop, the cause is an *environment difference*: a missing system program, a file that only exists on your disk (a sample PDF!), a different Python version, or a lock file out of date. That is the exact thing CI is there to reveal.

### Honest limits

- The workflow passes the `actionlint` workflow checker, and I ran every step of it on a clean copy without PDFs. It has **not run on GitHub yet**, so the first push is the real test. If it fails, send me the log of the red step.
- CI cannot run the slow real-OCR tests (no PDFs). You run those locally with `check.py --all` before a release.
- The GitHub Action versions (`checkout@v5` and the pinned uv action) were current when I checked; Dependabot will keep them moving.
