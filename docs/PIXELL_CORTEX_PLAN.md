# Pixell Cortex — Project Plan

**Internal codename:** Pixell Cortex
**User-facing product:** Pixell Agents
**Date:** 2026-05-02

Pixell Cortex is the company brain for K-beauty brands. It combines Hermes Agent (reasoning, Slack interface, scheduling, skills) with Sayou (knowledge storage, search, versioning) to capture tribal knowledge and make operational decisions.

---

## 0. No MCP

**Pixell Cortex does not use MCP. Ever.**

MCP tool schemas are injected into every LLM API call, consuming tokens on every turn even when the tools aren't used. For Cortex, this overhead is pure waste. Hermes already has a terminal toolset. Skills teach the agent which CLI commands and scripts to run. This gives the same capabilities as MCP at a fraction of the token cost.

All integrations (Sayou, Amazon APIs, Slack cards, data fetchers) are accessed via **CLI commands and Python scripts** that Hermes executes through its built-in terminal tools. Skills define the procedures. The terminal is the universal interface.

---

## 1. Architecture

```
Per-customer Vultr VPS ($6-12/mo, 2GB RAM, 1 vCPU)
┌──────────────────────────────────────────────────────┐
│                                                      │
│  docker-compose.yml                                  │
│  ┌────────────────────────────────────────────────┐  │
│  │  hermes-gateway (nousresearch/hermes-agent)    │  │
│  │  ├── Slack Socket Mode (brand's Slack)         │  │
│  │  ├── Agent loop (Claude / GPT / OpenRouter)    │  │
│  │  ├── SOUL.md (Pixell Agents personality)       │  │
│  │  ├── MEMORY.md (agent-level state, ~800 tok)   │  │
│  │  ├── Skills (brand-ops, domains, reporting)    │  │
│  │  ├── Cron (monitoring jobs, daily briefings)   │  │
│  │  └── Terminal toolset ─── runs CLI/scripts     │  │
│  └──────────────┬─────────────────────────────────┘  │
│                 │ shell commands                      │
│  ┌──────────────┴─────────────────────────────────┐  │
│  │  /opt/cortex/                                  │  │
│  │  ├── bin/                                      │  │
│  │  │   ├── brain          # Sayou CLI wrapper    │  │
│  │  │   ├── fetch-data     # Amazon/TikTok data   │  │
│  │  │   ├── exec-action    # Execute API actions   │  │
│  │  │   └── post-card      # Slack Block Kit cards │  │
│  │  ├── lib/               # Shared Python code    │  │
│  │  └── config/            # API credentials       │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Sayou (SQLite + local storage)                │  │
│  │  ├── ~/.sayou/sayou.db   (metadata, FTS, etc.) │  │
│  │  └── ~/.sayou/storage/   (file content)        │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Ingestion (cron or webhook)                   │  │
│  │  - Slack history → Sayou                       │  │
│  │  - Contract uploads → Sayou                    │  │
│  │  - GDrive/Notion sync → Sayou                  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  hermes-dashboard (port 9119)                  │  │
│  │  (internal monitoring only)                    │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Design Principles

- **No Hermes fork.** All customization via skills, CLI scripts, config.
- **No MCP.** Skills + terminal toolset. CLI commands, not tool schemas.
- **Sayou stays simple.** Versioned file store + search. No decision logic.
- **One instance per customer.** Hermes is single-tenant by design. Skills accumulate per-brand.
- **Slack is the interface.** No web dashboard for customers. No mobile app.
- **Skills are the product.** The brand-specific skill library is the moat.

---

## 2. Three Modes of Work

The brain operates in three distinct modes. Each has its own trigger, Slack surface, and value. The brain is not a copilot (always suggesting) or an alarm (only fires when something is wrong). It's an operations partner that's always working.

### Mode 1: Scheduled Monitoring (brain pushes)

**Trigger:** Cron jobs on a fixed schedule (6x/day on weekdays, daily briefings, weekly reviews).

**Slack surface:** Posts to `#brain` channel. Never interrupts other channels.

**What it does:** The brain checks operational state against the rule library and surfaces whatever needs attention — decisions, opportunities, status confirmations, and blocks.

**Examples across the full spectrum:**

