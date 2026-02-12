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
Orion Agent -- Structured Logging (v7.4.0)

JSON-structured logger for production environments.
"""

import json
import logging
import sys
from datetime import datetime, timezone


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
        self._correlation_id: str | None = None

        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def set_correlation_id(self, correlation_id: str):
        """Set the correlation ID for request tracing."""
        self._correlation_id = correlation_id

    def _format(self, level: str, message: str, **kwargs) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
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
