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
# Short-lived access token session duration (60 minutes per §12)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Abuse protection (§12): only trust X-Forwarded-For when explicitly enabled.
# Without a trusted proxy, clients can spoof X-Forwarded-For to mint fresh
# identifiers and bypass anonymous quotas/rate limits. Deployments behind a
# reverse proxy must set TRUST_PROXY_HEADERS=1 explicitly.
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "0") == "1"