| Type | Example |
|---|---|
| **Decision needed** | "BHA Spot Patch velocity up 40% this week. Current inventory covers 12 days at this rate. Restock decision needed by Friday." |
| **Opportunity** | "Creator @skincarejane posted yesterday, 847K views. Her contract allows one more repost. Recommend reposting today while momentum is hot." |
| **Block** | "Don't increase Serum ad budget — OY rebate at $186K/$200K with 11 days left." |
| **Status (no action)** | "OY GMV on track at $186K / $200K trigger. No action needed." |
| **Anomaly** | "BuyBox dropped below 80% on hero SKU. Investigating competing seller." |

The brain is not just catching mistakes. On a typical day, most output is routine operations: tracking metrics, flagging opportunities, confirming things are on track. Mistake-catching is maybe 10-20% of output.

**Output ratio (typical day):**
- 2-3 decisions or opportunities requiring action
- 1-2 status confirmations (things are on track)
- 0-1 urgent blocks (something going wrong)

### Mode 2: Task Execution (user pushes)

**Trigger:** User @mentions the brain in any channel and asks it to do something.

**Slack surface:** Responds in-thread where it was mentioned. May also post results to `#brain` if the task produces a decision or report.

**What it does:** The brain performs analysis, drafts, checks, and operational work on demand. The user gives it a task, it does the work, comes back with results.

**Examples:**

| Task | Brain does |
|---|---|
| "Check if we can run 20% promo on Serum next week" | Checks inventory, margin rules, channel conflicts, active promos, OY calendar. Returns yes/no with reasoning and cited constraints. |
| "Draft a creator brief for Cleansing Powder launch" | Pulls brand voice rules, compliance constraints, past brief templates. Drafts brief with flagged claims. |
| "Pull last 3 months of BuyBox data and tell me what's happening" | Runs `fetch-data buybox`, analyzes trends, identifies patterns, posts summary. |
| "Update the OY rebate threshold — they changed it to $250K" | Updates the rule in Sayou, adjusts confidence to 1.0 (direct from user), logs the change. |
| "Run a full review of TikTok Shop performance this week" | Pulls metrics, compares to previous weeks, checks against budget rules, posts report. |

This mode makes the brain useful every day, not just when it has something to push. The founder treats it like a team member they can delegate to.

### Mode 3: Knowledge Query (user asks)

**Trigger:** User @mentions the brain with a question.

**Slack surface:** Responds in-thread. Short, cited answers.

**What it does:** Answers questions from the rule library, decision history, and ingested sources. Fast, factual, always with citations.

**Examples:**

| Question | Brain answers |
|---|---|
| "What's our margin floor on Spot Patch?" | "$14.50 unit cost, $18.00 minimum price. Source: /rules/thresholds/spot-patch-margin.md" |
| "Who approves ad budgets over $5K?" | "Gahye. Source: /rules/relationships/budget-approval.md (from Slack Feb 12)" |
| "What happened with the Costco deal?" | Summarizes from /sources/contracts/ and /decisions/ with timeline and current status. |
| "Why did we hold ad spend last Tuesday?" | Links to the decision file with full reasoning and outcome. |
| "What rules do we have about Olive Young?" | Lists all active rules with OY in scope, with confidence scores and sources. |

This mode is especially valuable for new team members who need instant access to institutional knowledge without asking the founder.

### Slack Interaction Model

```
┌─────────────────────────────────────────────────────────┐
│  #brain channel                                         │
│  ├── Daily briefing (8am)                               │
│  ├── Decision cards (throughout day, from cron)         │
│  ├── Opportunity cards                                  │
│  ├── Status confirmations                               │
│  ├── Task results (when user-requested work completes)  │
│  └── Weekly review (Monday 9am)                         │
│                                                         │
│  @brain in any channel                                  │
│  ├── Task requests → brain does work, responds in-thread│
│  ├── Questions → brain answers from knowledge base      │
│  └── Feedback → "approve" / "reject: [reason]"          │
│                                                         │
│  DM from brain (rare)                                   │
│  └── Urgent blocks only (time-sensitive, high-impact)   │
└─────────────────────────────────────────────────────────┘
```

**What the brain does NOT do:**
- Does not comment on conversations in other channels
- Does not offer unsolicited suggestions on messages
- Does not pop up with tips or reminders
- Does not summarize threads unless asked
- Does not react to messages with emojis

The brain reads all channels passively for knowledge extraction. It speaks only in `#brain`, in threads where it's @mentioned, or via rare DMs. The absence of noise is part of the product — when the brain speaks, it matters.

### A Founder's Typical Day

**8:00 AM — Morning briefing in `#brain`**
Daily summary: what happened overnight, what needs attention today, any pending decisions. Approve two routine decisions. Read one opportunity card about creator momentum.

