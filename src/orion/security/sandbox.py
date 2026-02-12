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
"""
Orion Agent -- Docker Sandbox (v7.4.0)

Isolated code execution with resource limits.
Supports Python, Node.js, and shell via Docker containers.

Migrated from Orion_MVP/integrations/docker_sandbox/sandbox_manager.py.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.sandbox")

SANDBOX_CONFIG_PATH = Path.home() / ".orion" / "sandbox_config.json"

LANGUAGE_IMAGES = {
    "python": "python:3.11-slim",
    "python3": "python:3.11-slim",
    "node": "node:20-slim",
    "nodejs": "node:20-slim",
    "javascript": "node:20-slim",
    "bash": "ubuntu:22.04",
    "shell": "ubuntu:22.04",
    "sh": "ubuntu:22.04",
}

LANGUAGE_COMMANDS = {
    "python": ["python3", "-c"],
    "python3": ["python3", "-c"],
    "node": ["node", "-e"],
    "nodejs": ["node", "-e"],
    "javascript": ["node", "-e"],
    "bash": ["bash", "-c"],
    "shell": ["bash", "-c"],
    "sh": ["sh", "-c"],
}


class SandboxManager:
    """
    Manages Docker sandbox containers for Orion.

    Features:
    - Isolated code execution per language
    - Resource limits (CPU, memory, timeout)
    - Container lifecycle management
    - Execution history
    """

    CONTAINER_PREFIX = "orion-sandbox-"

    def __init__(self):
        self._memory_limit: str = "256m"
        self._cpu_limit: str = "1.0"
        self._default_timeout: int = 30
        self._network_enabled: bool = False
        self._history: list[dict[str, Any]] = []
        self._load_config()

    def _load_config(self):
        if SANDBOX_CONFIG_PATH.exists():
            try:
                with open(SANDBOX_CONFIG_PATH) as f:
                    data = json.load(f)
                self._memory_limit = data.get("memory_limit", self._memory_limit)
                self._cpu_limit = data.get("cpu_limit", self._cpu_limit)
                self._default_timeout = data.get("default_timeout", self._default_timeout)
                self._network_enabled = data.get("network_enabled", self._network_enabled)
            except Exception:
                pass

    def _save_config(self):
        SANDBOX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "memory_limit": self._memory_limit,
            "cpu_limit": self._cpu_limit,
            "default_timeout": self._default_timeout,
            "network_enabled": self._network_enabled,
        }
        with open(SANDBOX_CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    # ── Docker availability ──────────────────────────────────────────────

    def is_docker_available(self) -> bool:
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ── Code execution ───────────────────────────────────────────────────

    def run_code(
        self, code: str, language: str = "python", timeout: int | None = None
    ) -> dict[str, Any]:
        """Run code in an isolated Docker container."""
        if not code.strip():
            return {"success": False, "error": "No code provided"}

        lang = language.lower()
        if lang not in LANGUAGE_IMAGES:
            return {
                "success": False,
                "error": f"Unsupported language: {language}. Supported: {sorted(set(LANGUAGE_IMAGES.keys()))}",
            }

        if not self.is_docker_available():
            return {"success": False, "error": "Docker is not available. Install and start Docker."}

        timeout = timeout or self._default_timeout
        image = LANGUAGE_IMAGES[lang]
        cmd = LANGUAGE_COMMANDS[lang]
        container_name = f"{self.CONTAINER_PREFIX}{int(time.time())}"

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--memory",
            self._memory_limit,
            "--cpus",
            self._cpu_limit,
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
        ]

        if not self._network_enabled:
            docker_cmd.extend(["--network", "none"])

        docker_cmd.extend([image] + cmd + [code])

        start_time = time.time()

        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
            execution_time = time.time() - start_time

            self._history.append(
                {
                    "language": lang,
                    "code_length": len(code),
                    "exit_code": result.returncode,
                    "execution_time": execution_time,
                    "timestamp": time.time(),
                }
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": execution_time,
                "language": lang,
                "container": container_name,
            }
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=5)
            return {
                "success": False,
                "error": f"Execution timed out after {timeout}s",
                "language": lang,
            }
        except FileNotFoundError:
            return {"success": False, "error": "Docker not found in PATH"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Container management ─────────────────────────────────────────────

    def list_containers(self) -> dict[str, Any]:
        if not self.is_docker_available():
            return {"success": False, "error": "Docker not available"}
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={self.CONTAINER_PREFIX}",
                    "--format",
                    "{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            containers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    if len(parts) >= 4:
                        containers.append(
                            {
                                "id": parts[0],
                                "name": parts[1],
                                "status": parts[2],
                                "image": parts[3],
                            }
                        )
            return {"success": True, "containers": containers, "count": len(containers)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup_containers(self) -> dict[str, Any]:
        if not self.is_docker_available():
            return {"success": False, "error": "Docker not available"}
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"name={self.CONTAINER_PREFIX}",
                    "--format",
                    "{{.ID}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            ids = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]
            if not ids:
                return {"success": True, "removed": 0}
            subprocess.run(["docker", "rm", "-f"] + ids, capture_output=True, timeout=30)
            return {"success": True, "removed": len(ids)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Settings ─────────────────────────────────────────────────────────

    def set_memory_limit(self, limit: str) -> dict[str, Any]:
        self._memory_limit = limit
        self._save_config()
        return {"success": True, "memory_limit": limit}

    def set_cpu_limit(self, limit: str) -> dict[str, Any]:
        self._cpu_limit = limit
        self._save_config()
        return {"success": True, "cpu_limit": limit}

    def set_timeout(self, timeout: int) -> dict[str, Any]:
        self._default_timeout = timeout
        self._save_config()
        return {"success": True, "default_timeout": timeout}

    def set_network(self, enabled: bool) -> dict[str, Any]:
        self._network_enabled = enabled
        self._save_config()
        return {"success": True, "network_enabled": enabled}

    # ── Status ───────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        return {
            "docker_available": self.is_docker_available(),
            "memory_limit": self._memory_limit,
            "cpu_limit": self._cpu_limit,
            "default_timeout": self._default_timeout,
            "network_enabled": self._network_enabled,
            "supported_languages": sorted(set(LANGUAGE_IMAGES.keys())),
            "history_count": len(self._history),
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._history[-limit:]


# ── Singleton ────────────────────────────────────────────────────────────

_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager
