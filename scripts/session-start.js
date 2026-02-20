#!/usr/bin/env node

/**
 * session-start.js — SessionStart hook.
 *
 * Displays a workspace context summary at the start of each session.
 * Supports cloud mode (MCP endpoint via fetch) and local mode (CLI).
 *
 * Output is capped at ~400 tokens to stay lightweight.
 */

import {
  isCloudMode,
  workspaceList,
  workspaceRead,
  kvGet,
  kvSet,
  cliRun,
} from "./helpers.js";

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
  const folders = new Map();

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
      lines.push(
        `${prefix}${entry.name}${metaStr}     [${versionStr}${timeDisplay}]`
      );
      shown++;
    }
  }

  const remaining = files.length - shown;
  if (remaining > 0) {
    lines.push(`  +${remaining} more files`);
  }

  return lines.join("\n");
}

function countActivityEntries(content) {
  if (!content) return 0;
  return (content.match(/^- \d{2}:\d{2}/gm) || []).length;
}

function parseFileList(json) {
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}

// ── Cloud mode ──────────────────────────────────────────────

async function cloudMain() {
  const output = [];

  try {
    const listing = await workspaceList("/", true);

    if (!listing || (typeof listing === "string" && listing.includes("(0 files)"))) {
      output.push("[sayou] workspace (cloud)");
      output.push("");
      output.push("Your workspace is empty. Start building knowledge:");
      output.push('  "save a note about [topic]" — creates a versioned file');
      output.push("  /save — quick-save key decisions from this session");
      output.push("  /recall — search past knowledge");
    } else {
      // Get last active time
      let lastActiveStr = "";
      try {
        const lastActive = await kvGet("plugin.last_active");
        if (lastActive) {
          // Parse JSON-encoded string or raw value
          let val = lastActive;
          try { val = JSON.parse(lastActive); } catch {}
          if (typeof val === "string") {
            lastActiveStr = `, last active ${relativeTime(val)}`;
          }
        }
      } catch {}

      output.push(`[sayou] workspace (cloud${lastActiveStr})`);
      output.push("");
      output.push(typeof listing === "string" ? listing : JSON.stringify(listing));

      // Activity summary
      const today = new Date().toISOString().slice(0, 10);
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const parts = [];

      try {
        const todayLog = await workspaceRead(`activity/${today}.md`);
        const todayCount = countActivityEntries(todayLog);
        if (todayCount > 0) parts.push(`${todayCount} today`);
      } catch {}

      try {
        const yesterdayLog = await workspaceRead(`activity/${yesterday}.md`);
        const yesterdayCount = countActivityEntries(yesterdayLog);
        if (yesterdayCount > 0) parts.push(`${yesterdayCount} yesterday`);
      } catch {}

      if (parts.length > 0) {
        output.push("");
        output.push(`  recent activity: ${parts.join(", ")}`);
      }
    }
  } catch (e) {
    output.push(`[sayou] workspace (cloud — error: ${e.message})`);
  }

  // Update last active
  try {
    await kvSet("plugin.last_active", `"${new Date().toISOString()}"`);
  } catch {}

  process.stdout.write(output.join("\n") + "\n");
}

// ── Local mode ──────────────────────────────────────────────

function localMain() {
  const rawList = cliRun("sayou file list / --recursive --json");
  const data = rawList ? parseFileList(rawList) : null;

  let files = [];
  if (Array.isArray(data)) {
    files = data;
  } else if (data && Array.isArray(data.files)) {
    files = data.files;
  } else if (data && Array.isArray(data.items)) {
    files = data.items;
  }

  const displayFiles = files.filter(
    (f) => !f.path.startsWith("activity/") && !f.path.startsWith("sessions/")
  );

  const output = [];

  if (displayFiles.length === 0) {
    output.push("[sayou] workspace");
    output.push("");
    output.push("Your workspace is empty. Start building knowledge:");
    output.push('  "save a note about [topic]" — creates a versioned file');
    output.push("  /save — quick-save key decisions from this session");
    output.push("  /recall — search past knowledge");
    output.push("");
    output.push("docs: github.com/pixell-global/sayou");
  } else {
    let lastActiveStr = "";
    const lastActiveRaw = cliRun('sayou kv get "plugin.last_active"');
    if (lastActiveRaw) {
      try {
        let val = JSON.parse(lastActiveRaw);
        if (typeof val === "object" && val.value) val = typeof val.value === "string" ? val.value : JSON.parse(val.value);
        if (typeof val === "string") lastActiveStr = `, last active ${relativeTime(val)}`;
      } catch {
        const cleaned = lastActiveRaw.replace(/"/g, "");
        if (cleaned) lastActiveStr = `, last active ${relativeTime(cleaned)}`;
      }
    }

    output.push(`[sayou] workspace (${files.length} files${lastActiveStr})`);
    output.push("");
    output.push(formatTree(displayFiles));

    // Activity summary
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const parts = [];

    const todayLog = cliRun(`sayou file read "activity/${today}.md" --json`);
    if (todayLog) {
      try {
        const parsed = JSON.parse(todayLog);
        const content = parsed.content || todayLog;
        const count = countActivityEntries(content);
        if (count > 0) parts.push(`${count} today`);
      } catch {
        const count = countActivityEntries(todayLog);
        if (count > 0) parts.push(`${count} today`);
      }
    }

    const yesterdayLog = cliRun(`sayou file read "activity/${yesterday}.md" --json`);
    if (yesterdayLog) {
      try {
        const parsed = JSON.parse(yesterdayLog);
        const content = parsed.content || yesterdayLog;
        const count = countActivityEntries(content);
        if (count > 0) parts.push(`${count} yesterday`);
      } catch {
        const count = countActivityEntries(yesterdayLog);
        if (count > 0) parts.push(`${count} yesterday`);
      }
    }

    if (parts.length > 0) {
      output.push("");
      output.push(`  recent activity: ${parts.join(", ")}`);
    }
  }

  // Update last active
  try {
    const now = new Date().toISOString();
    cliRun(`sayou kv set "plugin.last_active" '"${now}"'`);
  } catch {}

  process.stdout.write(output.join("\n") + "\n");
}

// ── Entry point ─────────────────────────────────────────────

async function main() {
  if (isCloudMode()) {
    await cloudMain();
  } else {
    localMain();
  }
}

main();
