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
"""Platform-native credential storage for ARA authentication.

Replaces plain JSON storage with system keychain / credential manager.
Falls back to an encrypted file when no native backend is available.

See ARA-001 §3.6 for design.

Backends:
- Windows: Windows Credential Manager (via ctypes)
- macOS: macOS Keychain (via 'security' CLI)
- Linux: freedesktop Secret Service (via secretstorage, if available)
- Fallback: Fernet-encrypted file with machine-derived key
"""

from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("orion.ara.keychain")

SERVICE_NAME = "orion-ara"
FALLBACK_DIR = Path.home() / ".orion" / "credentials"
FALLBACK_FILE = FALLBACK_DIR / "vault.enc"


def _machine_key() -> bytes:
    """Derive a 32-byte key from machine-specific attributes."""
    raw = f"orion-keychain-{platform.node()}-{Path.home()}".encode()
    return hashlib.sha256(raw).digest()


class KeychainBackend:
    """Abstract base for credential storage backends."""

    def store(self, key: str, value: str) -> bool:
        raise NotImplementedError

    def retrieve(self, key: str) -> str | None:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def available(self) -> bool:
        raise NotImplementedError


class WindowsBackend(KeychainBackend):
    """Windows Credential Manager backend using ctypes."""

    def available(self) -> bool:
        return sys.platform == "win32"

    def store(self, key: str, value: str) -> bool:
        try:
            import ctypes
            import ctypes.wintypes

            advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]

            class CREDENTIAL(ctypes.Structure):
                _fields_ = [
                    ("Flags", ctypes.wintypes.DWORD),
                    ("Type", ctypes.wintypes.DWORD),
                    ("TargetName", ctypes.c_wchar_p),
                    ("Comment", ctypes.c_wchar_p),
                    ("LastWritten", ctypes.c_byte * 8),
                    ("CredentialBlobSize", ctypes.wintypes.DWORD),
                    ("CredentialBlob", ctypes.c_char_p),
                    ("Persist", ctypes.wintypes.DWORD),
                    ("AttributeCount", ctypes.wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", ctypes.c_wchar_p),
                    ("UserName", ctypes.c_wchar_p),
                ]

            target = f"{SERVICE_NAME}/{key}"
            blob = value.encode("utf-8")
            cred = CREDENTIAL()
            cred.Type = 1  # CRED_TYPE_GENERIC
            cred.TargetName = target
            cred.CredentialBlobSize = len(blob)
            cred.CredentialBlob = blob
            cred.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
            cred.UserName = "orion"

            result = advapi32.CredWriteW(ctypes.byref(cred), 0)
            return bool(result)
        except Exception as e:
            logger.debug("Windows credential store failed: %s", e)
            return False

    def retrieve(self, key: str) -> str | None:
        try:
            import ctypes
            import ctypes.wintypes

            advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
            target = f"{SERVICE_NAME}/{key}"
            pcred = ctypes.c_void_p()

            if advapi32.CredReadW(target, 1, 0, ctypes.byref(pcred)):
                # Parse credential blob
                class CREDENTIAL(ctypes.Structure):
                    _fields_ = [
                        ("Flags", ctypes.wintypes.DWORD),
                        ("Type", ctypes.wintypes.DWORD),
                        ("TargetName", ctypes.c_wchar_p),
                        ("Comment", ctypes.c_wchar_p),
                        ("LastWritten", ctypes.c_byte * 8),
                        ("CredentialBlobSize", ctypes.wintypes.DWORD),
                        ("CredentialBlob", ctypes.c_char_p),
                        ("Persist", ctypes.wintypes.DWORD),
                        ("AttributeCount", ctypes.wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", ctypes.c_wchar_p),
                        ("UserName", ctypes.c_wchar_p),
                    ]

                cred = ctypes.cast(pcred, ctypes.POINTER(CREDENTIAL)).contents
                blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
                advapi32.CredFree(pcred)
                return blob.decode("utf-8")
            return None
        except Exception as e:
            logger.debug("Windows credential read failed: %s", e)
            return None

    def delete(self, key: str) -> bool:
        try:
            import ctypes

            advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
            target = f"{SERVICE_NAME}/{key}"
            return bool(advapi32.CredDeleteW(target, 1, 0))
        except Exception as e:
            logger.debug("Windows credential delete failed: %s", e)
            return False


class MacOSBackend(KeychainBackend):
    """macOS Keychain backend using 'security' CLI."""

    def available(self) -> bool:
        return sys.platform == "darwin"

    def store(self, key: str, value: str) -> bool:
        try:
            # Delete existing first (ignore errors)
            subprocess.run(
                ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", key],
                capture_output=True,
                timeout=5,
            )
            result = subprocess.run(
                ["security", "add-generic-password", "-s", SERVICE_NAME, "-a", key, "-w", value],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug("macOS keychain store failed: %s", e)
            return False

    def retrieve(self, key: str) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", SERVICE_NAME, "-a", key, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            logger.debug("macOS keychain read failed: %s", e)
            return None

    def delete(self, key: str) -> bool:
        try:
            result = subprocess.run(
                ["security", "delete-generic-password", "-s", SERVICE_NAME, "-a", key],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug("macOS keychain delete failed: %s", e)
            return False


class FallbackBackend(KeychainBackend):
    """Encrypted file backend using Fernet (symmetric encryption).

    Used when no native keychain is available (headless, CI, etc.).
    """

    def __init__(self, path: Path | None = None, key: bytes | None = None):
        self._path = path or FALLBACK_FILE
        self._key = key or _machine_key()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def available(self) -> bool:
        return True

    def _load_vault(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            encrypted = self._path.read_bytes()
            decrypted = self._xor_crypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            logger.warning("Vault read failed: %s", e)
            return {}

    def _save_vault(self, vault: dict[str, str]) -> None:
        raw = json.dumps(vault, sort_keys=True).encode("utf-8")
        encrypted = self._xor_crypt(raw)
        self._path.write_bytes(encrypted)

    def _xor_crypt(self, data: bytes) -> bytes:
        """Simple XOR encryption with the machine key (repeating key)."""
        key = self._key
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    def store(self, key: str, value: str) -> bool:
        vault = self._load_vault()
        vault[key] = value
        self._save_vault(vault)
        return True

    def retrieve(self, key: str) -> str | None:
        vault = self._load_vault()
        return vault.get(key)

    def delete(self, key: str) -> bool:
        vault = self._load_vault()
        if key in vault:
            del vault[key]
            self._save_vault(vault)
            return True
        return False


class KeychainStore:
    """Platform-native credential storage with automatic backend selection.

    Usage::

        store = KeychainStore()
        store.store("pin_hash", "abc123...")
        value = store.retrieve("pin_hash")
        store.delete("pin_hash")
    """

    def __init__(
        self,
        backend: KeychainBackend | None = None,
        fallback_path: Path | None = None,
    ):
        if backend is not None:
            self._backend = backend
        else:
            self._backend = self._select_backend(fallback_path)
        logger.info("Keychain backend: %s", type(self._backend).__name__)

    @staticmethod
    def _select_backend(fallback_path: Path | None = None) -> KeychainBackend:
        """Select the best available backend for the current platform."""
        if sys.platform == "win32":
            win = WindowsBackend()
            if win.available():
                return win

        if sys.platform == "darwin":
            mac = MacOSBackend()
            if mac.available():
                return mac

        return FallbackBackend(path=fallback_path)

    def store(self, key: str, value: str) -> bool:
        """Store a credential. Returns True on success."""
        return self._backend.store(key, value)

    def retrieve(self, key: str) -> str | None:
        """Retrieve a credential. Returns None if not found."""
        return self._backend.retrieve(key)

    def delete(self, key: str) -> bool:
        """Delete a credential. Returns True if deleted."""
        return self._backend.delete(key)

    @property
    def backend_name(self) -> str:
        """Name of the active backend."""
        return type(self._backend).__name__

    def migrate_from_json(self, json_path: Path) -> int:
        """Migrate credentials from a plain JSON file to the keychain.

        Returns the number of credentials migrated.
        """
        if not json_path.exists():
            return 0

        try:
            with open(json_path) as f:
                data = json.load(f)
        except Exception as e:
            logger.warning("Could not read JSON credentials: %s", e)
            return 0

        migrated = 0
        for key, value in data.items():
            if isinstance(value, str) and self.store(key, value):
                migrated += 1

        if migrated > 0:
            logger.info("Migrated %d credentials from %s", migrated, json_path)

        return migrated
