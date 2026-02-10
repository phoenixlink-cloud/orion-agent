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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion CLI -- Main entry point.

Usage:
    orion                    # Interactive REPL
    orion chat "message"     # Single-shot
    orion doctor             # System diagnostics
    orion health             # Integration health
    orion --version          # Version info
"""

import sys
from orion import __version__


def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(f"orion-agent {__version__}")
        return

    from orion.cli.repl import start_repl
    start_repl()


if __name__ == "__main__":
    main()
