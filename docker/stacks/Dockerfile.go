# Orion Agent — Go stack image
# Pre-baked with Go 1.22
FROM ubuntu:22.04

LABEL maintainer="Phoenix Link (Pty) Ltd"
LABEL orion.stack="go"

ENV DEBIAN_FRONTEND=noninteractive
ENV GOPATH=/home/orion/go
ENV PATH=$PATH:/usr/local/go/bin:$GOPATH/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    jq \
    make \
    && curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz \
       | tar -C /usr/local -xzf - \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash orion
USER orion
WORKDIR /workspace
