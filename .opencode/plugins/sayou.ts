import { type Plugin } from "@opencode-ai/plugin"

export const SayouPlugin: Plugin = async ({ client }) => {
  let workspaceContext: string | null = null

  return {
    event: async (input) => {
      // Load workspace context on session start
      if (input.type === "session.created") {
        try {
          const result = await client.tool.call("workspace_context", {})
          workspaceContext = result?.content || null
        } catch {
          workspaceContext = null
        }
      }

      // Capture activity on tool use
      if (input.type === "tool.execute.after") {
        const { tool: toolName, input: toolInput } = input.properties
        const SKIP = new Set(["glob", "grep", "read", "list", "question"])
        if (SKIP.has(toolName)) return

        const now = new Date()
        const date = now.toISOString().slice(0, 10)
        const time = now.toTimeString().slice(0, 5)
        const summary = `${toolName}: ${JSON.stringify(toolInput).slice(0, 80)}`

        try {
          let existing = ""
          try {
            const r = await client.tool.call("workspace_read", { path: `activity/${date}.md` })
            existing = r?.content || ""
          } catch {
            // File doesn't exist yet
          }

          const line = `- ${time} — ${summary}`
          const content = existing
            ? existing + "\n" + line
            : `---\ntype: activity-log\ndate: ${date}\n---\n# Activity — ${date}\n\n${line}`

          await client.tool.call("workspace_write", {
            path: `activity/${date}.md`,
            content,
          })
        } catch {
          // Never block the agent
        }
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
            "silently save them using workspace_write to preferences/ with frontmatter type: preference."
        )
      }
    },
  }
}
