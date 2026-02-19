#!/usr/bin/env node

/**
 * auto-capture.js — PostToolUse hook for passive activity capture.
 *
 * Receives tool use data via stdin (JSON with tool_name, tool_input,
 * tool_output). Captures significant work into daily activity log files
 * in the workspace at activity/YYYY-MM-DD.md.
 *
 * Capture strategy:
 *   Write/Edit  → file path + purpose (change)
 *   Bash        → git commits, test results, deployments (command)
 *   Read        → config/architecture files only (discovery)
 *   WebFetch    → URL + key findings (discovery)
 *   WebSearch   → query + findings (discovery)
 *   Task        → subagent results (discovery)
 *   Glob/Grep   → skip (low-value exploration)
 *   AskUser     → skip (UX interaction)
 *
 * Always exits 0. Never blocks tool execution.
 */

import { execSync, spawnSync } from "node:child_process";
import { openSync, readSync, closeSync } from "node:fs";

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
  /^\s*sayou\b/,  // skip our own CLI calls to avoid recursion
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
      const path = toolInput?.file_path || toolInput?.notebook_path || "unknown";
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

      // Skip low-value commands
      for (const pat of SKIP_BASH_PATTERNS) {
        if (pat.test(cmd)) return null;
      }

      // Git commits are high-value
      if (/git commit/.test(cmd)) {
        const msgMatch = cmd.match(/-m\s+["']([^"']+)["']/);
        const msg = msgMatch ? msgMatch[1] : "commit";
        return { type: "command", summary: `git commit: "${msg}"` };
      }

      // Git push
      if (/git push/.test(cmd)) {
        return { type: "command", summary: `git push` };
      }

      // Test runs
      if (/pytest|npm test|jest|vitest|cargo test/.test(cmd)) {
        const passed = toolOutput && /passed|PASS/.test(toolOutput);
        const failed = toolOutput && /failed|FAIL|ERROR/.test(toolOutput);
        const status = failed ? "failed" : passed ? "passed" : "ran";
        return { type: "command", summary: `tests ${status}` };
      }

      // Deployments
      if (/deploy|docker build|npm run build/.test(cmd)) {
        return { type: "command", summary: truncate(cmd, 80) };
      }

      // Install commands
      if (/pip install|npm install|brew install/.test(cmd)) {
        return { type: "command", summary: truncate(cmd, 80) };
      }

      // Generic meaningful bash (skip if too short/simple)
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
      return { type: "discovery", summary: `searched "${truncate(query, 60)}"` };
    }

    case "Task": {
      const desc = toolInput?.description || "subagent task";
      return { type: "discovery", summary: truncate(desc, 80) };
    }

    default: {
      // MCP workspace tools — skip to avoid recursion with our own workspace
      if (toolName?.startsWith("mcp__sayou__")) return null;
      // Unknown tool — capture if it has output
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

function writeActivityEntry(entry) {
  const now = new Date();
  const date = now.toISOString().slice(0, 10);
  const time = now.toTimeString().slice(0, 5);
  const path = `activity/${date}.md`;

  const line = `- ${time} — [${entry.type}] ${entry.summary}`;

  // Try to read existing file
  let existing = null;
  try {
    existing = execSync(`sayou file read "${path}"`, {
      stdio: "pipe",
      timeout: 5000,
      encoding: "utf-8",
    }).trim();
  } catch {
    // File doesn't exist yet
  }

  const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const dateDisplay = `${monthNames[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;

  let content;
  if (existing && !existing.includes("not found") && !existing.includes("does not exist")) {
    // Append to existing — update entry count in frontmatter
    const lines = existing.split("\n");
    // Count existing entries
    const entryCount = lines.filter((l) => /^- \d{2}:\d{2}/.test(l)).length + 1;

    // Update entries count in frontmatter
    const updated = existing.replace(/entries: \d+/, `entries: ${entryCount}`);
    content = updated + "\n" + line;
  } else {
    // Create new file
    content = [
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

  try {
    // Use spawnSync with stdin for content to handle special characters
    spawnSync("sayou", ["file", "write", path, "-"], {
      input: content,
      stdio: ["pipe", "pipe", "pipe"],
      timeout: 5000,
    });
  } catch {
    // Silent failure — never block tool execution
  }
}

function main() {
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
      writeActivityEntry(entry);
    }
  } catch {
    // Never fail, never block
  }

  process.exit(0);
}

main();
