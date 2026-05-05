# Pixell Cortex — Implementation Phases

**Date:** 2026-05-04
**Status:** Pre-implementation

Each phase is a self-contained unit with a closed end-to-end loop and its own test environment. No phase depends on features from a later phase.

Related docs:
- [PIXELL_CORTEX_PLAN.md](./PIXELL_CORTEX_PLAN.md) — Technical architecture
- [PIXELL_CORTEX_PRD.md](./PIXELL_CORTEX_PRD.md) — Product requirements

---

## Phase 0: Environment

**Goal:** A running system where Hermes talks to Slack and can read/write Sayou. No product features — just infrastructure verified end-to-end.

### 0.1 Slack App

| Step | Detail |
|------|--------|
| Create Slack app | api.slack.com → new app from manifest |
| Bot scopes | `channels:history`, `channels:read`, `chat:write`, `groups:history`, `groups:read`, `im:history`, `im:read`, `im:write`, `mpim:history`, `reactions:read`, `users:read` |
| Event subscriptions | `message.channels`, `message.groups`, `message.im`, `app_mention` |
| Socket Mode | Enable, generate app-level token (`xapp-...`) |
| Install to workspace | Get bot token (`xoxb-...`) |
| Create `#brain` channel | Invite @pixell to it |

**Verified when:** @pixell shows as online in Slack. Posting in `#brain` or @mentioning @pixell produces an event in Hermes logs.

### 0.2 VPS + Docker

| Step | Detail |
|------|--------|
| Provision | Vultr VPS: 2GB RAM, 1 vCPU, Ubuntu 24.04 |
| Install | Docker, docker-compose, Python 3.11+, pip |
| Install Sayou | `pip install sayou` |
| Init Sayou workspace | `sayou init` → creates `~/.sayou/` with SQLite + storage |
| Verify | `sayou status` returns workspace info |

### 0.3 Hermes Agent

| Step | Detail |
|------|--------|
| Pull image | `docker pull nousresearch/hermes-agent` |
| Write `docker-compose.yml` | Hermes container with volume mounts for skills, config, and `/opt/cortex/` |
| Write `.env` | `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN`, LLM provider API key |
| Write `config.yaml` | Model selection, `enabled_toolsets: [terminal, web]` |
| Write `SOUL.md` | Minimal version — just identity and tool instructions, no domain logic yet |
| Write `gateway.json` | Slack platform config |
| Start | `docker-compose up -d` |

**Verified when:** Hermes logs show successful Slack connection. In Slack, "@pixell hello" gets a response.

### 0.4 brain CLI

| Step | Detail |
|------|--------|
| Write `bin/brain` | Python wrapper around Sayou CLI: `brain read`, `brain write`, `brain search`, `brain list`, `brain grep` |
| Install on PATH | Symlink or copy to `/opt/cortex/bin/`, ensure Hermes container can execute it |
| Verify from host | `brain list /` returns empty workspace structure |
| Verify from Hermes | In Slack: "@pixell run `brain list /` and tell me what you see" → agent runs command, returns output |

**Verified when:** Hermes can execute `brain` commands via its terminal toolset and return results to Slack.

### 0.5 Workspace Scaffold

Create the Sayou directory structure that all skills expect:

```bash
brain write /config/brand-profile.md --content "placeholder"
brain write /rules/.gitkeep --content ""
brain write /decisions/.gitkeep --content ""
brain write /sources/slack/.gitkeep --content ""
brain write /sources/contracts/.gitkeep --content ""
brain write /reports/.gitkeep --content ""
```

**Verified when:** `brain list / --recursive` shows the full directory tree.

### Phase 0 Acceptance

Everything below must pass before starting Phase 1:

```
[ ] Slack app installed, @pixell online, events flowing
[ ] VPS running, Docker up, Sayou initialized
[ ] Hermes responds to @mentions in Slack
[ ] Hermes can run `brain list /` via terminal and return results
[ ] Workspace directories exist in Sayou
[ ] SOUL.md loaded (check Hermes logs for personality file)
[ ] Round-trip works: user @mentions → Hermes reads Sayou → Hermes replies in Slack
```

This is the foundation. Everything in Phase 1-3 builds on this working.

---

## Phase 1: Knowledge Loop

**Loop:** ingest → extract → query → cite → correct → re-query

**Goal:** The brain has institutional memory, cites sources, learns from corrections. Modes 2 and 3 working.

### Environment Additions

| Component | Detail |
|-----------|--------|
| Test data: Slack export | Export 1-3 months from SINSURU Slack (Settings → Import/Export Data) |
| Test data: Contracts | 2-3 real contracts (OY agreement, creator contract, supplier terms) |
| SOUL.md update | Add brand context, citation rules, decision format, rule types |
| Brand profile | Real /config/brand-profile.md for SINSURU (SKUs, channels, team, thresholds) |

### Features

