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
Three-Tier Memory System -- Orion's competitive moat.

Tier 1: Session (RAM) -- current request context
Tier 2: Project (JSON) -- workspace-scoped patterns
Tier 3: Institutional (SQLite) -- cross-project wisdom
"""

from orion.core.memory.engine import MemoryEngine, get_memory_engine

__all__ = ["MemoryEngine", "get_memory_engine"]
