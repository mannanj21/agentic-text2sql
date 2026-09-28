import asyncio
import os
import sys

from cryptography.fernet import Fernet

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test_user:test_password@localhost:5433/test_db"
)
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-32-chars!!!!!")
os.environ.setdefault("LLM_PROVIDER", "fake")
