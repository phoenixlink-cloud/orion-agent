"""
Tests for orion.security.store -- Secure Credential Store.

Tests the SecureStore with encrypted file backend (Fernet),
credential CRUD operations, audit logging, and key migration.
"""

import json
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def tmp_store_dir(tmp_path):
    """Create a temporary store directory."""
    store_dir = tmp_path / "security"
    store_dir.mkdir()
    return store_dir


@pytest.fixture
def secure_store(tmp_store_dir):
    """Create a SecureStore instance with temp directory, keyring disabled."""
    # Reset singleton
    import orion.security.store as store_mod
    store_mod._instance = None

    from orion.security.store import SecureStore
    store = SecureStore(store_dir=tmp_store_dir)
    # Disable keyring to avoid system-wide side effects in tests
    store._keyring._available = False
    return store


class TestSecureStoreInit:
    """Test SecureStore initialization."""

    def test_creates_store_directory(self, tmp_path):
        store_dir = tmp_path / "new_security_dir"
        assert not store_dir.exists()

        import orion.security.store as store_mod
        store_mod._instance = None
        from orion.security.store import SecureStore
        store = SecureStore(store_dir=store_dir)
        assert store_dir.exists()

    def test_backend_name_not_none(self, secure_store):
        # Should have at least encrypted_file if cryptography is installed
        assert secure_store.backend_name in ("keyring", "encrypted_file", "none")

    def test_is_available(self, secure_store):
        # Should be True if cryptography is installed
        try:
            import cryptography
            assert secure_store.is_available
        except ImportError:
            # Without cryptography and keyring, may be False
            pass


