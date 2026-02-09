FROM alpine:3.19

RUN apk add --no-cache git curl jq tree grep

WORKDIR /repos

# === PRIMARY TARGETS (coding assistants to audit) ===
RUN git clone --depth 1 https://github.com/cli delegation/cli delegation.git && \
    git clone --depth 1 https://github.com/reference-project.git && \
    git clone --depth 1 https://github.com/anthropics/claude-code.git && \
    git clone --depth 1 https://github.com/OpenHands/OpenHands.git && \
    git clone --depth 1 https://github.com/cline/cline.git

# === REFERENCE PROJECTS (OAuth/integration patterns) ===
RUN git clone --depth 1 https://github.com/open-webui/open-webui.git && \
    git clone --depth 1 https://github.com/nextauthjs/next-auth.git

# Keep container alive
CMD ["tail", "-f", "/dev/null"]
