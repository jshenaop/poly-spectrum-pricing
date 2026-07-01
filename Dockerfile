# ============================================================
# Stage 1: Builder — install -dev packages and compile deps
# ============================================================
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Runtime — slim image, no -dev packages
# ============================================================
FROM python:3.11-slim

# Runtime-only libraries (no headers, no compilers).
# libgdal-dev installs libgdalNN as a dependency — we only need the
# runtime .so files.  Installing the -dev package briefly and then
# removing it is wasteful; instead we install the shared-library
# packages directly.  The exact soname versions depend on Debian
# bookworm (python:3.11-slim base).
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal36 \
        libgeos-c1t64 \
        libproj25 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip/setuptools/wheel to patch CVEs in base image versions
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy compiled Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code, tests, and root conftest
COPY app/ ./app/
COPY tests/ ./tests/
COPY conftest.py ./

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
