"""
Orion Agent — Structured Logging (v6.4.0)

JSON-structured logger for production environments.
"""

import sys
import json
import logging
from typing import Optional
from datetime import datetime


class StructuredLogger:
    """
    JSON-structured logger for production environments.

    Outputs logs in JSON format with correlation IDs, timestamps,
    and structured context fields.
    """

    def __init__(self, name: str = "orion", level: str = "INFO"):
        self.name = name
        self.level = getattr(logging, level.upper(), logging.INFO)
        self._logger = logging.getLogger(name)
        self._logger.setLevel(self.level)
        self._correlation_id: Optional[str] = None

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def set_correlation_id(self, correlation_id: str):
        """Set the correlation ID for request tracing."""
        self._correlation_id = correlation_id

    def _format(self, level: str, message: str, **kwargs) -> str:
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "service": self.name,
            "message": message,
        }
        if self._correlation_id:
            entry["correlation_id"] = self._correlation_id
        entry.update(kwargs)
        return json.dumps(entry)

    def info(self, message: str, **kwargs):
        self._logger.info(self._format("INFO", message, **kwargs))

    def warn(self, message: str, **kwargs):
        self._logger.warning(self._format("WARN", message, **kwargs))

    def error(self, message: str, **kwargs):
        self._logger.error(self._format("ERROR", message, **kwargs))

    def debug(self, message: str, **kwargs):
        self._logger.debug(self._format("DEBUG", message, **kwargs))
