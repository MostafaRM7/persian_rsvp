import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Database configuration (defaults to SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite://{BASE_DIR / 'db.sqlite3'}")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# JWT Authentication configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if ENVIRONMENT == "production":
        raise RuntimeError("CRITICAL: SECRET_KEY environment variable must be set in production!")
    SECRET_KEY = "persian-rsvp-super-secret-key-change-in-production-32chars-min"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
