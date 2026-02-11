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
Orion Agent -- Messaging Bridges (v6.8.0)

Bidirectional messaging bridges that let users interact with Orion
through external platforms: Telegram, Slack, Discord.

Security model:
  1. Chat ID allowlist -- only pre-authorized users can interact
  2. Passphrase authentication -- first message must contain a secret
  3. AEGIS gate -- destructive actions require inline approval
  4. Rate limiting -- per-user request throttling
  5. All messages logged to ~/.orion/logs/orion.log

Usage:
    from orion.bridges import get_bridge_manager
    manager = get_bridge_manager()
    manager.enable("telegram", token="BOT_TOKEN")
    await manager.start_all()
"""
