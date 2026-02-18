#!/bin/bash
# Orion Agent — Egress Proxy Entrypoint
#
# Starts the egress proxy service (The Narrow Door).
# This runs on the HOST side, outside Orion's sandbox.
#
# Config is read from /etc/orion/egress_config.yaml (mounted from host)
# Audit logs are written to /var/log/orion/egress_audit.log

set -e

CONFIG_PATH="${EGRESS_CONFIG_PATH:-/etc/orion/egress_config.yaml}"
AUDIT_LOG="${EGRESS_AUDIT_LOG:-/var/log/orion/egress_audit.log}"
PROXY_PORT="${EGRESS_PROXY_PORT:-8888}"

echo "Starting Orion Egress Proxy (The Narrow Door)..."
echo "  Config: ${CONFIG_PATH}"
echo "  Audit log: ${AUDIT_LOG}"
echo "  Port: ${PROXY_PORT}"

exec python -m orion.security.egress.server \
    --config "${CONFIG_PATH}" \
    --port "${PROXY_PORT}" \
    --audit-log "${AUDIT_LOG}"
