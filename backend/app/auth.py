from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.core import get_db
from app.database.models import User

settings = get_settings()
ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return ph.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    """Verify an Argon2 hash against a password."""
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: str) -> str:
    """Create a signed JWT access token for a user."""
    expire = datetime.now(UTC) + timedelta(days=7)
    to_encode = {"sub": user_id, "exp": expire}
    secret = settings.SESSION_SECRET.get_secret_value()
    return jwt.encode(to_encode, secret, algorithm="HS256")


def verify_access_token(token: str) -> str | None:
    """Verify a JWT access token and return the user ID (subject)."""
    try:
        secret = settings.SESSION_SECRET.get_secret_value()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        user_id: str | None = payload.get("sub")
        return user_id
    except jwt.InvalidTokenError:
        return None


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:  # noqa: B008
    """FastAPI dependency to retrieve the current user from the session cookie."""
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = verify_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return user
