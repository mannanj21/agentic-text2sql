"""Encryption for target-database credentials.

Ciphertext is prefixed with a key id so future rotations can retain a decryptor
for old keys while new credentials are encrypted with the current key.
"""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

CURRENT_KEY_ID = "v1"


class CredentialEncryptionError(ValueError):
    """Raised when credential encryption or decryption cannot be completed."""


class CredentialCipher:
    def __init__(self, key: SecretStr | str, key_id: str = CURRENT_KEY_ID) -> None:
        if not key_id or ":" in key_id:
            raise CredentialEncryptionError(
                "Credential key id must be non-empty and contain no colon."
            )
        value = key.get_secret_value() if isinstance(key, SecretStr) else key
        try:
            self._fernet = Fernet(value.encode("ascii"))
        except (AttributeError, ValueError) as exc:
            raise CredentialEncryptionError("ENCRYPTION_KEY must be a valid Fernet key.") from exc
        self.key_id = key_id

    def encrypt(self, plaintext: str) -> str:
        return f"{self.key_id}:{self._fernet.encrypt(plaintext.encode('utf-8')).decode('ascii')}"

    def decrypt(self, ciphertext: str) -> str:
        try:
            key_id, token = ciphertext.split(":", maxsplit=1)
        except ValueError as exc:
            raise CredentialEncryptionError("Credential ciphertext has no key id prefix.") from exc
        if key_id != self.key_id:
            raise CredentialEncryptionError(f"Credential key id '{key_id}' is unavailable.")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as exc:
            raise CredentialEncryptionError("Credential ciphertext cannot be decrypted.") from exc
