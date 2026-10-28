# Blender 4.2, the oldest supported release, bundles Python 3.11.
ARG PYTHON_IMAGE=docker.io/library/python:3.11-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

FROM ${PYTHON_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

FROM base AS dependencies

# Hash-pinned development tools; the add-on itself needs only Blender's Python.
RUN python -m venv /opt/venv
COPY requirements-dev.txt ./
RUN python -m pip install --only-binary=:all: -r requirements-dev.txt \
    && python -m pip check

# Tests stub bpy, so they run without Blender.
FROM dependencies AS checks

COPY ruff.toml pytest.ini __init__.py ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/
RUN python -m ruff check --no-cache . \
    && python -m ruff format --no-cache --check . \
    && python -m pytest -v -p no:cacheprovider
