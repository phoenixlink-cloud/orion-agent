#!/usr/bin/env python3
"""
ORION — Unified Launcher (v6.4.0)

Single entry point for all Orion modes:
    python orion.py              # Interactive menu
    python orion.py cli          # CLI mode (terminal interface)
    python orion.py web          # Web UI mode (browser interface)
    python orion.py api          # API server only (for development)

This replaces all other startup scripts for a clean user experience.
"""

import sys
import os
import socket
import subprocess
import threading
import webbrowser
import json
import time
import atexit
from pathlib import Path
from typing import Optional

# Ensure imports work
ORION_DIR = Path(__file__).parent
SRC_DIR = ORION_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

# =============================================================================
# CONFIGURATION
# =============================================================================

RUNTIME_CONFIG_PATH = Path.home() / ".orion" / "runtime.json"
DEFAULT_API_PORT = 8000
DEFAULT_WEB_PORT = 3001


def find_available_port(start_port: int, max_attempts: int = 100) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports in range {start_port}-{start_port + max_attempts}")


def save_runtime_config(api_port: int, web_port: int) -> dict:
    """Save runtime configuration."""
    RUNTIME_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "api_port": api_port,
        "web_port": web_port,
        "api_url": f"http://localhost:{api_port}",
        "web_url": f"http://localhost:{web_port}",
        "pid": os.getpid(),
        "version": "6.4.0",
    }
    with open(RUNTIME_CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)
    return config


def cleanup_runtime_config():
    """Remove runtime config on exit."""
    try:
        if RUNTIME_CONFIG_PATH.exists():
            RUNTIME_CONFIG_PATH.unlink()
    except Exception:
        pass


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return False
    except OSError:
        return True


# =============================================================================
# BANNER
# =============================================================================

def print_banner():
    """Print Orion banner."""
    print()
    print("  ╔═══════════════════════════════════════════════════════╗")
    print("  ║                                                       ║")
    print("  ║     ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗           ║")
    print("  ║    ██╔═══██╗██╔══██╗██║██╔═══██╗████╗  ██║           ║")
    print("  ║    ██║   ██║██████╔╝██║██║   ██║██╔██╗ ██║           ║")
    print("  ║    ██║   ██║██╔══██╗██║██║   ██║██║╚██╗██║           ║")
    print("  ║    ╚██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║           ║")
    print("  ║     ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝           ║")
    print("  ║                                                       ║")
    print("  ║        Governed AI Assistant with AEGIS v6.4.0        ║")
    print("  ║                                                       ║")
    print("  ╚═══════════════════════════════════════════════════════╝")
    print()


def print_menu():
    """Print interactive menu."""
    print("  How would you like to use Orion?")
    print()
    print("    [1]  CLI Mode      - Terminal interface")
    print("    [2]  Web UI Mode   - Browser interface (recommended)")
    print("    [3]  API Only      - Start API server for development")
    print("    [4]  Exit")
    print()


# =============================================================================
# MODE: CLI
# =============================================================================

def run_cli_mode():
    """Run the CLI interface."""
    print("\n  Starting Orion CLI v6.4.0...")
    print("  Type '/help' for commands, '/quit' to exit.\n")

    try:
        from orion.cli.repl import start_repl
        start_repl()
    except ImportError as e:
        print(f"\n  CLI module not available: {e}")
        print("  Make sure orion-agent is installed: pip install -e .")
        input("\n  Press Enter to exit...")
    except KeyboardInterrupt:
        print("\n\n  Goodbye!")
    except Exception as e:
        print(f"\n  Error: {e}")
        input("\n  Press Enter to exit...")


# =============================================================================
# MODE: WEB UI
# =============================================================================

