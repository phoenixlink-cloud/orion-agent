# Orion Agent — Production Dockerfile
# Multi-stage build for minimal image size

FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir build && \
    python -m build --wheel

# --- Runtime ---
FROM python:3.11-slim

RUN groupadd -r orion && useradd -r -g orion -m orion

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER orion

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

ENTRYPOINT ["orion"]
