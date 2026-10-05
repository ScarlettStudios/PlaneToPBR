FROM docker.io/library/python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS dependencies

COPY requirements.txt requirements-lint.txt ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/python -m pip install -r requirements.txt -r requirements-lint.txt

FROM base AS build

COPY --from=dependencies /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY __init__.py pytest.ini ruff.toml ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/

FROM build AS test

CMD ["python", "-m", "pytest", "-v"]
