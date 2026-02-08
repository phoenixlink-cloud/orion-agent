"""
Orion CLI — Main entry point.

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
