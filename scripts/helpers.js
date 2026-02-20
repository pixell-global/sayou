/**
 * helpers.js — Shared module for sayou plugin hooks.
 *
 * Provides cloud (HTTP fetch to MCP endpoint) and local (CLI execSync)
 * modes with unified workspace and KV operations.
 *
 * Cloud mode: API key from ~/.sayou/api-key or $SAYOU_API_KEY
 * Local mode: sayou CLI on PATH
 */

import { execSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

export const SAYOU_DIR = join(homedir(), ".sayou");
export const API_KEY_FILE = join(SAYOU_DIR, "api-key");
export const FLAG_FILE = join(SAYOU_DIR, ".plugin-ok");
const MCP_ENDPOINT = "https://drive.sayou.dev/api/v1/mcp";

// ── Mode detection ──────────────────────────────────────────

export function getApiKey() {
  if (process.env.SAYOU_API_KEY) {
    return process.env.SAYOU_API_KEY.trim();
  }
  try {
    if (existsSync(API_KEY_FILE)) {
      return readFileSync(API_KEY_FILE, "utf-8").trim();
    }
  } catch {
    // ignore
  }
  return null;
}

export function isCloudMode() {
  return !!getApiKey();
}

export function isCLIAvailable() {
  try {
    execSync("sayou status", { stdio: "pipe", timeout: 10000 });
    return true;
  } catch {
    return false;
  }
}

// ── Cloud: MCP JSON-RPC over HTTP ───────────────────────────

let _mcpId = 0;

export async function mcpCall(toolName, args = {}) {
  const key = getApiKey();
  if (!key) throw new Error("No API key");

  const resp = await fetch(MCP_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      method: "tools/call",
      params: { name: toolName, arguments: args },
      id: ++_mcpId,
    }),
  });

  if (!resp.ok) {
    throw new Error(`MCP ${resp.status}`);
  }

  const json = await resp.json();
  if (json.error) {
    throw new Error(json.error.message || "MCP error");
  }

  // Extract text from MCP tool result content array
  const content = json.result?.content;
  if (Array.isArray(content)) {
    const text = content.find((c) => c.type === "text");
    if (text) return text.text;
  }
  return json.result;
}

// ── Local: CLI helpers ──────────────────────────────────────

export function cliRun(cmd) {
  try {
    return execSync(cmd, {
      stdio: "pipe",
      timeout: 10000,
      encoding: "utf-8",
    }).trim();
  } catch {
    return null;
  }
}

export function cliWrite(path, content) {
  try {
    spawnSync("sayou", ["file", "write", path, "-"], {
      input: content,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: 10000,
    });
  } catch {
    // silent
  }
}

// ── Unified workspace operations ────────────────────────────

export async function workspaceList(path = "/", recursive = true) {
  if (isCloudMode()) {
    return await mcpCall("workspace_list", { path, recursive });
  }
  const flags = recursive ? "--recursive --json" : "--json";
  return cliRun(`sayou file list "${path}" ${flags}`);
}

export async function workspaceRead(path) {
  if (isCloudMode()) {
    return await mcpCall("workspace_read", { path });
  }
  return cliRun(`sayou file read "${path}"`);
}

export async function workspaceReadJson(path) {
  if (isCloudMode()) {
    return await mcpCall("workspace_read", { path });
  }
  return cliRun(`sayou file read "${path}" --json`);
}

export async function workspaceWrite(path, content) {
  if (isCloudMode()) {
    return await mcpCall("workspace_write", { path, content });
  }
  cliWrite(path, content);
}

export async function kvGet(key) {
  if (isCloudMode()) {
    try {
      const result = await mcpCall("workspace_kv", { action: "get", key });
      if (typeof result === "string") {
        if (result.startsWith("Key not found")) return null;
        // Format: "**key** = value"
        const match = result.match(/\*\*.*?\*\*\s*=\s*(.*)/s);
        if (match) return match[1].trim();
      }
      return result;
    } catch {
      return null;
    }
  }
  return cliRun(`sayou kv get "${key}"`);
}

export async function kvSet(key, value) {
  const val = typeof value === "string" ? value : JSON.stringify(value);
  if (isCloudMode()) {
    await mcpCall("workspace_kv", { action: "set", key, value: val });
  } else {
    cliRun(`sayou kv set "${key}" '${val}'`);
  }
}

// ── Utilities ───────────────────────────────────────────────

export function ensureDir(dir) {
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}
