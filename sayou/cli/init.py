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

MCP_ENTRY = {
    "command": "sayou",
}

EDITOR_CONFIGS: dict[str, Path] = {
    "claude": Path.home() / ".claude" / "mcp.json",
    "cursor": Path.cwd() / ".cursor" / "mcp.json",
    "windsurf": Path.home() / ".codeium" / "windsurf" / "mcp_config.json",
}


def _configure_editor(editor: str) -> None:
    """Add sayou to an editor's MCP config file."""
    path = EDITOR_CONFIGS[editor]

    # Read existing config or start fresh
    if path.exists():
        with open(path) as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                print(f"  Warning: {path} contains invalid JSON, overwriting")
                config = {}
    else:
        config = {}

    servers = config.setdefault("mcpServers", {})

    if "sayou" in servers:
        print(f"  Already configured in {path}")
        return

    servers["sayou"] = MCP_ENTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"  Configured {path}")


async def run_init(editor: str | None = None) -> None:
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

    # 4. Configure editor or print manual instructions
    if editor:
        _configure_editor(editor)
        print(f"\n  Restart {editor.title()} to connect.")
    else:
        print(f"\nReady! Add to your MCP client config:\n")
        mcp_config = {"mcpServers": {"sayou": MCP_ENTRY}}
        print(json.dumps(mcp_config, indent=2))
        print()
        print("Or re-run with an editor flag to auto-configure:")
        print("  sayou init --claude")
        print("  sayou init --cursor")
        print("  sayou init --windsurf")
        print()
