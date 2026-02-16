---
name: docker-setup
description: "Dockerfile best practices, multi-stage builds, and container configuration"
version: "1.0.0"
author: "Orion"
tags: ["devops", "docker", "containers"]
source: "bundled"
trust_level: "verified"
---

## Dockerfile Best Practices

### 1. Base Image Selection
- Use official images from Docker Hub
- Prefer slim/alpine variants for smaller size
- Pin specific versions (not `latest`)
- For Python: `python:3.12-slim` over `python:3.12`

### 2. Multi-Stage Builds
Use multi-stage builds to keep final images small:
```dockerfile
# Stage 1: Build
FROM node:20-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Production
FROM node:20-slim
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
CMD ["node", "dist/index.js"]
```

### 3. Layer Optimization
- Order instructions from least to most frequently changed
- Copy dependency files before source code
- Combine RUN commands to reduce layers
- Use `.dockerignore` to exclude unnecessary files

### 4. Security
- Run as non-root user: `USER appuser`
- Don't store secrets in the image
- Scan images for vulnerabilities
- Use `--no-install-recommends` for apt packages

### 5. Health Checks
Always include a health check:
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:3000/health || exit 1
```

### 6. Environment Configuration
- Use ENV for build-time defaults
- Use runtime environment variables for secrets
- Document all required environment variables
