# Osiris backend — Phase 0 reproducible image.
# Builds a runnable container from a clean clone. Secrets are injected via env at run time
# only (OSIRIS_JWT_SECRET, OSIRIS_WEBHOOK_SECRET, ...) — never baked into the image.

FROM python:3.13-slim AS base

# - No .pyc, unbuffered stdout so logs stream to the container engine immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OSIRIS_ENV=production \
    OSIRIS_LOG_JSON=1

WORKDIR /app

# Install dependencies first for layer caching. Install from the LOCK for an exact closure.
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.lock.txt

# Copy application source. .dockerignore keeps the dev SQLite file, caches, and venv out;
# the entrypoint runs migrations to build a fresh DB on first boot.
COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 osiris \
    && chown -R osiris:osiris /app
USER osiris

EXPOSE 8000

# Liveness/readiness probe hits the Phase 0 /healthz route (DB reachable + migrations current).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

# Apply migrations, then serve. `alembic upgrade head` is idempotent and stamps the DB so
# /healthz reports migrations=current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8000"]
