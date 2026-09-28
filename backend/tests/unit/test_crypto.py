import pytest
from cryptography.fernet import Fernet

from app.config import Settings
from app.database.crypto import CredentialCipher, CredentialEncryptionError


def test_credential_cipher_round_trip_and_key_prefix() -> None:
    cipher = CredentialCipher(Fernet.generate_key().decode(), key_id="primary")
    encrypted = cipher.encrypt("target-password")
    assert encrypted.startswith("primary:")
    assert cipher.decrypt(encrypted) == "target-password"


def test_credential_cipher_uses_random_ciphertext() -> None:
    cipher = CredentialCipher(Fernet.generate_key().decode())
    assert cipher.encrypt("target-password") != cipher.encrypt("target-password")


def test_credential_cipher_rejects_wrong_key_and_bad_prefix() -> None:
    encrypted = CredentialCipher(Fernet.generate_key().decode()).encrypt("target-password")
    with pytest.raises(CredentialEncryptionError):
        CredentialCipher(Fernet.generate_key().decode()).decrypt(encrypted)
    with pytest.raises(CredentialEncryptionError):
        CredentialCipher(Fernet.generate_key().decode()).decrypt("not-a-ciphertext")


def test_credential_cipher_rejects_missing_or_invalid_key() -> None:
    with pytest.raises(CredentialEncryptionError, match="valid Fernet key"):
        CredentialCipher("")


def test_settings_refuse_to_start_without_an_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        Settings(_env_file=None)