**10:30 AM — Task delegation**
Founder @mentions brain: "Check if we can run BOGO on Cleansing Powder next week." Brain checks inventory, margin rules, channel conflicts, active promos, returns a yes/no with reasoning.

**1:00 PM — Decision card appears in `#brain`**
Creator brief for a new campaign draft needs compliance review. Brain flags two claims that violate FDA rules, suggests alternatives. Founder approves the revision.

**3:30 PM — Brain DMs founder**
BuyBox dropped below 80% on hero SKU. Decision card: pause ads until BuyBox recovers, or investigate competing seller. Founder approves the pause.

**4:00 PM — New hire asks a question**
Team member @mentions brain in #general: "How do we handle returns for damaged items?" Brain answers from the rule library with the exact process and two exceptions, citing the Slack thread where the process was decided.

**Ad hoc throughout the day**
Founder asks "@brain what's our TikTok ROAS this week?" Gets a quick answer with trend comparison.

---

## 3. Components

### 2.1 Stock (no custom code)

| Component | Source | Role |
|---|---|---|
| Hermes Agent | `nousresearch/hermes-agent` Docker image | Agent loop, Slack, cron, skills |
| Sayou | `pip install sayou` | Knowledge store, accessed via CLI |
| Hermes Dashboard | Built into Hermes | Internal monitoring |

### 2.2 Custom Skills (~/.hermes/skills/)

Skills are markdown files. No code. They instruct the agent to run CLI commands via the terminal toolset.

```
~/.hermes/skills/
├── brand-ops/
│   ├── extract-rules/SKILL.md         # Artifacts → structured brand rules
│   ├── generate-decision/SKILL.md     # Rules + state → decision recommendation
│   ├── process-feedback/SKILL.md      # Approve/reject → rule updates
│   ├── ingest-artifact/SKILL.md       # New content → structured storage
│   └── resolve-conflict/SKILL.md      # Conflicting rules → resolution
├── domains/
│   ├── ads-allocation/SKILL.md        # Amazon SP/SB/SD, TikTok ad decisions
│   ├── listing-content/SKILL.md       # A+ content, copy, image updates
│   ├── inventory-routing/SKILL.md     # FBA/3PL/PBI3 reroute logic
│   ├── creator-compliance/SKILL.md    # Brief review, FDA claim checking
│   ├── pricing-promo/SKILL.md         # Discount timing, cannibalization
│   ├── compliance-claims/SKILL.md     # Regulatory flags, takedown risk
│   └── channel-mix/SKILL.md           # Amazon vs TikTok vs DTC allocation
└── reporting/
    ├── daily-briefing/SKILL.md        # Morning ops summary
    ├── weekly-review/SKILL.md         # Decision stats, rule delta, metrics
    └── onboarding-scan/SKILL.md       # First-run: scan all history, extract rules
```

### 2.3 CLI Scripts (/opt/cortex/)

Small Python scripts that the agent runs via Hermes's terminal toolset. These are the only custom code in the system.

| Script | Purpose | Estimated Size |
|---|---|---|
| `bin/brain` | Sayou CLI wrapper: `brain read`, `brain write`, `brain search`, `brain list`, `brain grep` | ~200 lines |
| `bin/fetch-data` | Read-only data fetchers: `fetch-data buybox`, `fetch-data ad-metrics`, `fetch-data inventory` | ~400 lines |
| `bin/exec-action` | Execution adapters: `exec-action pause-ads`, `exec-action update-budget`, `exec-action update-listing` | ~500 lines |
| `bin/post-card` | Post Slack Block Kit decision cards with approve/reject buttons | ~200 lines |

### 2.4 Configuration Files

| File | Purpose |
|---|---|
| `~/.hermes/config.yaml` | Model selection, provider keys, enabled toolsets |
| `~/.hermes/SOUL.md` | Pixell Agents personality and behavior |
| `~/.hermes/gateway.json` | Slack platform config, session settings |
| `~/.hermes/cron/jobs.json` | Scheduled monitoring and reporting jobs |
| `docker-compose.yml` | Service orchestration |
| `.env` | API keys (Slack, Amazon, TikTok, LLM provider) |

---

## 4. Sayou Knowledge Schema

Sayou stores everything as versioned markdown files with YAML frontmatter. The agent accesses Sayou via the `brain` CLI wrapper.

### 3.1 CLI Interface

