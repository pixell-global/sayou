from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = {"env_prefix": "SAYOU_", "env_file": str(_PROJECT_ROOT / ".env")}

    # Database
    database_url: str = "sqlite+aiosqlite:///./sayou.db"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False

    # S3 storage
    s3_bucket_name: str = "pixell-agents"
    s3_region: str = "us-east-2"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str | None = None

    # Identity (set via MCP config env vars)
    org_id: str = ""
    user_id: str = ""
    workspace_slug: str = "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
