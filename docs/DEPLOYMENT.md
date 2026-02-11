# Deployment Guide

Production deployment guide for Orion Agent.

## Deployment Options

| Option | Best For | Complexity |
|--------|----------|------------|
| Local pip install | Development, personal use | Low |
| Docker | Single-server production | Medium |
| Docker Compose | Full stack (API + Web UI) | Medium |
| Kubernetes | Enterprise, high availability | High |

## Docker Deployment

### Single Container (API Server)

```bash
# Build the image
docker build -t orion-agent .

# Run with API keys
docker run -d \
  --name orion-api \
  -p 8001:8001 \
  -e OPENAI_API_KEY=sk-your-key \
  -v orion-data:/root/.orion \
  orion-agent

# Check health
curl http://localhost:8001/health
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install Orion
COPY . .
RUN pip install --no-cache-dir -e ".[all]"

# Expose API port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

# Start API server
CMD ["uvicorn", "orion.api.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Docker Compose (Full Stack)

```yaml
version: '3.8'

services:
  orion-api:
    build: .
    ports:
      - "8001:8001"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ORION_LOG_LEVEL=INFO
    volumes:
      - orion-data:/root/.orion
      - ./workspaces:/workspaces
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  orion-web:
    build: ./orion-web
    ports:
      - "3001:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://orion-api:8001
      - NEXT_PUBLIC_WS_URL=ws://orion-api:8001/ws/chat
    depends_on:
      orion-api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  orion-data:
```

**Start:**
```bash
docker-compose up -d
```

**Monitor:**
```bash
docker-compose logs -f orion-api
```

## Production Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...          # Or other LLM provider key

# Recommended
ORION_LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
ORION_MODE=safe                # Default governance mode

# API Server
ORION_API_HOST=0.0.0.0        # Bind address
ORION_API_PORT=8001            # Port
ORION_API_WORKERS=4            # Uvicorn workers

# Security
ORION_AUTH_TOKEN=...           # API authentication token
ORION_RATE_LIMIT=60            # Requests per minute
ORION_CORS_ORIGINS=https://your-domain.com
```

### Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl;
    server_name orion.your-domain.com;

    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;

    # API endpoints
    location /api/ {
        proxy_pass http://localhost:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8001/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    # Web UI
    location / {
        proxy_pass http://localhost:3001/;
        proxy_set_header Host $host;
    }
}
```

## Monitoring

### Health Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /health` | Basic health check | `{"status": "healthy", "version": "7.1.0"}` |
| `GET /ready` | Readiness probe (K8s) | `{"ready": true}` |
| `GET /live` | Liveness probe (K8s) | `{"alive": true}` |

### Metrics

Prometheus-compatible metrics available at `/metrics`:

- `orion_requests_total` -- Total request count
- `orion_request_duration_seconds` -- Request latency histogram
- `orion_active_connections` -- Current WebSocket connections
- `orion_llm_calls_total` -- LLM API call count
- `orion_memory_patterns_total` -- Memory pattern count

### Logging

Production logging configuration:
```yaml
logging:
  level: INFO
  structured: true        # JSON format for log aggregation
  file: /var/log/orion/orion.log
  max_size: 50MB
  backup_count: 10
```

Structured log example:
```json
{
  "timestamp": "2025-02-10T14:23:45Z",
  "level": "INFO",
  "correlation_id": "abc-123",
  "component": "aegis",
  "event": "validation_pass",
  "details": {
    "action": "modify",
    "path": "src/main.py",
    "mode": "pro"
  }
}
```

## Scaling

### Horizontal Scaling

Orion's API server is stateless (memory is file-based), so you can run multiple instances behind a load balancer:

```yaml
# docker-compose scale
docker-compose up -d --scale orion-api=3
```

**Considerations:**
- Memory (Tier 2/3) is stored on disk -- use shared volumes or NFS
- WebSocket connections are stateful -- use sticky sessions
- Rate limiting is per-instance -- adjust limits accordingly

### Resource Requirements

| Deployment | CPU | RAM | Disk |
|-----------|-----|-----|------|
| Minimal (1 user) | 1 core | 512MB | 1GB |
| Standard (5 users) | 2 cores | 2GB | 5GB |
| Production (20+ users) | 4 cores | 4GB | 20GB |

## Backup and Restore

### What to Back Up

| Data | Location | Frequency |
|------|----------|-----------|
| Configuration | `~/.orion/config.yaml` | On change |
| Credentials | `~/.orion/credentials.enc` | On change |
| Institutional memory | `~/.orion/institutional.db` | Daily |
| Project memory | `.orion/memory/` per workspace | Daily |
| Logs | `~/.orion/logs/` | Weekly |

### Backup Script

```bash
#!/bin/bash
BACKUP_DIR="/backups/orion/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Config and credentials
cp ~/.orion/config.yaml "$BACKUP_DIR/"
cp ~/.orion/credentials.enc "$BACKUP_DIR/"

# Institutional memory
cp ~/.orion/institutional.db "$BACKUP_DIR/"

# Compress
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"
```

### Restore

```bash
tar -xzf /backups/orion/20250210.tar.gz -C /tmp/
cp /tmp/20250210/* ~/.orion/
```

## Troubleshooting Deployment

### Container won't start

Check logs:
```bash
docker logs orion-api
```

Common issues:
- Missing API key environment variable
- Port already in use
- Insufficient permissions on volume mount

### WebSocket disconnects

- Check nginx timeout settings (`proxy_read_timeout`)
- Ensure WebSocket upgrade headers are passed
- Check for proxy buffering issues

### High memory usage

- Reduce `max_tokens` in configuration
- Limit concurrent connections
- Monitor institutional memory database size

---

**Next:** [Configuration](CONFIGURATION.md) | [Security](SECURITY.md)
