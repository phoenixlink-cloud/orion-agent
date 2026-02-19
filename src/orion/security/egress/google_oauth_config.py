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
"""Manage user-provided Google OAuth app credentials (client_id / client_secret).

Orion ships with NO hardcoded Google OAuth credentials.  Each self-hosting
user must register their own Google Cloud OAuth application and provide:

  - ``client_id``  (required) -- e.g. ``123456789-abc.apps.googleusercontent.com``
  - ``client_secret`` (optional) -- e.g. ``GOCSPX-xxxxxxxx`` (Desktop apps using
    PKCE may omit this)

Credential resolution order (first non-empty wins):

  1. Environment variables: ``ORION_GOOGLE_CLIENT_ID``, ``ORION_GOOGLE_CLIENT_SECRET``
  2. Local config file: ``~/.orion/google_oauth.json``
  3. Generic OAuth client store: ``~/.orion/oauth_clients.json`` (via ``oauth_manager``)

The local config file is gitignored and has restricted permissions (0o600).

Functions
---------
load()      -- Load the current Google OAuth config (returns dict).
save()      -- Save client_id / client_secret to ``~/.orion/google_oauth.json``.
validate()  -- Check whether a client_id looks syntactically valid.
clear()     -- Delete ``~/.orion/google_oauth.json``.
status()    -- Return a summary dict (configured, source, masked_client_id).
resolve_client_id()     -- Resolve client_id from all sources.
resolve_client_secret() -- Resolve client_secret from all sources.
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
from pathlib import Path
from typing import Any

logger = logging.getLogger("orion.security.egress.google_oauth_config")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SETTINGS_DIR: Path = Path.home() / ".orion"
CONFIG_PATH: Path = SETTINGS_DIR / "google_oauth.json"

# ---------------------------------------------------------------------------
# Validation patterns
# ---------------------------------------------------------------------------

# Google OAuth client_id typically looks like:
#   123456789012-abcdefghijklmnopqrstuvwxyz123456.apps.googleusercontent.com
_CLIENT_ID_PATTERN = re.compile(r"^[0-9]+-[a-zA-Z0-9_]+\.apps\.googleusercontent\.com$")

# Google OAuth client_secret (web/desktop) typically starts with GOCSPX-
_CLIENT_SECRET_PATTERN = re.compile(r"^GOCSPX-[A-Za-z0-9_-]+$")


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def load() -> dict[str, Any]:
    """Load the Google OAuth config from ``~/.orion/google_oauth.json``.

    Returns an empty dict if the file does not exist or is unreadable.
    """
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        logger.warning("Could not read %s", CONFIG_PATH)
        return {}


def save(client_id: str, client_secret: str = "") -> Path:
    """Save Google OAuth app credentials to ``~/.orion/google_oauth.json``.

    Parameters
    ----------
    client_id : str
        The OAuth 2.0 client ID from Google Cloud Console.
    client_secret : str, optional
        The OAuth 2.0 client secret (may be empty for Desktop/PKCE apps).

    Returns
    -------
    Path
        The path to the saved config file.

    Raises
    ------
    ValueError
        If ``client_id`` is empty or fails basic validation.
    """
    if not client_id or not client_id.strip():
        raise ValueError("client_id must not be empty")

    client_id = client_id.strip()
    client_secret = client_secret.strip() if client_secret else ""

    valid, reason = validate(client_id, client_secret)
    if not valid:
        raise ValueError(reason)

    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "_comment": "User-provided Google OAuth app credentials for Orion. See docs/GOOGLE_SETUP.md.",
    }

    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Restrict permissions (owner-only read/write) -- best effort on Windows
    try:
        CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    logger.info("Google OAuth config saved to %s", CONFIG_PATH)
    return CONFIG_PATH


def validate(client_id: str, client_secret: str = "") -> tuple[bool, str]:
    """Validate a Google OAuth client_id (and optionally client_secret).

    Parameters
    ----------
    client_id : str
        The OAuth 2.0 client ID to validate.
    client_secret : str, optional
        The OAuth 2.0 client secret to validate (empty is OK for PKCE).

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` if valid, or ``(False, reason)`` if invalid.
    """
    if not client_id or not client_id.strip():
        return False, "client_id must not be empty"

    client_id = client_id.strip()

    if not _CLIENT_ID_PATTERN.match(client_id):
        return False, (
            "client_id does not match expected Google OAuth format: "
            "<number>-<alphanum>.apps.googleusercontent.com"
        )

    if client_secret and client_secret.strip():
        secret = client_secret.strip()
        if not _CLIENT_SECRET_PATTERN.match(secret):
            return False, (
                "client_secret does not match expected Google format (GOCSPX-...)."
                " If your app uses PKCE, you may leave client_secret empty."
            )

    return True, ""


def clear() -> bool:
    """Delete the local Google OAuth config file.

    Returns
    -------
    bool
        ``True`` if the file was deleted, ``False`` if it did not exist.
    """
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
        logger.info("Google OAuth config cleared: %s", CONFIG_PATH)
        return True
    return False


def resolve_client_id() -> str | None:
    """Resolve the Google OAuth client_id from all sources.

    Resolution order:
      1. ``ORION_GOOGLE_CLIENT_ID`` environment variable
      2. ``~/.orion/google_oauth.json`` (dedicated config)
      3. ``~/.orion/oauth_clients.json`` (generic OAuth store via oauth_manager)

    Returns
    -------
    str or None
        The client_id, or ``None`` if not configured anywhere.
    """
    # 1. Environment variable
    env_val = os.environ.get("ORION_GOOGLE_CLIENT_ID", "").strip()
    if env_val:
        return env_val

    # 2. Dedicated config file
    cfg = load()
    file_val = cfg.get("client_id", "").strip()
    if file_val:
        return file_val

    # 3. Generic OAuth client store
    try:
        from orion.integrations.oauth_manager import get_client_id

        generic_val = get_client_id("google")
        if generic_val:
            return generic_val
    except Exception:
        pass

    return None


def resolve_client_secret() -> str | None:
    """Resolve the Google OAuth client_secret from all sources.

    Resolution order:
      1. ``ORION_GOOGLE_CLIENT_SECRET`` environment variable
      2. ``~/.orion/google_oauth.json``
      3. ``~/.orion/oauth_clients.json`` (via oauth_manager)

    Returns
    -------
    str or None
        The client_secret, or ``None`` if not configured.
    """
    # 1. Environment variable
    env_val = os.environ.get("ORION_GOOGLE_CLIENT_SECRET", "").strip()
    if env_val:
        return env_val

    # 2. Dedicated config file
    cfg = load()
    file_val = cfg.get("client_secret", "").strip()
    if file_val:
        return file_val

    # 3. Generic OAuth client store
    try:
        from orion.integrations.oauth_manager import get_client_secret

        secret = get_client_secret("google")
        if secret:
            return secret
    except Exception:
        pass

    return None


def _mask_client_id(client_id: str) -> str:
    """Mask a client_id for safe display: show first 8 and last 20 chars."""
    if len(client_id) < 30:
        return client_id[:4] + "***" + client_id[-10:]
    return client_id[:8] + "***" + client_id[-20:]


def status() -> dict[str, Any]:
    """Return a summary of the current Google OAuth configuration.

    Returns
    -------
    dict
        Keys: ``configured``, ``source``, ``client_id_masked``,
        ``has_client_secret``, ``config_path``.
    """
    result: dict[str, Any] = {
        "configured": False,
        "source": None,
        "client_id_masked": None,
        "has_client_secret": False,
        "config_path": str(CONFIG_PATH),
    }

    # Check env var first
    env_id = os.environ.get("ORION_GOOGLE_CLIENT_ID", "").strip()
    if env_id:
        result["configured"] = True
        result["source"] = "environment"
        result["client_id_masked"] = _mask_client_id(env_id)
        env_secret = os.environ.get("ORION_GOOGLE_CLIENT_SECRET", "").strip()
        result["has_client_secret"] = bool(env_secret)
        return result

    # Check dedicated config file
    cfg = load()
    file_id = cfg.get("client_id", "").strip()
    if file_id:
        result["configured"] = True
        result["source"] = "config_file"
        result["client_id_masked"] = _mask_client_id(file_id)
        result["has_client_secret"] = bool(cfg.get("client_secret", "").strip())
        return result

    # Check generic oauth_clients.json
    try:
        from orion.integrations.oauth_manager import get_client_id

        generic_id = get_client_id("google")
        if generic_id:
            result["configured"] = True
            result["source"] = "oauth_clients"
            result["client_id_masked"] = _mask_client_id(generic_id)
            return result
    except Exception:
        pass

    return result
