# Orion Agent — Egress Proxy CLI entry point
# Usage: python -m orion.security.egress [--config PATH] [--port PORT]
from orion.security.egress.server import main

if __name__ == "__main__":
    main()
