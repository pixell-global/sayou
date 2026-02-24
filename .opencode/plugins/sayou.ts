import { tool } from "@opencode-ai/plugin"
import type { Plugin, PluginContext } from "@opencode-ai/plugin"

// ── Extraction prompt (general-purpose, not coding-specific) ────────

const EXTRACTION_SYSTEM_PROMPT = `You are a preference extraction assistant. Analyze a conversation between a user and an AI agent. Identify any preferences, conventions, rules, or decisions the user expressed that should be remembered across future sessions.

Extract:
- Style preferences ("always use snake_case", "prefer dark mode")
- Workflow conventions ("deploy to staging first", "always write tests")
- Tool preferences ("use pytest not unittest", "prefer ruff over flake8")
- Negative preferences ("never use print() for debugging", "avoid default exports")
- Architectural decisions ("use JWT with refresh tokens", "REST not GraphQL")
- Communication preferences ("be concise", "explain your reasoning")

Do NOT extract:
- Transient instructions ("fix this bug", "refactor that function")
- Questions the user asked
- Acknowledgements ("ok", "thanks", "got it")
- Descriptions of what the agent did

For each preference, provide a concise rule statement.
Respond with ONLY a JSON array. Each element: {"rule": "...", "category": "..."}
Categories: code-style, workflow, tooling, architecture, communication, general
If no preferences found, respond with: []`

// ── Helpers ─────────────────────────────────────────────────────────

function normalizeRule(text: string): string {
  let rule = text.trim()
  // Strip common preambles
  rule = rule.replace(/^(?:remember\s*(?:that\s*)?:?\s*)/i, "")
  rule = rule.replace(/^(?:from\s+now\s+on\s*,?\s*)/i, "")
  rule = rule.replace(/^(?:going\s+forward\s*,?\s*)/i, "")
  rule = rule.replace(/^(?:always\s+remember\s*(?:that\s*)?:?\s*)/i, "")
  // Capitalize first letter
  rule = rule.charAt(0).toUpperCase() + rule.slice(1)
  // Ensure trailing punctuation
  if (!/[.!]$/.test(rule)) rule += "."
  return rule
}

function isDuplicate(existing: string[], newRule: string): boolean {
  const normalized = newRule.toLowerCase().replace(/[.\s]+$/, "")
  return existing.some((r) => {
    const existingNorm = r.toLowerCase().replace(/[.\s]+$/, "")
    return existingNorm === normalized || existingNorm.includes(normalized) || normalized.includes(existingNorm)
  })
}

function extractTextFromResult(result: unknown): string | undefined {
  if (!result || typeof result !== "object") return undefined
  const r = result as Record<string, unknown>
  if (typeof r["text"] === "string") return r["text"]
  if (Array.isArray(r["parts"])) {
    for (const part of r["parts"]) {
      if (typeof part === "string") return part
      if (typeof part === "object" && part && typeof (part as any).text === "string") return (part as any).text
    }
  }
  if (typeof r["message"] === "object" && r["message"]) return extractTextFromResult(r["message"])
  if (Array.isArray(r["content"])) {
    for (const part of r["content"]) {
      if (typeof part === "string") return part
      if (typeof part === "object" && part && typeof (part as any).text === "string") return (part as any).text
    }
  }
  return undefined
}

function parseExtractionResponse(response: string): Array<{ rule: string; category: string }> {
  // Extract JSON from response (may be wrapped in ```json fences)
  const fenceMatch = response.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/)
  const jsonStr = fenceMatch ? fenceMatch[1]!.trim() : response.trim()

  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (item: any) => typeof item === "object" && item && typeof item.rule === "string" && item.rule.trim().length > 0,
    ).map((item: any) => ({
      rule: item.rule.trim(),
      category: typeof item.category === "string" ? item.category : "general",
    }))
  } catch {
    return []
  }
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)
}

// ── Plugin ──────────────────────────────────────────────────────────

