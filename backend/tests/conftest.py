import os

# Set test env vars BEFORE any app imports so Settings() never fails
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5433/test_db")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-chars!!!")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-32-chars!!!")
os.environ.setdefault("LLM_PROVIDER", "fake")
