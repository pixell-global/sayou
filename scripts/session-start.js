#!/usr/bin/env node

/**
 * session-start.js — SessionStart hook.
 *
 * Displays a workspace context summary at the start of each session.
 * Shows a file tree with frontmatter metadata and version counts,
 * plus a delta of changes since the last session.
 *
 * Output is capped at ~400 tokens to stay lightweight.
 */

import { execSync } from "node:child_process";

function run(cmd) {
  try {
    return execSync(cmd, { stdio: "pipe", timeout: 10000, encoding: "utf-8" }).trim();
  } catch {
    return null;
  }
}

function parseFileList(json) {
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

function relativeTime(dateStr) {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (isNaN(then)) return "";
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks}w ago`;
}

function formatTree(files) {
  const MAX_FILES = 20;
  const lines = [];
  const folders = new Map(); // folder -> [{name, meta, versions, updated}]

  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    const name = parts.pop();
    const folder = parts.length > 0 ? parts.join("/") + "/" : "";

    if (!folders.has(folder)) {
      folders.set(folder, []);
    }
    folders.get(folder).push({
      name,
      meta: f.frontmatter || {},
      versions: f.versions || f.version || 1,
      updated: f.updated_at || f.created_at || "",
    });
  }

  let shown = 0;
  const sortedFolders = [...folders.keys()].sort();

  for (const folder of sortedFolders) {
    if (shown >= MAX_FILES) break;

    if (folder) {
      lines.push(`  ${folder}`);
    }

    const entries = folders.get(folder);
    for (const entry of entries) {
      if (shown >= MAX_FILES) break;

      const metaParts = [];

      // Show key frontmatter fields inline
      for (const key of ["status", "type", "topic", "priority"]) {
        if (entry.meta[key]) {
          metaParts.push(`${key}=${entry.meta[key]}`);
        }
      }

      const metaStr = metaParts.length > 0 ? `  ${metaParts.join(", ")}` : "";
      const versionStr = `v${entry.versions}`;
      const timeStr = relativeTime(entry.updated);
      const timeDisplay = timeStr ? `, ${timeStr}` : "";

      const prefix = folder ? "    " : "  ";
      lines.push(`${prefix}${entry.name}${metaStr}     [${versionStr}${timeDisplay}]`);
      shown++;
    }
  }

  const remaining = files.length - shown;
  if (remaining > 0) {
    lines.push(`  +${remaining} more files`);
  }

  return lines.join("\n");
}

function getActivitySummary() {
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

  let todayCount = 0;
  let yesterdayCount = 0;

  const todayLog = run(`sayou file read "activity/${today}.md" --json`);
  if (todayLog) {
    try {
      const parsed = JSON.parse(todayLog);
      const content = parsed.content || todayLog;
      todayCount = (content.match(/^- \d/gm) || []).length;
    } catch {
      // count lines starting with "- " and a timestamp
      todayCount = (todayLog.match(/^- \d/gm) || []).length;
    }
  }

  const yesterdayLog = run(`sayou file read "activity/${yesterday}.md" --json`);
  if (yesterdayLog) {
    try {
      const parsed = JSON.parse(yesterdayLog);
      const content = parsed.content || yesterdayLog;
      yesterdayCount = (content.match(/^- \d/gm) || []).length;
    } catch {
      yesterdayCount = (yesterdayLog.match(/^- \d/gm) || []).length;
    }
  }

  if (todayCount === 0 && yesterdayCount === 0) return "";

  const parts = [];
  if (todayCount > 0) parts.push(`${todayCount} today`);
  if (yesterdayCount > 0) parts.push(`${yesterdayCount} yesterday`);
  return `recent activity: ${parts.join(", ")}`;
}

function getLastActive() {
  const raw = run('sayou kv get "plugin.last_active"');
  if (!raw) return null;
  try {
    // KV returns JSON-encoded string
    const val = JSON.parse(raw);
    if (typeof val === "string") return val;
    if (val && val.value) return typeof val.value === "string" ? val.value : JSON.parse(val.value);
  } catch {
    return raw.replace(/"/g, "");
  }
  return null;
}

function main() {
  // Get file listing
  const rawList = run("sayou file list / --recursive --json");
  const data = rawList ? parseFileList(rawList) : null;

  // Determine files array from response
  let files = [];
  if (Array.isArray(data)) {
    files = data;
  } else if (data && Array.isArray(data.files)) {
    files = data.files;
  } else if (data && Array.isArray(data.items)) {
    files = data.items;
  }

  // Filter out activity logs and session files from the tree display
  const displayFiles = files.filter(
    (f) => !f.path.startsWith("activity/") && !f.path.startsWith("sessions/")
  );

  const output = [];

  if (displayFiles.length === 0) {
    // Empty workspace
    output.push("[sayou] workspace");
    output.push("");
    output.push("Your workspace is empty. Start building knowledge:");
    output.push('  "save a note about [topic]" — creates a versioned file');
    output.push("  /save — quick-save key decisions from this session");
    output.push("  /recall — search past knowledge");
    output.push("");
    output.push("docs: github.com/pixell-global/sayou");
  } else {
    // Populated workspace
    const lastActive = getLastActive();
    const lastActiveStr = lastActive ? `, last active ${relativeTime(lastActive)}` : "";
    const activityStr = getActivitySummary();

    output.push(`[sayou] workspace (${files.length} files${lastActiveStr})`);
    output.push("");
    output.push(formatTree(displayFiles));

    if (activityStr) {
      output.push("");
      output.push(`  ${activityStr}`);
    }
  }

  // Update last active timestamp
  try {
    const now = new Date().toISOString();
    run(`sayou kv set "plugin.last_active" '"${now}"'`);
  } catch {
    // non-fatal
  }

  process.stdout.write(output.join("\n") + "\n");
}

main();
