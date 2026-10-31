# Blender 5.1, the oldest supported release, bundles Python 3.13.
ARG PYTHON_IMAGE=docker.io/library/python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base

# Use the image's Python rather than downloading one, and keep the venv
# outside /app so the source copy cannot shadow it.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

FROM base AS dependencies

# Locked, hash-verified development tools; the add-on itself needs only
# Blender's Python. uv runs from a bind mount, so it stays out of the image.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv sync --locked --only-dev --no-install-project --no-build \
    && uv pip check --python /opt/venv

# Tests stub bpy, so they run without Blender.
FROM dependencies AS checks

COPY __init__.py ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/
RUN python -m ruff check --no-cache . \
    && python -m ruff format --no-cache --check . \
    && python -m pytest -v -p no:cacheprovider
