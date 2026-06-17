# syntax=docker/dockerfile:1
# ---- Build stage ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy dependency manifests first for a cacheable deps layer.
COPY pyproject.toml uv.lock ./

# Install dependencies (no project code yet, no dev deps).
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and config, then install the project itself.
COPY src/ ./src/
COPY config/ ./config/

RUN uv sync --frozen --no-dev --no-editable

# ---- Runtime stage ----
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy the populated virtualenv and static config from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/config /app/config

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create and switch to a non-root user.
RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8080

ENTRYPOINT ["weatherlink-bridge"]
