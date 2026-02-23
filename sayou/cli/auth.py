"""sayou auth — manage Sayou Drive API key."""

from __future__ import annotations

import json
import os
import stat
import sys
import urllib.request
import urllib.error
from pathlib import Path

SAYOU_DIR = Path.home() / ".sayou"
API_KEY_FILE = SAYOU_DIR / "api-key"
FLAG_FILE = SAYOU_DIR / ".plugin-ok"
MCP_ENDPOINT = "https://drive.sayou.dev/api/v1/mcp"
KEY_PREFIX = "sk-sayou-"


def _get_saved_key() -> str | None:
    """Read saved API key from file or env."""
    env_key = os.environ.get("SAYOU_API_KEY")
    if env_key:
        return env_key.strip()
    if API_KEY_FILE.exists():
        return API_KEY_FILE.read_text().strip()
    return None


def _redact_key(key: str) -> str:
    """Redact API key for display: sk-sayou-abc...wxyz."""
    if len(key) <= 16:
        return key[:4] + "..." + key[-4:]
    return key[:12] + "..." + key[-4:]


def _validate_key(key: str) -> tuple[bool, str]:
    """Validate API key against Sayou Drive MCP endpoint.

    Returns (success, message).
    """
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 1,
    }).encode()

    req = urllib.request.Request(
        MCP_ENDPOINT,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, "Valid"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Invalid API key (401 Unauthorized)"
        return False, f"Server error ({e.code})"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except Exception as e:
        return False, f"Unexpected error: {e}"

    return False, "Unexpected response"


def _save_key(key: str) -> None:
    """Save API key to ~/.sayou/api-key with 600 permissions."""
    SAYOU_DIR.mkdir(parents=True, exist_ok=True)
    API_KEY_FILE.write_text(key + "\n")
    API_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600


def _clear_flag() -> None:
    """Delete .plugin-ok so ensure-sayou.js re-detects mode."""
    if FLAG_FILE.exists():
        FLAG_FILE.unlink()


async def run_auth_login() -> None:
    """Interactive: prompt for key, validate, save."""
    existing = _get_saved_key()
    if existing:
        redacted = _redact_key(existing)
        source = "env" if os.environ.get("SAYOU_API_KEY") else "file"
        print(f"  Existing key: {redacted} (from {source})")
        print()
        try:
            answer = input("  Replace it? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer not in ("y", "yes"):
            print("  Keeping existing key.")
            return
        print()

    print("  Get your API key from: https://drive.sayou.dev/settings")
    print()
    try:
        key = input("  Paste API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not key:
        print("  No key entered.")
        return

    # Format check
    if not key.startswith(KEY_PREFIX):
        print(f"  Error: Key must start with '{KEY_PREFIX}'")
        sys.exit(1)

    # Remote validation
    print("  Validating...", end="", flush=True)
    valid, message = _validate_key(key)
    if not valid:
        print(f" failed")
        print(f"  Error: {message}")
        sys.exit(1)

    print(f" ok")

    # Save
    _save_key(key)
    _clear_flag()

    print()
    print(f"  Saved to {API_KEY_FILE}")
    print("  Mode: cloud (Sayou Drive)")
    print()
    print("  Restart Claude Code to connect.")


async def run_auth_logout() -> None:
    """Remove saved API key."""
    if os.environ.get("SAYOU_API_KEY"):
        print("  Note: $SAYOU_API_KEY env var is set — unset it to fully disconnect.")
        print()

    if API_KEY_FILE.exists():
        API_KEY_FILE.unlink()
        _clear_flag()
        print("  Removed API key.")
        print("  Mode: local")
    else:
        print("  No saved API key found.")

    print()
    print("  Restart Claude Code to apply.")


async def run_auth_status() -> None:
    """Show current auth status."""
    key = _get_saved_key()
    if key:
        redacted = _redact_key(key)
        source = "env" if os.environ.get("SAYOU_API_KEY") else "file"
        print(f"  Mode:   cloud (Sayou Drive)")
        print(f"  Key:    {redacted} ({source})")
        print(f"  Server: {MCP_ENDPOINT}")
    else:
        print(f"  Mode:   local")
        print(f"  To connect: sayou auth")
