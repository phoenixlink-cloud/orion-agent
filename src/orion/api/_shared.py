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
Orion Agent -- Shared API Utilities

Common utilities, settings persistence, and Pydantic models
shared across all route modules.
"""

import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger("orion.api.server")

# Resolve project root (two levels up from src/orion/api/_shared.py)
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent.parent)


# =============================================================================
# ORION LOGGER
# =============================================================================

_orion_log = None


def _get_orion_log():
    """Lazy-init the OrionLogger with project-local log mirror."""
    global _orion_log
    if _orion_log is None:
        try:
            from orion.core.logging import get_logger

            _orion_log = get_logger(project_dir=_PROJECT_ROOT)
        except Exception:
            pass
    return _orion_log


# =============================================================================
# SETTINGS PERSISTENCE
# =============================================================================

SETTINGS_DIR = Path.home() / ".orion"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def _load_user_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_user_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


# =============================================================================
# SECURE STORE
# =============================================================================


def _get_secure_store():
    """Get SecureStore singleton. Falls back to legacy plaintext if unavailable."""
    try:
        from orion.security.store import get_secure_store

        store = get_secure_store()
        if store.is_available:
            return store
    except Exception as e:
        logger.debug(f"SecureStore unavailable: {e}")
    return None


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class ChatRequest(BaseModel):
    message: str
    workspace: str = ""
    mode: str = "safe"


class ModelModeRequest(BaseModel):
    mode: str  # "local" or "cloud"


class RoleConfigRequest(BaseModel):
    provider: str
    model: str
    light_model: str | None = ""
    use_tiers: bool | None = False


class ModelConfigRequest(BaseModel):
    mode: str | None = None
    builder: RoleConfigRequest | None = None
    reviewer: RoleConfigRequest | None = None


class PresetRequest(BaseModel):
    name: str


class APIKeySetRequest(BaseModel):
    provider: str
    key: str


class OAuthConfigureRequest(BaseModel):
    provider: str
    client_id: str
    client_secret: str | None = None


class OAuthLoginRequest(BaseModel):
    provider: str
    redirect_uri: str | None = None


class OAuthRevokeRequest(BaseModel):
    provider: str


class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: str


class ProviderToggleRequest(BaseModel):
    provider: str
    enabled: bool


class SettingsUpdate(BaseModel):
    # Core Features
    enable_table_of_three: bool | None = None
    enable_file_tools: bool | None = None
    enable_passive_memory: bool | None = None
    enable_intelligent_orion: bool | None = None
    enable_streaming: bool | None = None
    # Intelligent Orion
    quality_threshold: float | None = None
    max_refinement_iterations: int | None = None
    # Governance
    default_mode: str | None = None
    aegis_strict_mode: bool | None = None
    # Command Execution
    enable_command_execution: bool | None = None
    command_timeout_seconds: int | None = None
    # Limits
    max_evidence_files: int | None = None
    max_file_size_bytes: int | None = None
    max_evidence_retry: int | None = None
    # Web Access
    enable_web_access: bool | None = None
    web_cache_ttl: int | None = None
    allowed_domains: str | None = None
    # Image Generation
    image_provider: str | None = None
    sdxl_enabled: bool | None = None
    sdxl_endpoint: str | None = None
    flux_enabled: bool | None = None
    dalle_enabled: bool | None = None
    dalle_model: str | None = None
    # Models (legacy)
    use_local_models: bool | None = None
    gpt_model: str | None = None
    claude_model: str | None = None
    ollama_base_url: str | None = None
    ollama_builder_model: str | None = None
    ollama_reviewer_model: str | None = None
    # Paths
    data_dir: str | None = None
    ledger_file: str | None = None
    # Workspace
    workspace: str | None = None
    # ARA (Autonomous Role Architecture)
    ara_enabled: bool | None = None
    ara_default_auth: str | None = None
    ara_max_cost_usd: float | None = None
    ara_max_session_hours: float | None = None
    ara_sandbox_mode: str | None = None
    ara_prompt_guard: bool | None = None
    ara_audit_log: bool | None = None


class AegisApprovalResponse(BaseModel):
    approved: bool


class GitCommitRequest(BaseModel):
    workspace: str
    message: str = "orion: automated changes"


class GitUndoRequest(BaseModel):
    workspace: str
    subcommand: str = ""  # "", "all", "stack", "history"


class ModeRequest(BaseModel):
    mode: str  # "safe", "pro", "project"


class ContextFilesRequest(BaseModel):
    workspace: str
    files: list[str]


class PlatformConnectRequest(BaseModel):
    platform_id: str
    token: str | None = None
    api_key: str | None = None
