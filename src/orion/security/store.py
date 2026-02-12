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
Orion Agent -- Secure Credential Store (v7.4.0)

Enterprise-grade credential storage with layered backends:

  1. OS Keyring (primary)  -- Windows Credential Locker / macOS Keychain / Linux SecretService
  2. Encrypted File (fallback) -- Fernet (AES-128-CBC + HMAC-SHA256) with PBKDF2-derived key

Design principles:
  - No plaintext secrets on disk (ever)
  - Machine-bound encryption key derived from hardware/user identity
  - Thread-safe singleton access via get_secure_store()
  - Audit log of credential access events
  - Graceful degradation: keyring -> encrypted file -> clear error
"""

import base64
import hashlib
import json
import logging
import os
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("orion.security.store")

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CredentialEntry:
    """A stored credential with metadata."""

    provider: str
    created_at: float
    updated_at: float
    backend: str  # "keyring" or "encrypted_file"


@dataclass
class AuditEvent:
    """Credential access audit log entry."""

    timestamp: float
    action: str  # "set", "get", "delete", "rotate"
    provider: str
    backend: str
    success: bool
    detail: str = ""


# =============================================================================
# Encryption Backend (Fernet -- AES-128-CBC + HMAC-SHA256 via PBKDF2)
# =============================================================================


class _FernetBackend:
    """
    Encrypted file backend using cryptography.fernet.Fernet.

    Key derivation: PBKDF2-HMAC-SHA256 with 600,000 iterations
    (OWASP 2024 recommendation) from a machine-unique seed.
    """

    def __init__(self, store_dir: Path):
        self._store_dir = store_dir
        self._vault_path = store_dir / "vault.enc"
        self._salt_path = store_dir / "vault.salt"
        self._fernet = None
        self._available = False
        self._init_fernet()

    def _init_fernet(self):
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            # Ensure salt exists (generated once per install)
            if not self._salt_path.exists():
                salt = os.urandom(32)
                self._store_dir.mkdir(parents=True, exist_ok=True)
                self._salt_path.write_bytes(salt)
            else:
                salt = self._salt_path.read_bytes()

            # Derive key from machine-unique seed + salt
            seed = self._get_machine_seed()
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=600_000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(seed))
            self._fernet = Fernet(key)
            self._available = True
        except ImportError:
            logger.debug("cryptography package not installed -- encrypted file backend unavailable")
        except Exception as e:
            logger.warning(f"Failed to initialize encrypted file backend: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def _get_machine_seed(self) -> bytes:
        """
        Generate a machine-bound seed for key derivation.

        Combines: username + hostname + machine-id (Linux) or
        MachineGuid (Windows) or hardware UUID (macOS).
        This ties the encryption key to the specific machine and user.
        """
        parts = [
            os.getlogin() if hasattr(os, "getlogin") else os.environ.get("USER", "orion"),
            platform.node(),
        ]

        # Platform-specific machine identifier
        system = platform.system()
        if system == "Linux":
            for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
                try:
                    parts.append(Path(path).read_text().strip())
                    break
                except Exception:
                    pass
        elif system == "Windows":
            try:
                import winreg

                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                parts.append(guid)
                winreg.CloseKey(key)
            except Exception:
                pass
        elif system == "Darwin":
            try:
                import subprocess

                result = subprocess.run(
                    ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.split("\n"):
                    if "IOPlatformUUID" in line:
                        parts.append(line.split('"')[-2])
                        break
            except Exception:
                pass

        seed_str = "|".join(parts)
        return hashlib.sha256(seed_str.encode()).digest()

    def _load_vault(self) -> dict[str, str]:
        """Load and decrypt the vault file."""
        if not self._vault_path.exists():
            return {}
        try:
            encrypted = self._vault_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Failed to decrypt vault: {e}")
            return {}

    def _save_vault(self, data: dict[str, str]):
        """Encrypt and save the vault file."""
        self._store_dir.mkdir(parents=True, exist_ok=True)
        plaintext = json.dumps(data).encode()
        encrypted = self._fernet.encrypt(plaintext)
        self._vault_path.write_bytes(encrypted)

    def get(self, provider: str) -> str | None:
        vault = self._load_vault()
        return vault.get(provider)

    def set(self, provider: str, value: str):
        vault = self._load_vault()
        vault[provider] = value
        self._save_vault(vault)

    def delete(self, provider: str) -> bool:
        vault = self._load_vault()
        if provider in vault:
            del vault[provider]
            self._save_vault(vault)
            return True
        return False

    def list_providers(self) -> list[str]:
        return list(self._load_vault().keys())


# =============================================================================
# Keyring Backend
# =============================================================================


class _KeyringBackend:
    """
    OS keyring backend using the `keyring` library.

    Maps to:
      - Windows: Windows Credential Locker
      - macOS: Keychain
      - Linux: SecretService (GNOME Keyring / KDE Wallet)
    """

    SERVICE_NAME = "orion-agent"

    def __init__(self):
        self._available = False
        self._keyring = None
        self._init_keyring()

    def _init_keyring(self):
        try:
            import keyring as kr

            # Verify keyring is functional (not a null backend)
            backend_name = str(kr.get_keyring())
            if "fail" in backend_name.lower() or "null" in backend_name.lower():
                logger.debug(f"Keyring backend is non-functional: {backend_name}")
                return
            self._keyring = kr
            self._available = True
            logger.debug(f"Keyring backend active: {backend_name}")
        except ImportError:
            logger.debug("keyring package not installed -- OS keyring backend unavailable")
        except Exception as e:
            logger.debug(f"Keyring init failed: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def get(self, provider: str) -> str | None:
        try:
            return self._keyring.get_password(self.SERVICE_NAME, provider)
        except Exception as e:
            logger.warning(f"Keyring get failed for {provider}: {e}")
            return None

    def set(self, provider: str, value: str):
        try:
            self._keyring.set_password(self.SERVICE_NAME, provider, value)
        except Exception as e:
            logger.warning(f"Keyring set failed for {provider}: {e}")
            raise

    def delete(self, provider: str) -> bool:
        try:
            self._keyring.delete_password(self.SERVICE_NAME, provider)
            return True
        except Exception as e:
            logger.debug(f"Keyring delete failed for {provider}: {e}")
            return False


# =============================================================================
# Secure Store (Public API)
# =============================================================================


class SecureStore:
    """
    Layered credential store with audit logging.

    Backend priority:
      1. OS Keyring (if available and functional)
      2. Encrypted File (Fernet + PBKDF2)
      3. Error -- refuses to store in plaintext

    Usage:
        store = get_secure_store()
        store.set_key("openai", "sk-abc123...")
        key = store.get_key("openai")
        store.delete_key("openai")
    """

    def __init__(self, store_dir: Path | None = None):
        self._store_dir = store_dir or (Path.home() / ".orion" / "security")
        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._audit_path = self._store_dir / "audit.log"
        self._meta_path = self._store_dir / "credentials.meta.json"
        self._lock = threading.Lock()

        # Initialize backends in priority order
        self._keyring = _KeyringBackend()
        self._fernet = _FernetBackend(self._store_dir)

        # Load metadata (provider -> backend mapping, timestamps)
        self._meta: dict[str, CredentialEntry] = self._load_meta()

    @property
    def backend_name(self) -> str:
        """Name of the active primary backend."""
        if self._keyring.available:
            return "keyring"
        elif self._fernet.available:
            return "encrypted_file"
        return "none"

    @property
    def is_available(self) -> bool:
        """Whether any secure backend is available."""
        return self._keyring.available or self._fernet.available

    def get_key(self, provider: str) -> str | None:
        """Retrieve a stored credential by provider name."""
        with self._lock:
            # Try the backend recorded in metadata first
            entry = self._meta.get(provider)
            if entry:
                value = self._get_from_backend(entry.backend, provider)
                if value:
                    self._audit("get", provider, entry.backend, True)
                    return value

            # Fallback: try all backends
            for backend_name, backend in self._backends():
                value = backend.get(provider)
                if value:
                    self._audit("get", provider, backend_name, True)
                    return value

            self._audit("get", provider, "none", False, "not found")
            return None

    def set_key(self, provider: str, value: str) -> str:
        """
        Store a credential. Returns the backend name used.

        Raises RuntimeError if no secure backend is available.
        """
        with self._lock:
            if not self.is_available:
                raise RuntimeError(
                    "No secure storage backend available. "
                    "Install 'keyring' or 'cryptography' package: "
                    "pip install keyring cryptography"
                )

            backend_name = "none"
            stored = False

            # Try keyring first
            if self._keyring.available:
                try:
                    self._keyring.set(provider, value)
                    backend_name = "keyring"
                    stored = True
                except Exception:
                    pass

            # Fallback to encrypted file
            if not stored and self._fernet.available:
                self._fernet.set(provider, value)
                backend_name = "encrypted_file"
                stored = True

            if not stored:
                raise RuntimeError("Failed to store credential in any backend")

            # Update metadata
            now = time.time()
            existing = self._meta.get(provider)
            self._meta[provider] = CredentialEntry(
                provider=provider,
                created_at=existing.created_at if existing else now,
                updated_at=now,
                backend=backend_name,
            )
            self._save_meta()
            self._audit("set", provider, backend_name, True)
            return backend_name

    def delete_key(self, provider: str) -> bool:
        """Delete a stored credential. Returns True if found and deleted."""
        with self._lock:
            deleted = False
            backend_used = "none"

            # Try all backends to ensure complete removal
            if self._keyring.available and self._keyring.delete(provider):
                deleted = True
                backend_used = "keyring"

            if self._fernet.available and self._fernet.delete(provider):
                deleted = True
                backend_used = "encrypted_file"

            if provider in self._meta:
                del self._meta[provider]
                self._save_meta()

            self._audit("delete", provider, backend_used, deleted)
            return deleted

    def list_providers(self) -> list[str]:
        """List all providers that have stored credentials."""
        providers = set(self._meta.keys())

        # Also check backends directly for any not in metadata
        if self._fernet.available:
            providers.update(self._fernet.list_providers())

        return sorted(providers)

    def has_key(self, provider: str) -> bool:
        """Check if a credential exists for the given provider."""
        return provider in self._meta or self.get_key(provider) is not None

    def get_status(self) -> dict:
        """Get store status for diagnostics."""
        return {
            "available": self.is_available,
            "backend": self.backend_name,
            "keyring_available": self._keyring.available,
            "encrypted_file_available": self._fernet.available,
            "stored_providers": self.list_providers(),
            "store_dir": str(self._store_dir),
        }

    def rotate_key(self, provider: str, new_value: str) -> str:
        """Rotate a credential (delete old, store new). Returns backend used."""
        with self._lock:
            # Remove from all backends
            if self._keyring.available:
                self._keyring.delete(provider)
            if self._fernet.available:
                self._fernet.delete(provider)

        # Store with new value (re-acquires lock internally)
        backend = self.set_key(provider, new_value)
        self._audit("rotate", provider, backend, True)
        return backend

    def migrate_plaintext_keys(self, plaintext_path: Path | None = None) -> dict[str, str]:
        """
        Migrate plaintext API keys from legacy storage into secure store.

        Returns dict of {provider: backend_used} for each migrated key.
        """
        if plaintext_path is None:
            plaintext_path = Path.home() / ".orion" / "api_keys.json"

        if not plaintext_path.exists():
            return {}

        try:
            data = json.loads(plaintext_path.read_text())
        except Exception:
            return {}

        migrated = {}
        for provider, key_value in data.items():
            if isinstance(key_value, str) and key_value.strip():
                try:
                    backend = self.set_key(provider, key_value)
                    migrated[provider] = backend
                except Exception as e:
                    logger.warning(f"Failed to migrate key for {provider}: {e}")

        if migrated:
            # Rename plaintext file (don't delete -- user might want backup)
            backup_path = plaintext_path.with_suffix(".json.migrated")
            try:
                plaintext_path.rename(backup_path)
                logger.info(
                    f"Migrated {len(migrated)} keys to secure store. "
                    f"Plaintext backup at: {backup_path}"
                )
            except Exception:
                logger.warning("Could not rename plaintext key file after migration")

        return migrated

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _backends(self):
        """Yield (name, backend) pairs in priority order."""
        if self._keyring.available:
            yield "keyring", self._keyring
        if self._fernet.available:
            yield "encrypted_file", self._fernet

    def _get_from_backend(self, backend_name: str, provider: str) -> str | None:
        if backend_name == "keyring" and self._keyring.available:
            return self._keyring.get(provider)
        elif backend_name == "encrypted_file" and self._fernet.available:
            return self._fernet.get(provider)
        return None

    def _load_meta(self) -> dict[str, CredentialEntry]:
        if not self._meta_path.exists():
            return {}
        try:
            data = json.loads(self._meta_path.read_text())
            return {k: CredentialEntry(**v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_meta(self):
        data = {
            k: {
                "provider": v.provider,
                "created_at": v.created_at,
                "updated_at": v.updated_at,
                "backend": v.backend,
            }
            for k, v in self._meta.items()
        }
        self._meta_path.write_text(json.dumps(data, indent=2))

    def _audit(self, action: str, provider: str, backend: str, success: bool, detail: str = ""):
        """Append to audit log with caller tracking."""
        import inspect

        # Walk the stack to find the first caller outside this module
        caller = "unknown"
        try:
            for frame_info in inspect.stack()[2:6]:
                mod = frame_info.filename.replace("\\", "/")
                if "security/store" not in mod:
                    caller = f"{mod.split('/')[-1]}:{frame_info.function}:{frame_info.lineno}"
                    break
        except Exception:
            pass

        event = AuditEvent(
            timestamp=time.time(),
            action=action,
            provider=provider,
            backend=backend,
            success=success,
            detail=detail,
        )
        try:
            with open(self._audit_path, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": event.timestamp,
                            "action": event.action,
                            "provider": event.provider,
                            "backend": event.backend,
                            "success": event.success,
                            "detail": event.detail,
                            "caller": caller,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Audit logging is best-effort


# =============================================================================
# Singleton Access
# =============================================================================

_instance: SecureStore | None = None
_instance_lock = threading.Lock()


def get_secure_store(store_dir: Path | None = None) -> SecureStore:
    """
    Get the singleton SecureStore instance.

    Thread-safe. First call initializes the store.
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SecureStore(store_dir)
    return _instance
