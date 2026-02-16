# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
"""Tests for Phase 10: KeychainStore — platform-native credential storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.ara.keychain import FallbackBackend, KeychainStore


@pytest.fixture
def fallback_path(tmp_path: Path) -> Path:
    return tmp_path / "vault.enc"


@pytest.fixture
def backend(fallback_path: Path) -> FallbackBackend:
    return FallbackBackend(path=fallback_path, key=b"test-key-32bytes-0123456789abcdef")


@pytest.fixture
def store(fallback_path: Path) -> KeychainStore:
    fb = FallbackBackend(path=fallback_path, key=b"test-key-32bytes-0123456789abcdef")
    return KeychainStore(backend=fb)


class TestFallbackBackend:
    def test_available(self, backend: FallbackBackend):
        assert backend.available() is True

    def test_store_and_retrieve(self, backend: FallbackBackend):
        assert backend.store("pin_hash", "abc123")
        assert backend.retrieve("pin_hash") == "abc123"

    def test_retrieve_missing(self, backend: FallbackBackend):
        assert backend.retrieve("nonexistent") is None

    def test_delete(self, backend: FallbackBackend):
        backend.store("key1", "val1")
        assert backend.delete("key1") is True
        assert backend.retrieve("key1") is None

    def test_delete_missing(self, backend: FallbackBackend):
        assert backend.delete("nonexistent") is False

    def test_multiple_keys(self, backend: FallbackBackend):
        backend.store("a", "1")
        backend.store("b", "2")
        backend.store("c", "3")
        assert backend.retrieve("a") == "1"
        assert backend.retrieve("b") == "2"
        assert backend.retrieve("c") == "3"

    def test_overwrite(self, backend: FallbackBackend):
        backend.store("key", "old")
        backend.store("key", "new")
        assert backend.retrieve("key") == "new"

    def test_persistence(self, fallback_path: Path):
        key = b"test-key-32bytes-0123456789abcdef"
        b1 = FallbackBackend(path=fallback_path, key=key)
        b1.store("persist", "value")

        b2 = FallbackBackend(path=fallback_path, key=key)
        assert b2.retrieve("persist") == "value"

    def test_wrong_key_fails(self, fallback_path: Path):
        b1 = FallbackBackend(path=fallback_path, key=b"key-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        b1.store("secret", "data")

        b2 = FallbackBackend(path=fallback_path, key=b"key-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        # Wrong key should fail to decrypt properly
        result = b2.retrieve("secret")
        # Either None or garbage (not the original value)
        assert result != "data" or result is None

    def test_encrypted_on_disk(self, backend: FallbackBackend, fallback_path: Path):
        backend.store("secret", "supersecretvalue")
        raw = fallback_path.read_bytes()
        # The raw bytes should NOT contain the plaintext
        assert b"supersecretvalue" not in raw


class TestKeychainStore:
    def test_store_retrieve_delete(self, store: KeychainStore):
        assert store.store("test_key", "test_value")
        assert store.retrieve("test_key") == "test_value"
        assert store.delete("test_key")
        assert store.retrieve("test_key") is None

    def test_backend_name(self, store: KeychainStore):
        assert store.backend_name == "FallbackBackend"

    def test_migrate_from_json(self, store: KeychainStore, tmp_path: Path):
        import json

        json_path = tmp_path / "auth.json"
        json_path.write_text(
            json.dumps(
                {
                    "pin_hash": "hash123",
                    "totp_secret": "secret456",
                }
            )
        )

        migrated = store.migrate_from_json(json_path)
        assert migrated == 2
        assert store.retrieve("pin_hash") == "hash123"
        assert store.retrieve("totp_secret") == "secret456"

    def test_migrate_empty_file(self, store: KeychainStore, tmp_path: Path):
        json_path = tmp_path / "empty.json"
        migrated = store.migrate_from_json(json_path)
        assert migrated == 0

    def test_migrate_nonexistent(self, store: KeychainStore, tmp_path: Path):
        migrated = store.migrate_from_json(tmp_path / "nope.json")
        assert migrated == 0
