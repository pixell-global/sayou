#!/usr/bin/env node

/**
 * auto-capture.js — PostToolUse hook for passive activity capture.
 *
 * Receives tool use data via stdin (JSON with tool_name, tool_input,
 * tool_output). Captures significant work into daily activity log files
 * in the workspace at activity/YYYY-MM-DD.md.
 *
 * Supports cloud mode (MCP endpoint via fetch) and local mode (CLI).
 *
 * Always exits 0. Never blocks tool execution.
 */

import { openSync, readSync, closeSync } from "node:fs";
import {
  isCloudMode,
  workspaceRead,
  workspaceWrite,
  cliRun,
  cliWrite,
} from "./helpers.js";

// Tools to skip entirely
const SKIP_TOOLS = new Set([
  "Glob",
  "Grep",
  "AskUserQuestion",
  "EnterPlanMode",
  "ExitPlanMode",
  "TaskCreate",
  "TaskUpdate",
  "TaskList",
  "TaskGet",
  "ListMcpResourcesTool",
  "ReadMcpResourceTool",
]);

// Bash commands to skip (low-value)
const SKIP_BASH_PATTERNS = [
  /^\s*ls\b/,
  /^\s*cat\b/,
  /^\s*which\b/,
  /^\s*echo\b/,
  /^\s*cd\b/,
  /^\s*pwd\b/,
  /^\s*head\b/,
  /^\s*tail\b/,
  /^\s*wc\b/,
  /^\s*sayou\b/, // skip our own CLI calls to avoid recursion
];

// Read paths worth capturing (config, architecture, important docs)
const INTERESTING_READ_PATTERNS = [
  /\.env/i,
  /config/i,
  /architect/i,
  /readme/i,
  /claude\.md/i,
  /package\.json$/i,
  /pyproject\.toml$/i,
  /docker/i,
  /makefile/i,
  /\.ya?ml$/i,
];

function readStdin() {
  try {
    const chunks = [];
    const fd = openSync("/dev/stdin", "r");
    const buf = Buffer.alloc(65536);
    let bytesRead;
    while ((bytesRead = readSync(fd, buf, 0, buf.length)) > 0) {
      chunks.push(buf.slice(0, bytesRead));
    }
    closeSync(fd);
    return Buffer.concat(chunks).toString("utf-8");
  } catch {
    return "";
  }
}

