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
"""Orion Agent -- GDPR Compliance Routes."""

import contextlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter

from orion.api._shared import (
    SETTINGS_DIR,
    _get_secure_store,
    _load_user_settings,
)

router = APIRouter()

GDPR_CONSENTS_FILE = SETTINGS_DIR / "gdpr_consents.json"
GDPR_AUDIT_FILE = SETTINGS_DIR / "gdpr_audit.jsonl"


def _load_gdpr_consents() -> dict:
    if GDPR_CONSENTS_FILE.exists():
        try:
            return json.loads(GDPR_CONSENTS_FILE.read_text())
        except Exception:
            pass
    return {"consents": {}, "policy_version": "1.0.0"}


def _save_gdpr_consents(data: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    GDPR_CONSENTS_FILE.write_text(json.dumps(data, indent=2))


def _append_audit_log(action: str, data_type: str, details: str = None):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = json.dumps(
        {
            "action": action,
            "data_type": data_type,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "details": details,
        }
    )
    with open(GDPR_AUDIT_FILE, "a") as f:
        f.write(entry + "\n")


@router.get("/api/gdpr/consents")
async def get_gdpr_consents():
    """Get GDPR consent statuses."""
    return _load_gdpr_consents()


@router.post("/api/gdpr/consent/{consent_type}")
async def set_gdpr_consent(consent_type: str, granted: bool = True):
    """Set a GDPR consent."""
    data = _load_gdpr_consents()
    data["consents"][consent_type] = granted
    _save_gdpr_consents(data)
    _append_audit_log("consent_update", consent_type, f"granted={granted}")
    return {"status": "success", "consent_type": consent_type, "granted": granted}


@router.get("/api/gdpr/export")
async def export_all_data():
    """Export all user data (GDPR right to data portability)."""
    _append_audit_log("data_export", "all", "User requested full data export")

    from orion.api.routes.auth import _load_oauth_state, get_api_key_status

    export = {
        "settings": _load_user_settings(),
        "api_keys_configured": [
            p["provider"] for p in (await get_api_key_status()) if p["configured"]
        ],
        "oauth_state": _load_oauth_state(),
        "gdpr_consents": _load_gdpr_consents(),
    }
    # Include model config
    try:
        model_config_file = SETTINGS_DIR / "model_config.json"
        if model_config_file.exists():
            export["model_config"] = json.loads(model_config_file.read_text())
    except Exception:
        pass
    return export


@router.delete("/api/gdpr/data")
async def delete_all_data():
    """Delete all user data (GDPR right to erasure)."""
    _append_audit_log("data_deletion", "all", "User requested full data deletion")

    from orion.api._shared import SETTINGS_FILE

    # Clear secure store
    store = _get_secure_store()
    if store:
        for provider in store.list_providers():
            with contextlib.suppress(Exception):
                store.delete_key(provider)

    files_to_delete = [
        SETTINGS_FILE,
        SETTINGS_DIR / "api_keys.json",
        SETTINGS_DIR / "api_keys.json.migrated",
        SETTINGS_DIR / "oauth_state.json",
        SETTINGS_DIR / "oauth_tokens.json",
        SETTINGS_DIR / "model_config.json",
        SETTINGS_DIR / "provider_settings.json",
        SETTINGS_DIR / "security" / "vault.enc",
        SETTINGS_DIR / "security" / "vault.salt",
        SETTINGS_DIR / "security" / "credentials.meta.json",
        SETTINGS_DIR / "security" / "audit.log",
        GDPR_CONSENTS_FILE,
    ]
    deleted = []
    for f in files_to_delete:
        if f.exists():
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception:
                pass
    return {"status": "success", "deleted_files": deleted}


@router.get("/api/gdpr/audit")
async def get_audit_log(limit: int = 100):
    """Get GDPR audit log."""
    entries = []
    if GDPR_AUDIT_FILE.exists():
        try:
            lines = GDPR_AUDIT_FILE.read_text().strip().split("\n")
            for line in lines[-limit:]:
                if line.strip():
                    entries.append(json.loads(line))
        except Exception:
            pass
    return {"audit_log": entries}
