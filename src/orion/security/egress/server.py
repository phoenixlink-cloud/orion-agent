# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Egress proxy CLI entry point.

Starts the egress proxy as a standalone process. Designed to be run
on the HOST side, outside the Docker sandbox.

Usage:
    python -m orion.security.egress.server [--config PATH] [--port PORT] [--audit-log PATH]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from .config import load_config
from .proxy import EgressProxyServer

logger = logging.getLogger("orion.security.egress.server")


def main() -> None:
    """Entry point for the egress proxy server."""
    parser = argparse.ArgumentParser(
        prog="orion-egress-proxy",
        description="Orion Egress Proxy -- The Narrow Door",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to egress_config.yaml (default: ~/.orion/egress_config.yaml)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Proxy listen port (overrides config, default: 8888)",
    )
    parser.add_argument(
        "--audit-log",
        default=None,
        help="Path for audit log file (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load configuration
    config = load_config(args.config)

    # Apply CLI overrides
    if args.port is not None:
        config.proxy_port = args.port
    if args.audit_log is not None:
        config.audit_log_path = args.audit_log

    # Create and start server
    server = EgressProxyServer(config=config)

    # Handle graceful shutdown
    def _shutdown(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Start and block
    logger.info("=" * 60)
    logger.info("Orion Egress Proxy -- The Narrow Door")
    logger.info("=" * 60)
    logger.info("  Port: %d", config.proxy_port)
    logger.info("  Enforce: %s", config.enforce)
    logger.info("  Content inspection: %s", config.content_inspection)
    logger.info("  DNS filtering: %s", config.dns_filtering)
    logger.info(
        "  Domains: %d hardcoded + %d user",
        len(config.get_all_allowed_domains()) - len(config.whitelist),
        len(config.whitelist),
    )
    logger.info("  Audit log: %s", config.audit_log_path)
    logger.info("=" * 60)

    server.start()

    # Block main thread until interrupted
    try:
        signal.pause()
    except AttributeError:
        # signal.pause() not available on Windows -- use a loop
        import time

        while server.is_running:
            time.sleep(1)


if __name__ == "__main__":
    main()
