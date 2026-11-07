import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-this-key")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///instance/artworks.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", "10485760"))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
