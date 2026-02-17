"""E2B sandbox lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

MAX_OUTPUT_SIZE = 32 * 1024
SANDBOX_CREATION_TIMEOUT = 30.0
EXECUTION_TIMEOUT = 60.0
CLEANUP_TIMEOUT = 10.0
STALE_SANDBOX_AGE = 300
REAPER_INTERVAL = 60


class SandboxManager:
    """Manages E2B sandbox lifecycle per session."""

    def __init__(self, api_key: str | None = None, timeout: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self._sandboxes: dict[str, Any] = {}
        self._sandbox_created_at: dict[str, float] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._cleaning_sessions: set[str] = set()
        self._reaper_task: asyncio.Task[None] | None = None
        self._enabled = bool(api_key)

        if not self._enabled:
            logger.info("E2B API key not configured — sandbox operations disabled")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _truncate_output(self, text: str | None, max_size: int = MAX_OUTPUT_SIZE) -> str:
        if not text or len(text) <= max_size:
            return text or ""
        half = max_size // 2
        truncated_bytes = len(text) - max_size
        return f"{text[:half]}\n\n... [truncated {truncated_bytes:,} bytes] ...\n\n{text[-half:]}"

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()
            return self._session_locks[session_id]

    async def _create_sandbox_with_timeout(self) -> Any:
        try:
            from e2b_code_interpreter import Sandbox

            sandbox = await asyncio.wait_for(
                asyncio.to_thread(Sandbox.create, timeout=self.timeout, api_key=self.api_key),
                timeout=SANDBOX_CREATION_TIMEOUT,
            )
            return sandbox
        except ImportError:
            raise RuntimeError("e2b_code_interpreter not installed")

    async def get_or_create(self, session_id: str) -> Any:
        if not self._enabled:
            raise RuntimeError("Sandbox not configured — set SAYOU_AGENT_E2B_API_KEY")

        if session_id in self._cleaning_sessions:
            raise RuntimeError("Sandbox is being cleaned up")

        lock = await self._get_session_lock(session_id)
        async with lock:
            if session_id in self._sandboxes:
                return self._sandboxes[session_id]

            logger.info(f"Creating sandbox for session {session_id}")
            sandbox = await self._create_sandbox_with_timeout()
            self._sandboxes[session_id] = sandbox
            self._sandbox_created_at[session_id] = time.time()
            return sandbox

    async def execute_code(self, session_id: str, code: str) -> dict[str, Any]:
        sandbox = await self.get_or_create(session_id)
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(sandbox.run_code, code),
                timeout=EXECUTION_TIMEOUT,
            )
            stdout = result.logs.stdout if result.logs else []
            stderr = result.logs.stderr if result.logs else []
            if isinstance(stdout, list):
                stdout = "".join(stdout)
            if isinstance(stderr, list):
                stderr = "".join(stderr)
            return {
                "stdout": self._truncate_output(stdout),
                "stderr": self._truncate_output(stderr),
                "error": str(result.error) if result.error else None,
            }
        except TimeoutError:
            return {"stdout": "", "stderr": "", "error": f"Execution timed out after {EXECUTION_TIMEOUT}s"}
        except Exception as e:
            return {"stdout": "", "stderr": "", "error": str(e)}

    async def execute_bash(self, session_id: str, command: str) -> dict[str, Any]:
        code = f"""
import subprocess, sys
result = subprocess.run({repr(command)}, shell=True, capture_output=True, text=True, timeout=55)
print(result.stdout, end='')
print(result.stderr, file=sys.stderr, end='')
if result.returncode != 0:
    raise RuntimeError(f"Command exited with code {{result.returncode}}")
"""
        return await self.execute_code(session_id, code)

    async def cleanup(self, session_id: str) -> None:
        self._cleaning_sessions.add(session_id)
        try:
            lock = await self._get_session_lock(session_id)
            async with lock:
                if session_id in self._sandboxes:
                    sandbox = self._sandboxes.pop(session_id)
                    self._sandbox_created_at.pop(session_id, None)
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(sandbox.kill),
                            timeout=CLEANUP_TIMEOUT,
                        )
                    except Exception as e:
                        logger.warning(f"Error cleaning up sandbox: {e}")
        finally:
            self._cleaning_sessions.discard(session_id)
            async with self._global_lock:
                self._session_locks.pop(session_id, None)

    async def cleanup_all(self) -> None:
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            self._reaper_task = None

        for session_id in list(self._sandboxes.keys()):
            await self.cleanup(session_id)

    async def start_reaper(self) -> None:
        if not self._reaper_task:
            self._reaper_task = asyncio.create_task(self._reap_stale())

    async def _reap_stale(self) -> None:
        while True:
            try:
                await asyncio.sleep(REAPER_INTERVAL)
                now = time.time()
                stale = [
                    sid for sid, created_at in self._sandbox_created_at.items()
                    if now - created_at > STALE_SANDBOX_AGE
                ]
                for sid in stale:
                    logger.info(f"Reaping stale sandbox: {sid}")
                    await self.cleanup(sid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reaper error: {e}")