function classify(toolName, toolInput, toolOutput) {
  if (SKIP_TOOLS.has(toolName)) return null;

  switch (toolName) {
    case "Write":
    case "NotebookEdit": {
      const path =
        toolInput?.file_path || toolInput?.notebook_path || "unknown";
      const shortPath = path.replace(/^\/.*\//, "");
      return { type: "change", summary: `\`${shortPath}\` — created/wrote file` };
    }

    case "Edit": {
      const path = toolInput?.file_path || "unknown";
      const shortPath = path.replace(/^\/.*\//, "");
      return { type: "change", summary: `\`${shortPath}\` — edited file` };
    }

    case "Bash": {
      const cmd = (toolInput?.command || "").trim();
      if (!cmd) return null;

      for (const pat of SKIP_BASH_PATTERNS) {
        if (pat.test(cmd)) return null;
      }

      if (/git commit/.test(cmd)) {
        const msgMatch = cmd.match(/-m\s+["']([^"']+)["']/);
        const msg = msgMatch ? msgMatch[1] : "commit";
        return { type: "command", summary: `git commit: "${msg}"` };
      }

      if (/git push/.test(cmd)) {
        return { type: "command", summary: `git push` };
      }

      if (/pytest|npm test|jest|vitest|cargo test/.test(cmd)) {
        const passed = toolOutput && /passed|PASS/.test(toolOutput);
        const failed = toolOutput && /failed|FAIL|ERROR/.test(toolOutput);
        const status = failed ? "failed" : passed ? "passed" : "ran";
        return { type: "command", summary: `tests ${status}` };
      }

      if (/deploy|docker build|npm run build/.test(cmd)) {
        return { type: "command", summary: truncate(cmd, 80) };
      }

      if (/pip install|npm install|brew install/.test(cmd)) {
        return { type: "command", summary: truncate(cmd, 80) };
      }

      if (cmd.length > 10) {
        return { type: "command", summary: truncate(cmd, 80) };
      }

      return null;
    }

    case "Read": {
      const path = toolInput?.file_path || "";
      const interesting = INTERESTING_READ_PATTERNS.some((p) => p.test(path));
      if (!interesting) return null;
      const shortPath = path.replace(/^\/.*\//, "");
      return { type: "discovery", summary: `read \`${shortPath}\`` };
    }

    case "WebFetch": {
      const url = toolInput?.url || "unknown URL";
      const host = url.replace(/^https?:\/\//, "").split("/")[0];
      return { type: "discovery", summary: `fetched ${host}` };
    }

    case "WebSearch": {
      const query = toolInput?.query || "unknown query";
      return {
        type: "discovery",
        summary: `searched "${truncate(query, 60)}"`,
      };
    }

    case "Task": {
      const desc = toolInput?.description || "subagent task";
      return { type: "discovery", summary: truncate(desc, 80) };
    }

    default: {
      // MCP workspace tools — skip to avoid recursion
      if (toolName?.startsWith("mcp__sayou__")) return null;
      if (toolOutput && String(toolOutput).length > 50) {
        return { type: "discovery", summary: `${toolName} tool used` };
      }
      return null;
    }
  }
}

function truncate(str, max) {
  if (str.length <= max) return str;
  return str.slice(0, max - 3) + "...";
}

function buildActivityContent(existing, line, now) {
  const date = now.toISOString().slice(0, 10);
  const monthNames = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const dateDisplay = `${monthNames[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;

  if (
    existing &&
    !existing.includes("not found") &&
    !existing.includes("does not exist") &&
    !existing.includes("File not found") &&
    !existing.includes("No matches")
  ) {
    const lines = existing.split("\n");
    const entryCount =
      lines.filter((l) => /^- \d{2}:\d{2}/.test(l)).length + 1;
    const updated = existing.replace(/entries: \d+/, `entries: ${entryCount}`);
    return updated + "\n" + line;
  }

  return [
    "---",
    "type: activity-log",
    `date: ${date}`,
    "entries: 1",
    "---",
    `# Activity — ${dateDisplay}`,
    "",
    line,
  ].join("\n");
}

// ── Cloud mode ──────────────────────────────────────────────

async function cloudWriteActivity(entry) {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  const time = now.toTimeString().slice(0, 5);
  const path = `activity/${date}.md`;
  const line = `- ${time} — [${entry.type}] ${entry.summary}`;

  let existing = null;
  try {
    existing = await workspaceRead(path);
  } catch {
    // file doesn't exist yet
  }

  const content = buildActivityContent(existing, line, now);
  await workspaceWrite(path, content);
}

// ── Local mode ──────────────────────────────────────────────

function localWriteActivity(entry) {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  const time = now.toTimeString().slice(0, 5);
  const path = `activity/${date}.md`;
  const line = `- ${time} — [${entry.type}] ${entry.summary}`;

  const existing = cliRun(`sayou file read "${path}"`);
  const content = buildActivityContent(existing, line, now);
  cliWrite(path, content);
}

// ── Entry point ─────────────────────────────────────────────

async function main() {
  try {
    const raw = readStdin();
    if (!raw) {
      process.exit(0);
    }

    let data;
    try {
      data = JSON.parse(raw);
    } catch {
      process.exit(0);
    }

    const toolName = data.tool_name || data.toolName || "";
    const toolInput = data.tool_input || data.toolInput || data.input || {};
    const toolOutput = data.tool_output || data.toolOutput || data.output || "";

    const entry = classify(toolName, toolInput, String(toolOutput).slice(0, 500));

    if (entry) {
      if (isCloudMode()) {
        await cloudWriteActivity(entry);
      } else {
        localWriteActivity(entry);
      }
    }
  } catch {
    // Never fail, never block
  }

  process.exit(0);
}

main();