| # | Feature | What to Build |
|---|---------|---------------|
| 1 | Slack history ingestion script | Parse Slack export JSON → write each message as a Sayou file under /sources/slack/{channel}/{date}-{user}.md with metadata |
| 2 | Contract upload script | Read a document file → extract text → write to /sources/contracts/ with structured YAML frontmatter (parties, date, type, summary) |
| 3 | `extract-rules` skill | Hermes skill (markdown): given a set of source files, identify implicit/explicit rules, write each as a rule file with type/confidence/domain/source_path/source_quote |
| 4 | `onboarding-scan` skill | Hermes skill (markdown): orchestrate first-run extraction — list all sources, batch through extract-rules, report results |
| 5 | `process-feedback` skill | Hermes skill (markdown): parse approve/reject from user reply, log decision outcome, on rejection extract the implicit rule and write it |

### Verification

After building, use the real SINSURU workspace to verify. Not scripted steps — actual usage:

**Ingest and extract:**
- Run Slack ingestion with real export. Check that messages land correctly (`brain list /sources/slack/`).
- Upload 2 contracts. Check frontmatter is accurate (`brain read /sources/contracts/oy-amendment-2025.md`).
- Run onboarding-scan. Review the extracted rules — are they real? Are the confidence levels reasonable? Are the source citations accurate?
- Manually correct bad rules. Delete wrong ones. Adjust confidence on uncertain ones.

**Daily usage (do this for a week):**
- Ask @pixell operational questions you'd normally answer from memory. Does it find the right rule? Does it cite the right source?
- Ask @pixell to analyze something ("can we run a promo on X next week?"). Does it check the right constraints? Does it miss anything?
- Deliberately reject a suggestion with a reason. Does a new rule appear? Is it correctly formed?
- Ask the same question again after the rejection. Does the brain respect the new rule?
- Ask questions in Korean. Does it respond in Korean with the same citation quality?

**What to report back:**
- Rules extracted: total count, how many are accurate, how many are garbage
- Citation quality: does it cite the right source, or just any source?
- Gaps: questions it can't answer that it should be able to
- False confidence: rules marked HIGH that are actually wrong
- Anything surprising (good or bad)

---

## Phase 2: Decision Loop

**Loop:** monitor → detect → recommend → approve → execute → log outcome

**Goal:** The brain monitors autonomously, makes real decisions with live data, executes real actions, logs outcomes. Mode 1 fully working.

### Environment Additions

