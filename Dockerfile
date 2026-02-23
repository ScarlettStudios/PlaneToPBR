# Use slim Python base for small CI image
FROM python:3.11-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system deps (optional but useful)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install test dependencies
RUN pip install --no-cache-dir \
    pytest

# Default command (can be overridden in CI)
CMD ["pytest", "-v"]