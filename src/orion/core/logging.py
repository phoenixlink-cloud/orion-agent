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
Orion Agent -- Live Production Logger (v6.6.0)

The holy grail of logs. Every significant event in Orion's lifecycle is
captured in real-time to a rotating log file that users can tail to
understand exactly what's happening.

LOG LOCATION:
    ~/.orion/logs/orion.log          (current)
    ~/.orion/logs/orion.log.1        (previous rotation)
    ~/.orion/logs/orion.log.2        (etc.)

RULES:
    - Single log file, max 10 MB before rotation
    - Log folder purges oldest files once it exceeds 10 GB
    - Human-readable format with structured JSON fields
    - Every LLM call, route decision, memory event, sandbox action logged
    - Errors include full context for debugging

USAGE:
    from orion.core.logging import get_logger
    log = get_logger()
    log.info("Router", "Classified as FAST_PATH", request="What is Python?")
    log.llm("Builder", model="gpt-4o-mini", tokens=1234, latency_ms=1500)
    log.error("Sandbox", "Docker not available", error=str(e))
"""

import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# =============================================================================
# CONSTANTS
# =============================================================================

MAX_LOG_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per file
MAX_LOG_FOLDER_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB total
LOG_BACKUP_COUNT = 1000  # max rotated files (purge handles the rest)
LOG_DIR = Path.home() / ".orion" / "logs"
LOG_FILE = LOG_DIR / "orion.log"


# =============================================================================
# CUSTOM FORMATTER -- human-readable + structured
# =============================================================================


class OrionLogFormatter(logging.Formatter):
    """
    Format: TIMESTAMP | LEVEL | COMPONENT | MESSAGE | {structured fields}

    Example:
    2026-02-09T17:30:45.123Z | INFO  | Router   | Classified as FAST_PATH | request="What is Python?" complexity=0.2
    2026-02-09T17:30:46.500Z | LLM   | Builder  | Call complete | model=gpt-4o-mini tokens=340 latency_ms=1377
    2026-02-09T17:30:46.501Z | ERROR | Sandbox  | Docker not available | error="connection refused"
    """

    LEVEL_WIDTH = 5
    COMPONENT_WIDTH = 12

    def format(self, record: logging.LogRecord) -> str:
        ts = (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
        )

        level = getattr(record, "orion_level", record.levelname)
        component = getattr(record, "component", "System")
        message = record.getMessage()

        # Structured fields
        fields = getattr(record, "fields", {})
        field_str = ""
        if fields:
            parts = []
            for k, v in fields.items():
                if isinstance(v, str):
                    parts.append(f'{k}="{v}"')
                elif isinstance(v, float):
                    parts.append(f"{k}={v:.3f}")
                else:
                    parts.append(f"{k}={v}")
            field_str = " | " + " ".join(parts)

        return (
            f"{ts} | {level:<{self.LEVEL_WIDTH}} | "
            f"{component:<{self.COMPONENT_WIDTH}} | {message}{field_str}"
        )


# =============================================================================
# FOLDER PURGE -- keep total folder size under 10 GB
# =============================================================================


def _purge_old_logs(log_dir: Path, max_bytes: int = MAX_LOG_FOLDER_BYTES):
    """Delete oldest log files if folder exceeds max_bytes."""
    try:
        log_files = sorted(
            [
                f
                for f in log_dir.iterdir()
                if f.is_file() and f.suffix in (".log", "") or f.name.startswith("orion.log")
            ],
            key=lambda f: f.stat().st_mtime,
        )

        total_size = sum(f.stat().st_size for f in log_files)

        while total_size > max_bytes and len(log_files) > 1:
            oldest = log_files.pop(0)
            total_size -= oldest.stat().st_size
            oldest.unlink()
    except Exception:
        pass


# =============================================================================
# ORION LOGGER
# =============================================================================


class OrionLogger:
    """
    Production-grade logger for Orion.

    Writes to ~/.orion/logs/orion.log with:
    - 10 MB rotation per file
    - 10 GB max folder size (oldest purged)
    - Human-readable format with structured fields
    - Component-tagged entries for filtering
    """

    def __init__(self, project_dir: str | None = None):
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger("orion.live")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        # Remove existing handlers to avoid duplicates
        self._logger.handlers.clear()

        # Primary file handler: ~/.orion/logs/orion.log
        file_handler = logging.handlers.RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=MAX_LOG_FILE_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(OrionLogFormatter())
        self._logger.addHandler(file_handler)

        # Also log to stderr at WARNING+ for immediate visibility
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(OrionLogFormatter())
        self._logger.addHandler(stderr_handler)

        # Session tracking (must be before any self.info() calls)
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._request_count = 0

        # Project-local log mirror: <project>/logs/orion.log
        self._project_log_dir = None
        if project_dir:
            self.add_project_log(project_dir)

        # Purge old logs on startup
        _purge_old_logs(LOG_DIR)

        self.info("System", "Logger initialized", log_file=str(LOG_FILE), session=self._session_id)

    def add_project_log(self, project_dir: str):
        """Add a project-local log mirror at <project>/logs/orion.log."""
        proj_log_dir = Path(project_dir) / "logs"
        proj_log_dir.mkdir(parents=True, exist_ok=True)
        self._project_log_dir = proj_log_dir
        proj_log_file = proj_log_dir / "orion.log"
        proj_handler = logging.handlers.RotatingFileHandler(
            str(proj_log_file),
            maxBytes=MAX_LOG_FILE_BYTES,
            backupCount=5,
            encoding="utf-8",
        )
        proj_handler.setLevel(logging.DEBUG)
        proj_handler.setFormatter(OrionLogFormatter())
        self._logger.addHandler(proj_handler)
        self.info("System", "Project log mirror enabled", project_log=str(proj_log_file))

    def _log(self, level: int, orion_level: str, component: str, message: str, **fields):
        """Core log method."""
        fields["session"] = self._session_id
        record = self._logger.makeRecord(
            name="orion.live",
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.component = component
        record.orion_level = orion_level
        record.fields = fields
        self._logger.handle(record)

    # =========================================================================
    # PUBLIC API -- Standard levels
    # =========================================================================

    def info(self, component: str, message: str, **fields):
        """Log an informational event."""
        self._log(logging.INFO, "INFO", component, message, **fields)

    def warn(self, component: str, message: str, **fields):
        """Log a warning."""
        self._log(logging.WARNING, "WARN", component, message, **fields)

    def error(self, component: str, message: str, **fields):
        """Log an error."""
        self._log(logging.ERROR, "ERROR", component, message, **fields)

    def debug(self, component: str, message: str, **fields):
        """Log a debug event."""
        self._log(logging.DEBUG, "DEBUG", component, message, **fields)

    # =========================================================================
    # PUBLIC API -- Domain-specific log methods
    # =========================================================================

    def llm(
        self,
        component: str,
        model: str = "",
        tokens: int = 0,
        latency_ms: int = 0,
        success: bool = True,
        **fields,
    ):
        """Log an LLM call."""
        fields.update(model=model, tokens=tokens, latency_ms=latency_ms, success=success)
        level = "LLM" if success else "LLM-ERR"
        self._log(logging.INFO, level, component, "LLM call", **fields)

    def route(
        self,
        route_name: str,
        request: str,
        complexity: float = 0,
        risk: str = "",
        latency_ms: int = 0,
        **fields,
    ):
        """Log a routing decision."""
        fields.update(route=route_name, complexity=complexity, risk=risk, latency_ms=latency_ms)
        self._log(
            logging.INFO,
            "ROUTE",
            "Router",
            f"Routed to {route_name}",
            request=request[:100],
            **fields,
        )
        self._request_count += 1

    def memory(
        self, action: str, tier: int = 0, category: str = "", confidence: float = 0, **fields
    ):
        """Log a memory event."""
        fields.update(action=action, tier=tier, category=category, confidence=confidence)
        self._log(logging.INFO, "MEM", "Memory", f"Memory {action}", **fields)

    def sandbox(
        self, action: str, mode: str = "", session_id: str = "", success: bool = True, **fields
    ):
        """Log a sandbox event."""
        fields.update(action=action, mode=mode, sandbox_session=session_id, success=success)
        level = logging.INFO if success else logging.ERROR
        self._log(level, "SAND", "Sandbox", f"Sandbox {action}", **fields)

    def security(self, action: str, passed: bool = True, violations: int = 0, **fields):
        """Log a security/AEGIS event."""
        fields.update(action=action, passed=passed, violations=violations)
        level = logging.INFO if passed else logging.WARNING
        self._log(level, "SEC", "AEGIS", f"Security {action}", **fields)

    def approval(
        self, task_id: str, rating: int, task_type: str = "", promoted: bool = False, **fields
    ):
        """Log user feedback/approval."""
        fields.update(task_id=task_id, rating=rating, task_type=task_type, promoted=promoted)
        self._log(logging.INFO, "APRV", "Feedback", f"User rated {rating}/5", **fields)

    def session_start(self, workspace: str = "", mode: str = "", **fields):
        """Log session start."""
        fields.update(workspace=workspace, mode=mode, session=self._session_id)
        self._log(logging.INFO, "START", "Session", "Session started", **fields)

    def server_start(self, host: str = "", port: int = 0, **fields):
        """Log API server startup."""
        fields.update(host=host, port=port)
        self._log(logging.INFO, "BOOT", "Server", "API server started", **fields)

    def server_stop(self, **fields):
        """Log API server shutdown."""
        fields.update(requests_served=self._request_count)
        self._log(logging.INFO, "HALT", "Server", "API server stopped", **fields)

    def http_request(
        self, method: str, path: str, status: int = 200, latency_ms: int = 0, **fields
    ):
        """Log an HTTP request."""
        fields.update(method=method, path=path, status=status, latency_ms=latency_ms)
        level = logging.INFO if status < 400 else logging.WARNING
        self._log(level, "HTTP", "Server", f"{method} {path} -> {status}", **fields)
        self._request_count += 1

    def ws_connect(self, client: str = "", **fields):
        """Log WebSocket connection."""
        fields.update(client=client)
        self._log(logging.INFO, "WS", "WebSocket", "Client connected", **fields)

    def ws_disconnect(self, client: str = "", requests: int = 0, **fields):
        """Log WebSocket disconnection."""
        fields.update(client=client, requests=requests)
        self._log(logging.INFO, "WS", "WebSocket", "Client disconnected", **fields)

    def settings_change(self, changed_keys: list = None, **fields):
        """Log settings update."""
        fields.update(changed=str(changed_keys or []))
        self._log(logging.INFO, "CFG", "Settings", "Settings updated", **fields)

    def session_end(
        self, requests: int = 0, tier1: int = 0, tier2: int = 0, tier3: int = 0, **fields
    ):
        """Log session end with memory stats."""
        fields.update(
            requests=requests or self._request_count, tier1=tier1, tier2=tier2, tier3=tier3
        )
        self._log(logging.INFO, "END", "Session", "Session ended", **fields)

    def council(self, phase: str, agent: str, decision: str = "", latency_ms: int = 0, **fields):
        """Log council deliberation events."""
        fields.update(phase=phase, agent=agent, decision=decision, latency_ms=latency_ms)
        self._log(logging.INFO, "CNCL", "Council", f"Council {phase}: {agent}", **fields)

    def edit(self, action: str, file_path: str = "", confidence: float = 0, **fields):
        """Log file edit events."""
        fields.update(action=action, file=file_path, confidence=confidence)
        self._log(logging.INFO, "EDIT", "Editor", f"Edit {action}", **fields)

    # =========================================================================
    # UTILITY
    # =========================================================================

    @property
    def log_file(self) -> str:
        return str(LOG_FILE)

    @property
    def log_dir(self) -> str:
        return str(LOG_DIR)

    def get_log_stats(self) -> dict[str, Any]:
        """Get statistics about the log folder."""
        try:
            log_files = [f for f in LOG_DIR.iterdir() if f.is_file()]
            total_size = sum(f.stat().st_size for f in log_files)
            return {
                "log_file": str(LOG_FILE),
                "log_dir": str(LOG_DIR),
                "file_count": len(log_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "max_file_mb": MAX_LOG_FILE_BYTES / (1024 * 1024),
                "max_folder_gb": MAX_LOG_FOLDER_BYTES / (1024 * 1024 * 1024),
                "session_id": self._session_id,
                "requests_logged": self._request_count,
            }
        except Exception:
            return {"log_file": str(LOG_FILE), "error": "could not stat"}


# =============================================================================
# SINGLETON
# =============================================================================

_logger_instance: OrionLogger | None = None


def get_logger(project_dir: str | None = None) -> OrionLogger:
    """Get or create the global OrionLogger singleton.

    Args:
        project_dir: If provided on first call, enables a project-local
                     log mirror at <project_dir>/logs/orion.log.
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = OrionLogger(project_dir=project_dir)
    elif project_dir and _logger_instance._project_log_dir is None:
        _logger_instance.add_project_log(project_dir)
    return _logger_instance