| Component | Detail |
|-----------|--------|
| Amazon SP API credentials | Seller Central → API access (for SINSURU's account) |
| Amazon Ads API credentials | Amazon Advertising console → API profile |
| Slack app: interactivity | Enable interactivity in Slack app config (for Block Kit button callbacks) |
| Request URL or Lambda | Endpoint to receive button click events from Slack |
| Cron config | Hermes cron jobs file (`~/.hermes/cron/jobs.json`) |
| SOUL.md update | Add decision format, execution rules, reversibility classification |

### Features

| # | Feature | What to Build |
|---|---------|---------------|
| 6 | `fetch-data` script (Amazon) | Python CLI: subcommands for buybox, ad-metrics, inventory, reviews, listings. Pulls from Amazon APIs, writes to /sources/amazon/ in Sayou. |
| 7 | `generate-decision` skill | Hermes skill: read rules + fetch live data → reason across domains → format as decision card → post via post-card |
| 8 | `post-card` script | Python script: post Slack Block Kit message with structured decision data + approve/reject buttons. Handle interaction payloads. |
| 9 | `exec-action` script (Amazon) | Python CLI: subcommands for pause-ads, resume-ads, update-budget, update-bid, update-listing, apply-coupon. Calls Amazon APIs. |
| 10 | Cron jobs | Configure Hermes cron: ops-monitor (6x/day weekdays), daily-briefing (8am), weekly-review (Mon 9am), ingestion-check (every 4h) |
| 11 | `daily-briefing` skill | Hermes skill: summarize yesterday's decisions, rule changes, key metric movements. Post to #brain. |
| 12 | `weekly-review` skill | Hermes skill: compile decision stats, acceptance rate, rule delta, missed opportunities. |
| 13 | `resolve-conflict` skill | Hermes skill: when generate-decision finds contradicting rules, post conflict card with both sources, ask for resolution. |
| 14 | Decision outcome tracking | Extend process-feedback: after execution, schedule outcome check. Update decision file with actual result. |
| 15 | Domain skills (4) | ads-allocation, inventory-routing, pricing-promo, listing-content — domain-specific reasoning procedures |

### Verification

**Before going live:** test each component in isolation.
- Run `fetch-data buybox` manually → verify data appears in Sayou, schema is correct
- Run `fetch-data ad-metrics` → verify campaign data is parseable
- Run `post-card` with hardcoded test data → verify card renders correctly in #brain, buttons work
- Run `exec-action pause-ads` with a test campaign → verify it actually pauses in Amazon console, then resume it
- Trigger `generate-decision` manually → verify it pulls data, checks rules, produces a well-formed card

**Go live with cron — one cycle at a time:**
1. Enable only `daily-briefing` cron first. Run for 3 days. Is the briefing useful? Is it accurate?
2. Add `ops-monitor` at 2x/day (not 6x). Run for a week. Are decision cards actionable? Are sources cited correctly?
3. Approve a few decisions. Verify execution happens and logs correctly.
4. Reject a decision. Verify new rule is created and respected.
5. Scale to 6x/day once confident.

**What to report back:**
- Decision cards per day: how many, how many are actionable vs noise
- Execution success rate: did exec-action actually work?
- False positives: decisions that shouldn't have been recommended
- False negatives: things that should have been caught but weren't
- Card format: is it readable? Too long? Missing info?
- Latency: how long from cron trigger to card appearing?

---

## Phase 3: Multi-User + Multi-Brand

**Loop:** deploy new brand → multiple users interact → permissions enforced → delegation works

**Goal:** Product works for multiple users, operates autonomously when founder is away, deploys to new brands repeatably.

### Environment Additions

| Component | Detail |
|-----------|--------|
| Second Slack workspace | For Brand B (or a test workspace) |
| Second VPS | Separate Vultr instance for Brand B |
| Multiple Slack accounts | At least 3 users in the workspace (founder, ops lead, team member) for permission testing |
| Brand B data | Slack export + contracts for the second brand |
| TikTok Shop API credentials | If testing TikTok adapter |
| Shopify API credentials | If testing Shopify adapter |

### Features

| # | Feature | What to Build |
|---|---------|---------------|
| 16 | User role config | Config file at /opt/cortex/config/roles.yaml mapping Slack user IDs → roles + approval scopes |
| 17 | Approval authority enforcement | Modify process-feedback: check user role before processing approval. Team=blocked, ops_lead=reversible only, founder=all. |
| 18 | Delegated approval mode | Founder sets parameters via Slack ("approve under $5K reversible"). Brain stores as temporary delegation rule. Auto-approves within params. |
| 19 | Deployment script | Shell script: provision VPS → install deps → pull Hermes → install Cortex → write configs → connect Slack → init Sayou → scaffold directories |
| 20 | Automated onboarding skill | Hermes skill: given a Slack export and contracts, run full ingestion + extraction + present rules for review. One command to bootstrap a new brand. |
| 21 | TikTok Shop adapter | fetch-data + exec-action subcommands for TikTok Shop API |
| 22 | Shopify adapter | fetch-data subcommands for Shopify Admin API |
| 23 | `creator-compliance` skill | Hermes skill: review briefs against FDA rules, brand voice, contract terms |

### Verification

**Permissions (use SINSURU workspace with 3 users):**
- As team member: query @pixell → works. Try to approve a card → blocked.
- As ops lead: approve a routine reversible card → works. Try to approve non-reversible → blocked.
- As founder: approve non-reversible → logged.
- Verify that unauthorized approvals never execute.

**Delegation (1-week live test):**
- Founder sets delegation parameters, then stops responding to cards for a week.
- At end of week: review what was auto-approved, what was held, whether any decision was wrong.
- Verify the return summary is accurate.

**Multi-brand (deploy Brand B):**
- Run deployment script against a new VPS.
- Time it. Note every manual step that should have been automated.
- Run onboarding skill with Brand B data. Review extracted rules.
- Trigger monitoring. Verify Brand B decisions reference Brand B rules, not Brand A.
- Verify Brand A instance is completely unaffected.

**What to report back:**
- Permission violations: any case where the wrong user could approve?
- Delegation accuracy: decisions auto-approved that shouldn't have been?
- Deployment time: how long from "new brand" to "first decision card"?
- Onboarding quality: rule extraction quality for a brand the system has never seen?

---

## Phase Summary

| Phase | What it proves | Modes | Features | Success Gate |
|-------|---------------|-------|----------|-------------|
| 0 | Infrastructure works | — | 0 (setup) | Round-trip: @mention → Sayou read → Slack reply |
| 1 | Brain knows things | 2, 3 | 5 | Accurate citations, learns from corrections, 1 week of real usage |
| 2 | Brain makes decisions | 1, 2, 3 | 10 | 30+ cards/week, real execution, 75%+ acceptance |
| 3 | Brain scales | 1, 2, 3 | 8 | Permissions enforced, delegation works, second brand deployed |

**Total: 23 features + environment setup across 4 phases.**

---

## Excluded

- Web dashboard, mobile app
- Bid optimization algorithms
- Multi-tenant single instance
- MCP (skills + CLI only)
- Terraform/Pulumi (manual provisioning is fine)
- Centralized monitoring (one instance at a time)
- Rule decay (no data on whether it's real)
- Channel-mix skill (emerges from usage)
