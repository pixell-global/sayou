"""sayou init — initialize local setup."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

SAYOU_DIR = Path.home() / ".sayou"
CONFIG_FILE = SAYOU_DIR / "config.yaml"
DB_FILE = SAYOU_DIR / "sayou.db"
STORAGE_DIR = SAYOU_DIR / "storage"

DEFAULT_CONFIG = {
    "org_id": "local",
    "user_id": "default-user",
    "workspace": "default",
}

MCP_CONFIG = {
    "mcpServers": {
        "sayou": {
            "command": "sayou",
        }
    }
}


async def run_init() -> None:
    """Initialize sayou local setup."""
    # 1. Create directories
    SAYOU_DIR.mkdir(parents=True, exist_ok=True)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Created {SAYOU_DIR}")

    # 2. Write config.yaml (only if doesn't exist)
    if CONFIG_FILE.exists():
        print(f"  Config exists: {CONFIG_FILE}")
    else:
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
        print(f"  Created {CONFIG_FILE}")

    # 3. Initialize database
    from sayou.catalog.database import init_db

    db_url = f"sqlite+aiosqlite:///{DB_FILE}"
    await init_db(db_url)
    print(f"  Database ready: {DB_FILE}")

    # 4. Print MCP config
    print(f"\nReady! Add to your MCP client config:\n")
    print(json.dumps(MCP_CONFIG, indent=2))
    print()
