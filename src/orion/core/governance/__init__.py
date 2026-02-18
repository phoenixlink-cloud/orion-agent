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
Governance -- AEGIS safety gate and execution authority.

AEGIS is a hard gate that enforces workspace confinement, mode restrictions,
action scope validation, and risk assessment.
"""

from orion.core.governance.aegis import (
    AegisResult,
    ExternalAccessRequest,
    Intent,
    NetworkAccessRequest,
    check_aegis_gate,
    check_external_access,
    check_network_access,
    classify_credential_access,
    validate_action_bundle,
)

__all__ = [
    "check_aegis_gate",
    "check_external_access",
    "check_network_access",
    "classify_credential_access",
    "validate_action_bundle",
    "AegisResult",
    "ExternalAccessRequest",
    "NetworkAccessRequest",
    "Intent",
]