```bash
# Read a file
brain read /rules/constraints/oy-peak-hero-sku.md

# Write a file (content from stdin or --content flag)
brain write /rules/constraints/new-rule.md --content "---\ntype: constraint\n..."

# Search by frontmatter
brain search --filters '{"status": "active", "type": "constraint"}'

# Full-text search
brain search --query "olive young rebate"

# List a directory
brain list /rules/ --recursive

# Grep file contents
brain grep "rebate trigger" --path "**/*.md"
```

### 3.2 Directory Structure (per workspace)

```
/
├── rules/
│   ├── constraints/        # "Don't do X during Y"
│   ├── triggers/           # "If metric > threshold, do Z"
│   ├── thresholds/         # "Rebate at N units"
│   ├── voice/              # "Never say X in claims"
│   └── relationships/      # "Person A approves type B"
├── decisions/
│   ├── 2026-05/            # By month
│   │   ├── hold-serum-ad-spend.md
│   │   └── reroute-bha-patch-pbi3.md
│   └── ...
├── sources/
│   ├── slack/              # Synced Slack messages (via sayou-drive)
│   ├── gdrive/             # Synced Google Drive docs
│   ├── notion/             # Synced Notion pages
│   └── contracts/          # Uploaded contracts, manually ingested
├── reports/
│   ├── daily/
│   └── weekly/
└── config/
    └── brand-profile.md    # Brand identity, channels, team, thresholds
```

### 3.3 Rule File Format

```markdown
---
type: constraint
confidence: 0.92
status: active
domain: ads
source_path: /sources/slack/general/2026-03-14-heejee.md
source_quote: "we can't push A on Amazon during OY peak"
last_confirmed: 2026-03-14
created: 2026-05-02
---
# Don't increase Amazon ad spend on hero SKUs during Olive Young peak window

When Olive Young has an active co-marketing window or is approaching a
quarterly rebate trigger, do not increase Amazon Sponsored Products spend
on SKUs that overlap with the OY assortment. The risk is cannibalizing
the OY relationship for marginal Amazon revenue.

## Applies to
- Soothing Serum 50ml (ASIN: B0XXXXXX)
- Any SKU in the OY exclusive assortment

## Exceptions
- If OY GMV already hit the quarterly rebate trigger, constraint lifts.
```

### 3.4 Decision File Format

```markdown
---
type: decision
domain: ads
status: approved
confidence: high
estimated_impact: 34000
rules_applied:
  - /rules/constraints/oy-peak-hero-sku.md
  - /rules/thresholds/oy-q2-rebate.md
approved_by: gahye
approved_at: 2026-05-02T14:30:00Z
executed: true
---
# Hold Soothing Serum 50ml ad budget — $34K rebate at risk

## Recommendation
Do not increase Amazon Sponsored Products budget from $4,200 to $6,800
for Soothing Serum 50ml. Olive Young Q2 rebate trigger is at $200K Korea
retail GMV; we are at $186K with 11 days remaining.

## Sources
- Olive Young contract amendment (Section 4.2): /sources/contracts/oy-amendment-2025.md
- Slack message from Heejee (Mar 14): /sources/slack/general/2026-03-14-heejee.md
- Current OY GMV: $186K / $200K trigger
- Scheduled Amazon increase: $4,200 → $6,800 (tomorrow 9am)

## Outcome
Ad spend held at $4,200. OY GMV hit $200K trigger on May 8.
Rebate of $34K secured.
```

---

## 5. Hermes Configuration

### 4.1 config.yaml

```yaml
# ~/.hermes/config.yaml
personality: SOUL.md

model: anthropic/claude-sonnet-4-20250514
provider: anthropic

# No mcp_servers. All access via terminal + CLI scripts.

enabled_toolsets:
  - terminal
  - web
```

### 4.2 SOUL.md

```markdown
You are a Pixell Agent — an AI operations partner for a K-beauty brand.

Your job is to make high-stakes operational decisions that the founder
would make if they had perfect memory and unlimited attention. You have
access to the brand's complete knowledge base: Slack history, contracts,
call transcripts, and operational data.

## Tools

You access all systems via CLI commands in the terminal:
- `brain read|write|search|list|grep` — read/write knowledge in Sayou
- `fetch-data buybox|ad-metrics|inventory|reviews` — pull operational data
- `exec-action pause-ads|update-budget|update-listing` — execute decisions
- `post-card` — post a decision card to Slack with approve/reject buttons

Do NOT use MCP tools. Use terminal commands only.

## Core behaviors

1. **Cite everything.** Every recommendation must reference at least two
   internal sources. If you can't cite it, you don't know it.

2. **Block before boost.** If a brand rule says "don't do X," that
   overrides any optimization signal saying "do X." Constraints are
   sacred.

3. **Quantify impact.** Every decision recommendation includes a dollar
   estimate. If you can't estimate, say so and explain why.

4. **Learn from rejections.** When a decision is rejected, extract the
   implicit rule and store it. Never make the same mistake twice.

5. **Stay in your lane.** You recommend. Humans approve. Never execute
   a non-reversible action without explicit approval.

## Decision format

Always format decisions as:

[emoji] **Headline action — dollar impact**

Reasoning: 2-3 sentences.

Sources:
- [type] description (from /path)
- [type] description (from /path)

Confidence: HIGH/MEDIUM/LOW
Reversible: YES/NO

Reply "approve" to execute, or "reject: [reason]" to block.
```

