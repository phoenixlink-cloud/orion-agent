# Orion Agent — Production Dockerfile
# Multi-stage build for minimal image size
#
# Usage:
#   CLI mode:  docker run orion-agent
#   API mode:  docker run -p 8000:8000 orion-agent serve
#   Custom:    docker run orion-agent --help

FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

# Create a dummy LICENSE if it doesn't exist (for builds without it)
RUN touch LICENSE

RUN pip install --no-cache-dir build && \
    python -m build --wheel

# --- Runtime ---
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r orion && useradd -r -g orion -m orion

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir "/tmp/*.whl[web,security]" 2>/dev/null || \
    pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl

# Copy entrypoint script
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create log and data directories
RUN mkdir -p /home/orion/.orion/logs && chown -R orion:orion /home/orion/.orion

USER orion

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["serve"]