def start_api_server_thread(port: int) -> threading.Thread:
    """Start API server in background thread."""
    def run():
        try:
            import uvicorn
            from orion.api.server import app
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        except Exception as e:
            print(f"  API Server Error: {e}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def start_web_server(port: int, api_port: int) -> Optional[subprocess.Popen]:
    """Start Next.js web server."""
    web_dir = ORION_DIR / "orion-web"

    if not web_dir.exists():
        print(f"  Error: Web UI not found at {web_dir}")
        print("  The web UI directory 'orion-web' must exist alongside orion.py")
        return None

    # Set environment
    env = os.environ.copy()
    env["NEXT_PUBLIC_API_URL"] = f"http://localhost:{api_port}"
    env["PORT"] = str(port)

    # Check for node_modules
    if not (web_dir / "node_modules").exists():
        print("  Installing web UI dependencies (first time only)...")
        result = subprocess.run(
            "npm install",
            cwd=web_dir,
            shell=True,
            capture_output=True
        )
        if result.returncode != 0:
            print("  Error installing dependencies. Is Node.js installed?")
            return None

    # Start Next.js
    if sys.platform == "win32":
        process = subprocess.Popen(
            f"cmd /c npm run dev",
            cwd=web_dir,
            shell=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=web_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return process


def run_web_mode():
    """Run web UI mode with API server."""
    api_already_running = is_port_in_use(DEFAULT_API_PORT)
    web_already_running = is_port_in_use(DEFAULT_WEB_PORT)

    if api_already_running and web_already_running:
        print(f"\n  Orion is already running!")
        print(f"  ─────────────────────────────────────")
        print(f"  API Server:  http://localhost:{DEFAULT_API_PORT}")
        print(f"  Web UI:      http://localhost:{DEFAULT_WEB_PORT}")
        print(f"  ─────────────────────────────────────")
        print(f"\n  Opening browser...")
        webbrowser.open(f"http://localhost:{DEFAULT_WEB_PORT}")
        input("\n  Press Enter to exit...")
        return

    api_port = DEFAULT_API_PORT if not api_already_running else find_available_port(DEFAULT_API_PORT)
    web_port = DEFAULT_WEB_PORT if not web_already_running else find_available_port(DEFAULT_WEB_PORT)

    save_runtime_config(api_port, web_port)
    atexit.register(cleanup_runtime_config)

    print(f"\n  Starting Orion Web UI...")
    print(f"  ─────────────────────────────────────")
    print(f"  API Server:  http://localhost:{api_port}")
    print(f"  Web UI:      http://localhost:{web_port}")
    print(f"  ─────────────────────────────────────")

    # Start API server
    print("  [1/2] Starting API server...")
    api_thread = start_api_server_thread(api_port)
    time.sleep(1)

    # Start web server
    print("  [2/2] Starting web server...")
    web_process = start_web_server(web_port, api_port)

    if not web_process:
        print("\n  Failed to start web server.")
        print("  Make sure Node.js is installed: https://nodejs.org")
        input("\n  Press Enter to exit...")
        return

    # Wait for web server to be ready
    print("  Waiting for servers to start", end="", flush=True)
    for i in range(30):
        if is_port_in_use(web_port):
            break
        print(".", end="", flush=True)
        time.sleep(1)
    print()

    if not is_port_in_use(web_port):
        print("\n  Warning: Web server may not have started properly.")
        print("  Try running manually: cd orion-web && npm run dev")

    print(f"\n  Orion is running!")
    print(f"  Opening browser to http://localhost:{web_port}")
    print()
    print("  ─────────────────────────────────────")
    print("  Press Ctrl+C to stop Orion")
    print("  ─────────────────────────────────────")

    webbrowser.open(f"http://localhost:{web_port}")

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\n  Shutting down Orion...")
    finally:
        if web_process:
            web_process.terminate()
            try:
                web_process.wait(timeout=5)
            except Exception:
                web_process.kill()
        print("  Goodbye!")


# =============================================================================
# MODE: API ONLY
# =============================================================================

def run_api_mode():
    """Run API server only (for development)."""
    api_port = find_available_port(DEFAULT_API_PORT)

    save_runtime_config(api_port, 0)
    atexit.register(cleanup_runtime_config)

    print(f"\n  Starting Orion API Server...")
    print(f"  ─────────────────────────────────────")
    print(f"  API Server:  http://localhost:{api_port}")
    print(f"  Health:      http://localhost:{api_port}/health")
    print(f"  Docs:        http://localhost:{api_port}/docs")
    print(f"  ─────────────────────────────────────")
    print()
    print("  Press Ctrl+C to stop")
    print()

    try:
        import uvicorn
        from orion.api.server import app
        uvicorn.run(app, host="127.0.0.1", port=api_port, log_level="info")
    except KeyboardInterrupt:
        print("\n  Goodbye!")
    except ImportError:
        print("  Error: FastAPI/uvicorn not installed.")
        print("  Run: pip install fastapi uvicorn")
        input("\n  Press Enter to exit...")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    print_banner()

    # Check for command line arguments
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

        if mode in ['cli', 'terminal', 'console']:
            run_cli_mode()
        elif mode in ['web', 'ui', 'browser']:
            run_web_mode()
        elif mode in ['api', 'server']:
            run_api_mode()
        elif mode in ['help', '-h', '--help']:
            print("  Usage: python orion.py [mode]")
            print()
            print("  Modes:")
            print("    cli    - Terminal interface")
            print("    web    - Browser interface (recommended)")
            print("    api    - API server only")
            print()
            print("  No arguments = interactive menu")
            print()
        else:
            print(f"  Unknown mode: {mode}")
            print("  Use 'cli', 'web', or 'api'")
        return

    # Interactive menu
    while True:
        print_menu()

        try:
            choice = input("  Enter choice [1-4]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Goodbye!")
            break

        if choice == '1':
            run_cli_mode()
            break
        elif choice == '2':
            run_web_mode()
            break
        elif choice == '3':
            run_api_mode()
            break
        elif choice == '4' or choice.lower() in ['exit', 'quit', 'q']:
            print("\n  Goodbye!")
            break
        else:
            print("\n  Invalid choice. Please enter 1, 2, 3, or 4.\n")


if __name__ == "__main__":
    main()
