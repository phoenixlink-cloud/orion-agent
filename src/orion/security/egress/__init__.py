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
"""Orion Egress Proxy -- The Narrow Door.

Host-side network security layer that filters all outbound traffic
from Orion's Docker sandbox. Implements an additive whitelist model
where only explicitly allowed domains are reachable.

Architecture (from Milestone Decision Document):
  Docker Container (Orion) --> Egress Proxy (Host) --> Internet (filtered)

Security properties:
  - Default DENY: all domains blocked except LLM endpoints
  - Additive whitelist: users add domains explicitly
  - HTTPS only: no raw TCP/SMTP/SSH/FTP unless explicitly enabled
  - Content inspection: outbound payloads checked for credential leakage
  - Rate limiting: prevents runaway API costs
  - DNS-level filtering: non-whitelisted domains return NXDOMAIN
  - Full audit logging: every request logged, unmodifiable by Orion
"""
