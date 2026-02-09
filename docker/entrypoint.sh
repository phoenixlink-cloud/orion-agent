#!/bin/bash
# Orion Agent — Container Entrypoint
#
# Modes:
#   serve    — Start the FastAPI server (default)
#   cli      — Start the interactive CLI REPL
#   --version — Print version and exit
#   *        — Pass through to orion CLI

set -e

case "${1:-serve}" in
    serve|api|server)
        echo "Starting Orion API server on port ${PORT:-8000}..."
        exec python -m uvicorn orion.api.server:app \
            --host 0.0.0.0 \
            --port "${PORT:-8000}" \
            --workers "${WORKERS:-1}" \
            --log-level "${LOG_LEVEL:-info}"
        ;;
    cli|repl)
        exec python -m orion
        ;;
    --version|-v)
        python -c "from orion import __version__; print(f'orion-agent v{__version__}')"
        ;;
    *)
        exec orion "$@"
        ;;
esac
