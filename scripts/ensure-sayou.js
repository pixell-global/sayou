#!/usr/bin/env node

/**
 * ensure-sayou.js — Verify sayou connectivity (cloud or local).
 *
 * Runs before session-start.js. Cloud-first: checks for API key,
 * then falls back to local CLI. If neither is available, outputs
 * setup instructions but always exits 0 (never blocks session start).
 *
 * Sets a flag file at ~/.sayou/.plugin-ok on success so subsequent
 * hooks can skip re-checking.
 */

import { existsSync, writeFileSync } from "node:fs";
import {
  getApiKey,
  isCLIAvailable,
  ensureDir,
  SAYOU_DIR,
  FLAG_FILE,
} from "./helpers.js";

function main() {
  // Fast path: already verified this install
  if (existsSync(FLAG_FILE)) {
    process.exit(0);
  }

  // Cloud mode: API key found
  if (getApiKey()) {
    ensureDir(SAYOU_DIR);
    writeFileSync(FLAG_FILE, `cloud:${new Date().toISOString()}`);
    process.exit(0);
  }

  // Local mode: CLI available
  if (isCLIAvailable()) {
    ensureDir(SAYOU_DIR);
    writeFileSync(FLAG_FILE, `local:${new Date().toISOString()}`);
    process.exit(0);
  }

  // Neither found — show setup instructions
  const msg = [
    "[sayou] Connect your workspace:",
    "",
    "  Cloud (recommended):",
    "    1. Create an API key at https://drive.sayou.dev/settings",
    "    2. Run: sayou auth",
    "    3. Restart Claude Code",
    "",
    "  Local:",
    "    pip install sayou && sayou init",
    "",
    "  docs: github.com/pixell-global/sayou",
  ].join("\n");
  process.stdout.write(msg + "\n");
  process.exit(0);
}

main();
