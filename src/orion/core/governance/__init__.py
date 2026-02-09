"""
Governance — AEGIS safety gate and execution authority.

AEGIS is a hard gate that enforces workspace confinement, mode restrictions,
action scope validation, and risk assessment.
"""

from orion.core.governance.aegis import (
    check_aegis_gate,
    check_external_access,
    classify_credential_access,
    validate_action_bundle,
    AegisResult,
    ExternalAccessRequest,
    Intent,
)

__all__ = [
    "check_aegis_gate",
    "check_external_access",
    "classify_credential_access",
    "validate_action_bundle",
    "AegisResult",
    "ExternalAccessRequest",
    "Intent",
]
