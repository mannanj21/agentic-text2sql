from typing import Any

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.database.core import get_db
from app.database.models import User

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    # Validate and normalize email
    try:
        email_info = validate_email(req.email, check_deliverability=False)
        normalized_email = email_info.normalized
    except EmailNotValidError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Password policy (e.g. min 8 chars)
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    # Check for existing user
    result = await db.execute(select(User).where(User.email == normalized_email))
    if result.scalars().first():
        # Do not leak user existence specifically, use generic error message
        raise HTTPException(status_code=400, detail="Invalid email or password")

    hashed_pw = hash_password(req.password)
    user = User(email=normalized_email, password_hash=hashed_pw)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"message": "User registered successfully", "id": user.id}


@router.post("/login")
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    try:
        email_info = validate_email(req.email, check_deliverability=False)
        normalized_email = email_info.normalized
    except EmailNotValidError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalars().first()

    if not user or not verify_password(user.password_hash, req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create token
    token = create_access_token(user.id)

    # Set httpOnly cookie
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=get_settings().APP_ENV == "production",
        max_age=7 * 24 * 3600,
    )

    return {"message": "Logged in successfully"}


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(
        key="session",
        httponly=True,
        samesite="lax",
        secure=get_settings().APP_ENV == "production",
    )
    return {"message": "Logged out successfully"}