class TestCredentialCRUD:
    """Test set/get/delete/list operations."""

    def test_set_and_get_key(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        backend = secure_store.set_key("test_provider", "test_secret_123")
        assert backend in ("keyring", "encrypted_file")

        retrieved = secure_store.get_key("test_provider")
        assert retrieved == "test_secret_123"

    def test_get_nonexistent_key(self, secure_store):
        result = secure_store.get_key("nonexistent_provider")
        assert result is None

    def test_delete_key(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        secure_store.set_key("delete_me", "value123")
        assert secure_store.has_key("delete_me")

        deleted = secure_store.delete_key("delete_me")
        assert deleted is True
        assert secure_store.get_key("delete_me") is None

    def test_delete_nonexistent_key(self, secure_store):
        deleted = secure_store.delete_key("never_existed")
        assert deleted is False

    def test_list_providers(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        secure_store.set_key("provider_a", "key_a")
        secure_store.set_key("provider_b", "key_b")
        providers = secure_store.list_providers()
        assert "provider_a" in providers
        assert "provider_b" in providers

    def test_has_key(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        import uuid
        unique_key = f"check_{uuid.uuid4().hex[:8]}"
        assert not secure_store.has_key(unique_key)
        secure_store.set_key(unique_key, "value")
        assert secure_store.has_key(unique_key)

    def test_overwrite_key(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        secure_store.set_key("overwrite_test", "original")
        secure_store.set_key("overwrite_test", "updated")
        assert secure_store.get_key("overwrite_test") == "updated"


class TestKeyRotation:
    """Test key rotation."""

    def test_rotate_key(self, secure_store):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        secure_store.set_key("rotate_me", "old_value")
        backend = secure_store.rotate_key("rotate_me", "new_value")
        assert backend in ("keyring", "encrypted_file")
        assert secure_store.get_key("rotate_me") == "new_value"


class TestMigration:
    """Test plaintext key migration."""

    def test_migrate_plaintext_keys(self, secure_store, tmp_store_dir):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        # Create a fake plaintext keys file
        plaintext_path = tmp_store_dir.parent / "api_keys.json"
        plaintext_path.write_text(json.dumps({
            "openai": "sk-test-12345678",
            "anthropic": "sk-ant-test-12345678",
        }))

        migrated = secure_store.migrate_plaintext_keys(plaintext_path)
        assert "openai" in migrated
        assert "anthropic" in migrated

        # Verify keys are accessible from secure store
        assert secure_store.get_key("openai") == "sk-test-12345678"
        assert secure_store.get_key("anthropic") == "sk-ant-test-12345678"

        # Original file should be renamed
        assert not plaintext_path.exists()
        assert plaintext_path.with_suffix(".json.migrated").exists()

    def test_migrate_empty_file(self, secure_store, tmp_store_dir):
        plaintext_path = tmp_store_dir.parent / "empty_keys.json"
        plaintext_path.write_text("{}")
        migrated = secure_store.migrate_plaintext_keys(plaintext_path)
        assert migrated == {}

    def test_migrate_nonexistent_file(self, secure_store):
        migrated = secure_store.migrate_plaintext_keys(Path("/nonexistent/keys.json"))
        assert migrated == {}


class TestAuditLog:
    """Test audit logging."""

    def test_audit_log_created(self, secure_store, tmp_store_dir):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        secure_store.set_key("audit_test", "value")
        secure_store.get_key("audit_test")

        audit_path = tmp_store_dir / "audit.log"
        assert audit_path.exists()

        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) >= 2  # At least set + get

        # Parse and validate first entry
        entry = json.loads(lines[0])
        assert entry["action"] == "set"
        assert entry["provider"] == "audit_test"
        assert entry["success"] is True


class TestGetStatus:
    """Test diagnostics status."""

    def test_get_status_structure(self, secure_store):
        status = secure_store.get_status()
        assert "available" in status
        assert "backend" in status
        assert "keyring_available" in status
        assert "encrypted_file_available" in status
        assert "stored_providers" in status
        assert "store_dir" in status


class TestMetadata:
    """Test credential metadata tracking."""

    def test_metadata_timestamps(self, secure_store, tmp_store_dir):
        if not secure_store.is_available:
            pytest.skip("No secure backend available")

        before = time.time()
        secure_store.set_key("ts_test", "value")
        after = time.time()

        meta_path = tmp_store_dir / "credentials.meta.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert "ts_test" in meta
        assert before <= meta["ts_test"]["created_at"] <= after
        assert meta["ts_test"]["backend"] in ("keyring", "encrypted_file")


class TestFernetBackend:
    """Test encrypted file backend specifics."""

    def test_vault_encrypted_on_disk(self, tmp_store_dir):
        """Ensure vault file is not readable as plain JSON."""
        try:
            from orion.security.store import _FernetBackend
        except ImportError:
            pytest.skip("cryptography not installed")

        backend = _FernetBackend(tmp_store_dir)
        if not backend.available:
            pytest.skip("Fernet backend unavailable")

        backend.set("test", "secret_value")
        vault_path = tmp_store_dir / "vault.enc"
        assert vault_path.exists()

        # The file should NOT be valid JSON (it's encrypted)
        raw = vault_path.read_bytes()
        with pytest.raises(Exception):
            json.loads(raw)

    def test_salt_persisted(self, tmp_store_dir):
        """Ensure salt is created and persisted."""
        try:
            from orion.security.store import _FernetBackend
        except ImportError:
            pytest.skip("cryptography not installed")

        backend = _FernetBackend(tmp_store_dir)
        if not backend.available:
            pytest.skip("Fernet backend unavailable")

        salt_path = tmp_store_dir / "vault.salt"
        assert salt_path.exists()
        assert len(salt_path.read_bytes()) == 32


class TestSingleton:
    """Test singleton access pattern."""

    def test_get_secure_store_returns_same_instance(self, tmp_store_dir):
        import orion.security.store as store_mod
        store_mod._instance = None

        from orion.security.store import get_secure_store
        store1 = get_secure_store(tmp_store_dir)
        store2 = get_secure_store(tmp_store_dir)
        assert store1 is store2

        # Clean up
        store_mod._instance = None


class TestNoBackendAvailable:
    """Test behavior when no backend is available."""

    def test_set_key_raises_without_backend(self, tmp_store_dir):
        from orion.security.store import SecureStore

        store = SecureStore(store_dir=tmp_store_dir)
        # Mock both backends as unavailable
        store._keyring._available = False
        store._fernet._available = False

        with pytest.raises(RuntimeError, match="No secure storage backend"):
            store.set_key("test", "value")
