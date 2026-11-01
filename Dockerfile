# syntax=docker/dockerfile:1
# Builds the API into a small, non-root image. Explained step by step in GUIDE.md, Part 11.
#
#   docker build -t newspaper-pipeline .
#   docker run --rm -p 8000:8000 newspaper-pipeline        # then open http://127.0.0.1:8000/docs

# ---------- Stage 1: build the Python environment (this stage is thrown away afterwards) ----------
FROM python:3.12-slim AS builder

# uv, copied from its official image (pinned, same version family as on your laptop)
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Copy ONLY the dependency description first. Docker caches each step: as long as these three files
# are unchanged, the slow install below is reused, and editing our own code does not trigger it.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# ---------- Stage 2: the image that actually runs ----------
FROM python:3.12-slim AS runtime

# Tesseract is a program, not a Python package. --no-install-recommends keeps the image small.
# (Not pinning apt package versions on purpose: Debian deletes old versions from its servers,
# so exact pins would make this build fail months from now with no change of ours.)
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Never run as root inside a container: if the app were ever compromised, the damage stays small.
RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY api ./api
COPY pipeline ./pipeline

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER 10001
EXPOSE 8000

# Docker asks this every 30 s. "healthy" only if /health answers with status "ok" (so a missing
# Tesseract shows up as unhealthy). Slim images have no curl, so we use Python itself.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import json,urllib.request,sys; sys.exit(0 if json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=8))['status']=='ok' else 1)"]

# 0.0.0.0 = listen on all addresses INSIDE the container (127.0.0.1 would be unreachable from outside).
# ONE worker on purpose: the "one PDF at a time" guard lives inside the process.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
