#!/usr/bin/env node

/**
 * session-end.js — Stop hook.
 *
 * Writes a brief session summary to sessions/YYYY-MM-DD-{short_id}.md
 * if the workspace was used during this session. Updates the
 * plugin.last_active KV key for the SessionStart delta display.
 *
 * Supports cloud mode (MCP endpoint via fetch) and local mode (CLI).
 */

import { randomBytes } from "node:crypto";
import {
  isCloudMode,
  workspaceRead,
  workspaceWrite,
  kvSet,
  cliRun,
  cliWrite,
} from "./helpers.js";

function extractStats(activityContent) {
  const lines = activityContent
    .split("\n")
    .filter((l) => /^- \d{2}:\d{2}/.test(l));
  if (lines.length === 0) return null;

  const types = { change: 0, command: 0, discovery: 0 };
  for (const line of lines) {
    const match = line.match(/\[(\w+)\]/);
    if (match && types[match[1]] !== undefined) {
      types[match[1]]++;
    }
  }

  return { total: lines.length, ...types };
}

function buildSessionContent(stats, activity, now) {
  const date = now.toISOString().slice(0, 10);

  const parts = [];
  if (stats.change > 0) parts.push(`${stats.change} changes`);
  if (stats.command > 0) parts.push(`${stats.command} commands`);
  if (stats.discovery > 0) parts.push(`${stats.discovery} discoveries`);
  const statLine = parts.join(", ");

  const recentLines = activity
    .split("\n")
    .filter((l) => /^- \d{2}:\d{2}/.test(l))
    .slice(-10)
    .join("\n");

  return [
    "---",
    "type: session-summary",
    `date: ${date}`,
    `entries: ${stats.total}`,
    `changes: ${stats.change}`,
    `commands: ${stats.command}`,
    `discoveries: ${stats.discovery}`,
    "---",
    `# Session — ${date}`,
    "",
    statLine,
    "",
    "## Recent Activity",
    "",
    recentLines,
    "",
  ].join("\n");
}

// ── Cloud mode ──────────────────────────────────────────────

async function cloudMain() {
  const now = new Date();

  // Update last active
  try {
    await kvSet("plugin.last_active", `"${now.toISOString()}"`);
  } catch {}

  // Check for today's activity
  const today = now.toISOString().slice(0, 10);
  let activity = null;
  try {
    activity = await workspaceRead(`activity/${today}.md`);
  } catch {}

  if (
    !activity ||
    (typeof activity === "string" &&
      (activity.includes("not found") ||
        activity.includes("does not exist") ||
        activity.includes("File not found")))
  ) {
    process.exit(0);
  }

  const stats = extractStats(activity);
  if (!stats || stats.total === 0) {
    process.exit(0);
  }

  const shortId = randomBytes(3).toString("hex");
  const path = `sessions/${today}-${shortId}.md`;
  const content = buildSessionContent(stats, activity, now);

  try {
    await workspaceWrite(path, content);
  } catch {}

  process.exit(0);
}

// ── Local mode ──────────────────────────────────────────────

function localMain() {
  const now = new Date();

  // Update last active
  cliRun(`sayou kv set "plugin.last_active" '"${now.toISOString()}"'`);

  // Check for today's activity
  const today = now.toISOString().slice(0, 10);
  const activity = cliRun(`sayou file read "activity/${today}.md"`);
  if (
    !activity ||
    activity.includes("not found") ||
    activity.includes("does not exist")
  ) {
    process.exit(0);
  }

  const stats = extractStats(activity);
  if (!stats || stats.total === 0) {
    process.exit(0);
  }

  const shortId = randomBytes(3).toString("hex");
  const path = `sessions/${today}-${shortId}.md`;
  const content = buildSessionContent(stats, activity, now);

  cliWrite(path, content);
  process.exit(0);
}

// ── Entry point ─────────────────────────────────────────────

async function main() {
  try {
    if (isCloudMode()) {
      await cloudMain();
    } else {
      localMain();
    }
  } catch {
    // Never fail, never block
  }
  process.exit(0);
}

main();
