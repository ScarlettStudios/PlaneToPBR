# Blender 5.1, the oldest supported release, bundles Python 3.13.
ARG PYTHON_IMAGE=docker.io/library/python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

FROM base AS dependencies

# Hash-pinned development tools; the add-on itself needs only Blender's Python.
# uv runs from a bind mount, so neither it nor pip ends up in the venv.
COPY requirements-dev.txt ./
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    uv venv --no-cache /opt/venv \
    && uv pip install --no-cache --python /opt/venv --require-hashes \
        --only-binary=:all: -r requirements-dev.txt \
    && uv pip check --python /opt/venv

# Tests stub bpy, so they run without Blender.
FROM dependencies AS checks

COPY ruff.toml pytest.ini __init__.py ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/
RUN python -m ruff check --no-cache . \
    && python -m ruff format --no-cache --check . \
    && python -m pytest -v -p no:cacheprovider
