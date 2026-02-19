#!/usr/bin/env node

/**
 * session-end.js — Stop hook.
 *
 * Writes a brief session summary to sessions/YYYY-MM-DD-{short_id}.md
 * if the workspace was used during this session. Updates the
 * plugin.last_active KV key for the SessionStart delta display.
 */

import { execSync, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";

function run(cmd) {
  try {
    return execSync(cmd, { stdio: "pipe", timeout: 10000, encoding: "utf-8" }).trim();
  } catch {
    return null;
  }
}

function writeFile(path, content) {
  try {
    spawnSync("sayou", ["file", "write", path, "-"], {
      input: content,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: 10000,
    });
  } catch {
    // Silent failure
  }
}

function getTodayActivity() {
  const today = new Date().toISOString().slice(0, 10);
  const raw = run(`sayou file read "activity/${today}.md"`);
  if (!raw || raw.includes("not found") || raw.includes("does not exist")) {
    return null;
  }
  return raw;
}

function extractStats(activityContent) {
  const lines = activityContent.split("\n").filter((l) => /^- \d{2}:\d{2}/.test(l));
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

function main() {
  // Update last active
  const now = new Date().toISOString();
  run(`sayou kv set "plugin.last_active" '"${now}"'`);

  // Check if there's activity from today
  const activity = getTodayActivity();
  if (!activity) {
    // No workspace activity this session — skip summary
    process.exit(0);
  }

  const stats = extractStats(activity);
  if (!stats || stats.total === 0) {
    process.exit(0);
  }

  // Generate session summary
  const date = now.slice(0, 10);
  const shortId = randomBytes(3).toString("hex");
  const path = `sessions/${date}-${shortId}.md`;

  const parts = [];
  if (stats.change > 0) parts.push(`${stats.change} changes`);
  if (stats.command > 0) parts.push(`${stats.command} commands`);
  if (stats.discovery > 0) parts.push(`${stats.discovery} discoveries`);
  const statLine = parts.join(", ");

  // Extract the last few activity entries for context
  const recentLines = activity
    .split("\n")
    .filter((l) => /^- \d{2}:\d{2}/.test(l))
    .slice(-10)
    .join("\n");

  const content = [
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

  writeFile(path, content);
  process.exit(0);
}

main();
