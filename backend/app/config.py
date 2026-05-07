import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    agent_name: str = "system-design-coach"
    database_path: str = "data/tutor.db"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"


def get_settings() -> Settings:
    return Settings(
        livekit_url=_required("LIVEKIT_URL"),
        livekit_api_key=_required("LIVEKIT_API_KEY"),
        livekit_api_secret=_required("LIVEKIT_API_SECRET"),
        agent_name=os.getenv("AGENT_NAME", "system-design-coach"),
        database_path=os.getenv("DATABASE_PATH", "data/tutor.db"),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080"),
    )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
