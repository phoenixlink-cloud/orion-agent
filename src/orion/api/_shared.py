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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Shared API Utilities

Common utilities, settings persistence, and Pydantic models
shared across all route modules.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

from orion._version import __version__

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
    light_model: Optional[str] = ""
    use_tiers: Optional[bool] = False


class ModelConfigRequest(BaseModel):
    mode: Optional[str] = None
    builder: Optional[RoleConfigRequest] = None
    reviewer: Optional[RoleConfigRequest] = None


class PresetRequest(BaseModel):
    name: str


class APIKeySetRequest(BaseModel):
    provider: str
    key: str


class OAuthConfigureRequest(BaseModel):
    provider: str
    client_id: str
    client_secret: Optional[str] = None


class OAuthLoginRequest(BaseModel):
    provider: str
    redirect_uri: Optional[str] = None


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
    enable_table_of_three: Optional[bool] = None
    enable_file_tools: Optional[bool] = None
    enable_passive_memory: Optional[bool] = None
    enable_intelligent_orion: Optional[bool] = None
    enable_streaming: Optional[bool] = None
    # Intelligent Orion
    quality_threshold: Optional[float] = None
    max_refinement_iterations: Optional[int] = None
    # Governance
    default_mode: Optional[str] = None
    aegis_strict_mode: Optional[bool] = None
    # Command Execution
    enable_command_execution: Optional[bool] = None
    command_timeout_seconds: Optional[int] = None
    # Limits
    max_evidence_files: Optional[int] = None
    max_file_size_bytes: Optional[int] = None
    max_evidence_retry: Optional[int] = None
    # Web Access
    enable_web_access: Optional[bool] = None
    web_cache_ttl: Optional[int] = None
    allowed_domains: Optional[str] = None
    # Image Generation
    image_provider: Optional[str] = None
    sdxl_enabled: Optional[bool] = None
    sdxl_endpoint: Optional[str] = None
    flux_enabled: Optional[bool] = None
    dalle_enabled: Optional[bool] = None
    dalle_model: Optional[str] = None
    # Models (legacy)
    use_local_models: Optional[bool] = None
    gpt_model: Optional[str] = None
    claude_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_builder_model: Optional[str] = None
    ollama_reviewer_model: Optional[str] = None
    # Paths
    data_dir: Optional[str] = None
    ledger_file: Optional[str] = None
    # Workspace
    workspace: Optional[str] = None


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
    files: List[str]


class PlatformConnectRequest(BaseModel):
    platform_id: str
    token: Optional[str] = None
    api_key: Optional[str] = None
