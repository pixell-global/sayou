import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import model_validator
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SAYOU_HOME = Path.home() / ".sayou"
_CONFIG_FILE = _SAYOU_HOME / "config.yaml"

# Field mapping from config.yaml keys to Settings field names
_YAML_KEY_MAP = {
    "org_id": "org_id",
    "user_id": "user_id",
    "workspace": "workspace_slug",
    "database_url": "database_url",
}


def _load_config_file() -> dict:
    """Load config from ~/.sayou/config.yaml if it exists."""
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE) as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


class Settings(BaseSettings):
    model_config = {"env_prefix": "SAYOU_", "env_file": str(_PROJECT_ROOT / ".env")}

    # Database
    database_url: str = ""
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
    org_id: str = "local"
    user_id: str = "default-user"
    workspace_slug: str = "default"

    @model_validator(mode="after")
    def _apply_defaults(self) -> "Settings":
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{_SAYOU_HOME / 'sayou.db'}"
        return self

    # Embeddings (semantic search)
    embedding_provider: str = ""  # "openai" or "" (disabled)
    embedding_api_key: str = ""
    embedding_model: str = ""  # default per provider

    # Auto-Metadata
    metadata_provider: str = ""  # "openai" or "" (disabled)
    metadata_api_key: str = ""
    metadata_model: str = ""  # default per provider
    auto_metadata_enabled: bool = False  # master switch


class ConfigError(Exception):
    """Raised when configuration is invalid or services are unreachable."""


def format_error(e: Exception, context: dict | None = None) -> str:
    """Convert exceptions to actionable error messages for MCP clients."""
    from sayou.core.workspace import AccessDeniedError, FileNotFoundError

    ctx = context or {}
    msg = str(e)

    if isinstance(e, FileNotFoundError):
        path = ctx.get("path", "unknown")
        return f"File '{path}' not found. Use workspace_list to see available files."

    if isinstance(e, AccessDeniedError):
        return (
            f"Permission denied for org '{ctx.get('org_id', 'unknown')}'. "
            f"Check SAYOU_ORG_ID configuration."
        )

    if "connection" in msg.lower() or "database" in msg.lower():
        return "Database connection error. Run 'sayou status' to diagnose."

    if "s3" in msg.lower() or "NoCredentialsError" in type(e).__name__:
        return "S3 credentials invalid. Check SAYOU_S3_ACCESS_KEY_ID env var."

    return f"Error: {type(e).__name__}: {msg}"


@lru_cache
def get_settings() -> Settings:
    """Load settings with config file fallback.

    Priority: env vars > config.yaml > built-in defaults.
    """
    file_config = _load_config_file()
    overrides = {}
    for yaml_key, field_name in _YAML_KEY_MAP.items():
        env_key = f"SAYOU_{field_name.upper()}"
        if yaml_key in file_config and not os.environ.get(env_key):
            val = file_config[yaml_key]
            if val:  # skip empty values
                overrides[field_name] = val
    return Settings(**overrides)


settings = get_settings()
