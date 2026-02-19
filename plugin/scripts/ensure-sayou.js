#!/usr/bin/env node

/**
 * ensure-sayou.js — Verify sayou CLI is available.
 *
 * Runs before session-start.js. If sayou is missing, outputs install
 * instructions but always exits 0 (never blocks session start).
 * Sets a flag file at ~/.sayou/.plugin-ok on success so subsequent
 * hooks can skip re-checking.
 */

import { execSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const FLAG_DIR = join(homedir(), ".sayou");
const FLAG_FILE = join(FLAG_DIR, ".plugin-ok");

function sayouAvailable() {
  try {
    execSync("sayou status", { stdio: "pipe", timeout: 10000 });
    return true;
  } catch {
    return false;
  }
}

function main() {
  // Fast path: already verified this install
  if (existsSync(FLAG_FILE)) {
    process.exit(0);
  }

  if (sayouAvailable()) {
    // Mark as verified
    if (!existsSync(FLAG_DIR)) {
      mkdirSync(FLAG_DIR, { recursive: true });
    }
    writeFileSync(FLAG_FILE, new Date().toISOString());
    process.exit(0);
  }

  // sayou not found — try auto-install
  try {
    execSync("pip install sayou", { stdio: "pipe", timeout: 60000 });
  } catch {
    // pip install failed — show manual instructions
    const msg = [
      "[sayou] not found on PATH",
      "",
      "Install:  pip install sayou",
      "Then:     sayou init",
      "",
      "docs: github.com/pixell-global/sayou",
    ].join("\n");
    process.stdout.write(msg);
    process.exit(0);
  }

  // Verify install succeeded
  if (sayouAvailable()) {
    // Run init to create default workspace
    try {
      execSync("sayou init", { stdio: "pipe", timeout: 10000 });
    } catch {
      // init failure is non-fatal
    }

    if (!existsSync(FLAG_DIR)) {
      mkdirSync(FLAG_DIR, { recursive: true });
    }
    writeFileSync(FLAG_FILE, new Date().toISOString());
  } else {
    process.stdout.write("[sayou] install succeeded but CLI not on PATH. Restart your shell.\n");
  }

  process.exit(0);
}

main();