export const SayouPlugin: Plugin = async (ctx) => {
  let workspaceContext: string | null = null
  const userMessages: string[] = []
  let lastExtractedCount = 0
  let existingPreferenceRules: string[] = []

  // Load workspace context and cache existing preference rules
  async function loadContext(): Promise<void> {
    try {
      const result = await ctx.client.tool.call("workspace_context", {})
      workspaceContext = result?.content || null

      // Cache existing rules for deduplication
      existingPreferenceRules = []
      if (workspaceContext) {
        // Extract rule lines from preferences section
        const prefMatch = workspaceContext.match(/\*\*Preferences:\*\*[\s\S]*?(?=\*\*|$)/)
        if (prefMatch) {
          const lines = prefMatch[0].split("\n")
          for (const line of lines) {
            const trimmed = line.trim()
            if (trimmed && !trimmed.startsWith("**") && !trimmed.startsWith("- preferences/")) {
              existingPreferenceRules.push(trimmed)
            }
          }
        }
      }
    } catch {
      workspaceContext = null
    }
  }

  // Save a preference with deduplication and toast
  async function savePreference(rule: string, category: string): Promise<boolean> {
    const normalized = normalizeRule(rule)
    if (isDuplicate(existingPreferenceRules, normalized)) return false

    const slug = slugify(rule)
    const content =
      `---\ntype: preference\ncategory: ${category}\n---\n${normalized}\n`

    try {
      await ctx.client.tool.call("workspace_write", {
        path: `preferences/${slug}.md`,
        content,
      })
      existingPreferenceRules.push(normalized)
      return true
    } catch {
      return false
    }
  }

  // Auto-extract preferences from conversation on idle
  async function extractFromConversation(): Promise<void> {
    if (userMessages.length === 0 || userMessages.length === lastExtractedCount) return

    const messagesToAnalyze = userMessages.slice(lastExtractedCount)
    lastExtractedCount = userMessages.length

    let session: { id: string } | undefined
    try {
      session = await ctx.client.session.create({
        body: { title: "[sayou] preference extraction" },
      })

      const prompt =
        (existingPreferenceRules.length > 0
          ? "## Already saved preferences (do NOT re-extract these)\n" +
            existingPreferenceRules.map((r) => `- ${r}`).join("\n") + "\n\n"
          : "") +
        "## User messages from this session\n" +
        messagesToAnalyze.map((msg, i) => `[${i + 1}] ${msg}`).join("\n") +
        "\n\nAnalyze the messages above. Extract any new preferences. Respond with ONLY a JSON array."

      const result = await ctx.client.session.prompt({
        path: { id: session.id },
        body: {
          parts: [{ type: "text", text: EXTRACTION_SYSTEM_PROMPT + "\n\n" + prompt }],
        },
      })

      const responseText = extractTextFromResult(result)
      if (!responseText) return

      const extracted = parseExtractionResponse(responseText)
      if (extracted.length === 0) return

      let savedCount = 0
      for (const { rule, category } of extracted) {
        const saved = await savePreference(rule, category)
        if (saved) savedCount++
      }

      if (savedCount > 0) {
        const plural = savedCount > 1 ? "s" : ""
        await ctx.client.tui
          .showToast({
            body: {
              message: `${savedCount} preference${plural} saved to workspace`,
              variant: "success",
            },
          })
          .catch(() => {})

        // Refresh context so compaction injection has latest
        await loadContext()
      }
    } catch {
      // Never block
    } finally {
      if (session) {
        await ctx.client.session.delete({ path: { id: session.id } }).catch(() => {})
      }
    }
  }

  return {
    event: async ({ event }) => {
      // Load workspace context on session start
      if (event.type === "session.created") {
        await loadContext()
      }

      // Collect user messages for auto-extraction
      if (
        event.type === "message.updated" &&
        event.properties &&
        (event.properties as Record<string, unknown>)["role"] === "user" &&
        typeof (event.properties as Record<string, unknown>)["text"] === "string"
      ) {
        userMessages.push((event.properties as Record<string, unknown>)["text"] as string)
      }

      // Auto-extract preferences when session goes idle
      if (event.type === "session.idle") {
        await extractFromConversation()
      }
    },

    // Capture activity on tool use
    "tool.execute.after": async (input, _output) => {
      const toolName = input.tool
      const SKIP = new Set(["glob", "grep", "read", "list", "question", "workspace_context", "workspace_read"])
      if (SKIP.has(toolName)) return

      // Show toast when agent saves a preference via workspace_write
      if (toolName === "workspace_write" && input.args) {
        const path = (input.args as Record<string, unknown>)["path"]
        if (typeof path === "string" && path.startsWith("preferences/")) {
          await ctx.client.tui
            .showToast({
              body: { message: `Preference saved: ${path}`, variant: "success" },
            })
            .catch(() => {})
          // Refresh context so compaction has latest
          await loadContext()
          return
        }
      }

      // Activity capture for non-read tools
      const now = new Date()
      const date = now.toISOString().slice(0, 10)
      const time = now.toTimeString().slice(0, 5)
      const summary = `${toolName}: ${JSON.stringify(input.args || {}).slice(0, 80)}`

      try {
        let existing = ""
        try {
          const r = await ctx.client.tool.call("workspace_read", { path: `activity/${date}.md` })
          existing = r?.content || ""
        } catch {
          // File doesn't exist yet
        }

        const line = `- ${time} — ${summary}`
        const content = existing
          ? existing + "\n" + line
          : `---\ntype: activity-log\ndate: ${date}\n---\n# Activity — ${date}\n\n${line}`

        await ctx.client.tool.call("workspace_write", { path: `activity/${date}.md`, content })
      } catch {
        // Never block
      }
    },

    // Inject preferences into system prompt
    "experimental.chat.system.transform": async (_input, output) => {
      if (workspaceContext) {
        output.system.push(
          "## Workspace Context (from sayou)\n\n" +
            workspaceContext +
            "\n\n" +
            "Follow all preferences listed above. " +
            "When the user expresses new preferences about coding style, conventions, or workflow, " +
            "silently save them using workspace_write to preferences/ with frontmatter type: preference.",
        )
      }
    },

    // Re-inject preferences on context window compaction so they survive long sessions
    "experimental.session.compacting": async (_input, output) => {
      // Refresh to get latest (user may have added preferences mid-session)
      await loadContext()
      if (workspaceContext) {
        output.context.push(
          "## Workspace Context (from sayou)\n\n" +
            workspaceContext +
            "\n\nFollow all preferences listed above.",
        )
      }
    },

    // Custom tools: /remember and /context
    tool: {
      remember: tool({
        description:
          "Save a preference or rule to persistent workspace memory. " +
          "Use when the user explicitly asks to remember something with /remember. " +
          "The preference will be loaded automatically in future sessions.",
        args: {
          rule: tool.schema.string().describe("The preference or rule to remember"),
          category: tool.schema
            .string()
            .describe("Category: code-style, workflow, tooling, architecture, communication, or general")
            .optional(),
        },
        async execute(args) {
          const rule = args.rule?.trim()
          if (!rule) return "No rule provided. Usage: /remember <rule>"

          const category = args.category || "general"
          const saved = await savePreference(rule, category)

          if (saved) {
            return `Preference saved to workspace:\n> ${normalizeRule(rule)}`
          } else {
            return `This preference already exists in your workspace.`
          }
        },
      }),

      context: tool({
        description: "View all saved preferences and workspace context.",
        args: {},
        async execute() {
          await loadContext()
          if (!workspaceContext) {
            return "No preferences saved yet. Express preferences naturally — they'll be saved automatically. Or use /remember to save one explicitly."
          }
          return workspaceContext
        },
      }),
    },
  }
}