### 4.3 Cron Jobs

```json
[
  {
    "name": "ops-monitor",
    "schedule": "0 9,11,13,15,17,19 * * 1-5",
    "prompt": "Run the generate-decision skill. Check all active brand rules against current operational state. If any decision opportunities exist, post recommendations to Slack.",
    "platform": "slack",
    "enabled_toolsets": ["terminal"]
  },
  {
    "name": "daily-briefing",
    "schedule": "0 8 * * 1-5",
    "prompt": "Run the daily-briefing skill. Summarize yesterday's decisions, rule changes, and key metrics. Post to the #pixell-brain channel.",
    "platform": "slack",
    "enabled_toolsets": ["terminal"]
  },
  {
    "name": "weekly-review",
    "schedule": "0 9 * * 1",
    "prompt": "Run the weekly-review skill. Compile decision stats, rule delta, confidence changes, and missed opportunities. Post to #pixell-brain.",
    "platform": "slack",
    "enabled_toolsets": ["terminal"]
  },
  {
    "name": "ingestion-check",
    "schedule": "0 */4 * * *",
    "prompt": "Check for new unprocessed content in Sayou /sources/. Run extract-rules on any new artifacts. Report new rules found.",
    "platform": "slack",
    "enabled_toolsets": ["terminal"]
  }
]
```

---

## 6. Build Phases

### Phase 1: Foundation (demo-ready)

Goal: One brand (SINSURU), one "eerie moment" card, working Slack interaction.

**Deliverables:**
- [ ] Vultr VPS provisioned with Docker
- [ ] Hermes gateway running with Slack Socket Mode
- [ ] `brain` CLI wrapper installed and working
- [ ] SOUL.md written and loaded
- [ ] 1 month SINSURU Slack history ingested into Sayou
- [ ] 2-3 contracts uploaded to Sayou with structured frontmatter
- [ ] `extract-rules` skill written
- [ ] `generate-decision` skill written
- [ ] `process-feedback` skill written
- [ ] `onboarding-scan` skill written and run (initial rule extraction)
- [ ] At least 1 decision card posted that cites a source the founder forgot
- [ ] Approve/reject flow working via text replies

**Not in Phase 1:** Custom Slack cards, execution adapters, cron jobs, domain-specific skills, data fetchers.

### Phase 2: Decision Engine

Goal: Automated monitoring, multiple decision domains, real execution.

**Deliverables:**
- [ ] `fetch-data` script: Amazon BuyBox, ad metrics, inventory levels
- [ ] `exec-action` script: Amazon Ads API budget changes (real)
- [ ] `post-card` script: Slack Block Kit cards with approve/reject buttons
- [ ] Domain skills: ads-allocation, listing-content, inventory-routing, pricing-promo
- [ ] Cron jobs: ops-monitor (every 2 hours), daily-briefing, ingestion-check
- [ ] Rule extraction running on new Slack messages automatically
- [ ] Decision log in Sayou with full history and outcomes
- [ ] At least 30 decision cards/week generated from real operational state

### Phase 3: Multi-Brand

Goal: Second and third paying customers, repeatable deployment.

**Deliverables:**
- [ ] Deployment script: provision VPS → install Docker → configure Hermes → install Cortex scripts → connect Slack
- [ ] Brand onboarding skill: scan N months of Slack history, extract initial rule set, generate brand profile
- [ ] Domain skills: creator-compliance, compliance-claims, channel-mix
- [ ] `exec-action` expansion: TikTok Shop API, Shopify API
- [ ] Weekly review skill with metrics dashboard (text-based in Slack)
- [ ] Skill versioning: track which skill versions are deployed per customer
- [ ] At least 2 paying customers at $2K+/month

