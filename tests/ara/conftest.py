# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Shared fixtures for ARA tests."""

from __future__ import annotations

import pytest


def pytest_configure(config):
    """Register custom markers for ARA tests."""
    config.addinivalue_line("markers", "docker: requires Docker daemon running")
    config.addinivalue_line("markers", "ollama: requires Ollama running locally")
    config.addinivalue_line("markers", "e2e: end-to-end integration test")
