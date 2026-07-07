# FIX: C2 - multi-stage build: install deps in `builder`, copy only the venv into
# the final `runtime` image. Smaller image, smaller attack surface (no build-essential,
# no gcc, no pip cache). Runtime runs as non-root `appuser` (uid 1001) and ships a
# HEALTHCHECK so compose/orchestrators can restart a wedged container.

FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Build an isolated venv we can copy wholesale into the runtime stage.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# Optionally copy a hash-pinned lock if it exists (the [k] glob makes the COPY a
# no-op when requirements.lock is absent, instead of failing the build).
COPY requirements.loc[k] .
# Prefer the hash-pinned lock: --require-hashes makes installs reproducible and
# tamper-evident (a substituted/poisoned package fails the sha256 check). Falls
# back to the plain requirements.txt when no lock has been generated yet.
RUN pip install --upgrade pip && \
    if [ -f requirements.lock ]; then \
        pip install --require-hashes -r requirements.lock; \
    else \
        pip install -r requirements.txt; \
    fi


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Runtime deps: only the shared libs the venv's compiled extensions link against
# (libpq for asyncpg, curl for the HEALTHCHECK). No build-essential, no gcc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 appuser \
    && useradd  --system --uid 1001 --gid appuser --home-dir /app --shell /sbin/nologin appuser

WORKDIR /app

# Copy the prebuilt venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Application code, owned by root but world-readable (appuser only needs to read +
# write to media/ + logs/, which we chown below).
COPY --chown=root:appuser . .

RUN mkdir -p media logs && chown -R appuser:appuser media logs

USER appuser

# FIX: C2 - HEALTHCHECK hits /health/ready so compose `healthcheck:` can restart a
# container whose process is up but the DB/Redis connection is dead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/ready || exit 1

# Default command runs the bot; compose overrides for api/worker services.
CMD ["python", "-m", "bot.main"]