### Phase 4: Scale

Goal: 10+ customers, operational efficiency.

**Deliverables:**
- [ ] Centralized monitoring across all customer instances
- [ ] Automated VPS provisioning (Terraform/Pulumi + Vultr API)
- [ ] Skill distribution: update skills across all instances from a central repo
- [ ] Sayou upgrade path: SQLite → managed MySQL for larger customers
- [ ] Alert system: notify ops team when an instance has errors or low decision acceptance rate
- [ ] Evaluate: continue with Hermes or build own lightweight agent loop

---

## 7. Customer Deployment Checklist

For each new brand:

```
1. PROVISION
   [ ] Vultr VPS (2GB RAM, 1 vCPU, Ubuntu 24.04)
   [ ] Domain/subdomain (internal only)
   [ ] Docker + docker-compose installed

2. CONFIGURE
   [ ] .env file with all API keys
   [ ] SOUL.md customized for brand
   [ ] config.yaml with model/provider settings
   [ ] gateway.json with Slack workspace config
   [ ] /opt/cortex/ scripts installed and on PATH
   [ ] Brand profile written to Sayou /config/brand-profile.md

3. CONNECT
   [ ] Slack app installed to brand's workspace
   [ ] Hermes gateway connected via Socket Mode
   [ ] `brain list /` returns expected directory structure
   [ ] Test message sent and received

4. INGEST
   [ ] Slack history (1-3 months) synced to Sayou /sources/slack/
   [ ] Key contracts uploaded to Sayou /sources/contracts/
   [ ] Google Drive connected (if applicable)
   [ ] Notion connected (if applicable)

5. ONBOARD
   [ ] Run onboarding-scan skill (extract initial rules)
   [ ] Review extracted rules with founder (confirm/reject/adjust)
   [ ] Tune confidence scores based on founder feedback
   [ ] Enable cron jobs

6. VALIDATE
   [ ] First decision card posted within 72 hours
   [ ] At least one card cites a source the founder forgot
   [ ] Approve/reject loop working
   [ ] Founder says "this is useful" unprompted
```

---

## 8. Cost Model (Per Customer)

| Item | Monthly Cost |
|---|---|
| Vultr VPS (2GB) | $6-12 |
| LLM API (Claude Sonnet, ~1M tokens/day) | $50-150 |
| Embedding API (if semantic search enabled) | $5-10 |
| Amazon Ads API | Free (with seller account) |
| Slack app | Free |
| **Total infrastructure** | **~$60-170/month** |
| **Customer price** | **$2,000-5,000/month** |
| **Gross margin** | **95-97%** |

---

## 9. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| Rule extraction quality too low | High | Validate with SINSURU first. Iterate on extract-rules skill prompt. Start with contracts (high signal) before Slack (noisy). |
| Hermes agent loop unreliable for long tool chains | Medium | Keep skills focused. Max 5-7 tool calls per skill invocation. Test with max_turns limits. |
| Slack Socket Mode disconnects | Medium | Hermes has reconnection logic. Docker restart policy. Monitor via dashboard. |
| LLM costs spike with frequent cron | Medium | Start with 6x/day monitoring, not 12x. Use cheaper models for routine checks. |
| Customer wants web dashboard | Low | Defer. The spec explicitly says "Slack is the interface. Period." |
| Hermes upstream breaking changes | Medium | Pin Docker image version. Test upgrades in staging before rolling to customers. |
| Skills become too complex / long | Medium | Keep skills under 100 lines. Split into sub-skills. Progressive disclosure via skill_view. |

---

## 10. Success Criteria (Pre-YC Application)

From the spec, validated against this architecture:

- [ ] Brain ingests 1 month of SINSURU Slack history and extracts >= 200 brand rules
- [ ] Brain generates >= 30 decision cards/week from real operational state
- [ ] >= 75% of cards are accepted (rejected cards generate new rules)
- [ ] At least one card per week cites an internal source the founder forgot
- [ ] Cards span at least 4 of the 7 decision domains
- [ ] One brand outside SINSURU is paying >= $2K/month
- [ ] Demo video produced with real-time genuine founder reaction

---

## 11. What This Plan Intentionally Excludes

- MCP (use skills + CLI instead — fewer tokens, same capability)
- Web dashboard or standalone UI
- Multi-tenant Hermes (one instance serves multiple brands)
- Custom Hermes fork
- Bid optimization algorithms
- Analytics/charting
- Mobile app
- Public marketing site
- Horizontal scaling of a single instance
