"""Unit tests for auth module: hashing, JWT, password policy."""

from app.auth import create_access_token, hash_password, verify_access_token, verify_password


def test_hash_and_verify_password() -> None:
    hashed = hash_password("securepassword123")
    assert hashed != "securepassword123"
    assert verify_password(hashed, "securepassword123")


def test_wrong_password_fails_verification() -> None:
    hashed = hash_password("correctpassword")
    assert not verify_password(hashed, "wrongpassword")


def test_hash_format_is_argon2() -> None:
    hashed = hash_password("anypassword!")
    assert hashed.startswith("$argon2"), f"Expected argon2 hash, got: {hashed[:20]}"


def test_access_token_round_trip() -> None:
    user_id = "user-abc-123"
    token = create_access_token(user_id)
    assert isinstance(token, str)
    assert len(token) > 20
    decoded_id = verify_access_token(token)
    assert decoded_id == user_id


def test_tampered_token_fails() -> None:
    token = create_access_token("user-1")
    parts = token.split(".")
    parts[1] = parts[1][:-3] + "abc"
    bad_token = ".".join(parts)
    assert verify_access_token(bad_token) is None


def test_invalid_token_returns_none() -> None:
    assert verify_access_token("not.a.valid.jwt") is None
    assert verify_access_token("") is None


def test_token_never_contains_user_email() -> None:
    """Sensitive data must not appear in the token."""
    import base64

    token = create_access_token("user-xyz")
    # Decode payload (middle part) and check
    payload_part = token.split(".")[1]
    # Pad and decode
    padded = payload_part + "=" * (4 - len(payload_part) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode()
    assert "password" not in decoded
    assert "email" not in decoded
