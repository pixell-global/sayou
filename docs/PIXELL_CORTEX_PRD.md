# Pixell Cortex — Product Requirements Document

**Product:** Pixell Cortex (Company Brain for D2C Brands)
**Bot name:** @pixell
**Date:** 2026-05-03
**Status:** Pre-launch

---

## 1. Product Overview

### Problem Statement

D2C brand founders operate with tribal knowledge scattered across Slack threads, contract PDFs, spreadsheets, and their own heads. They make 30-50 operational decisions per week — ad budget changes, inventory moves, pricing calls, creator approvals — each requiring context from multiple sources. When they're asleep, traveling, or busy, decisions stall. When they hire, knowledge doesn't transfer. When they forget a constraint, money burns.

Current tools solve single-channel optimization (Amazon ads, inventory forecasting, attribution). None of them can block an ad budget increase because of a contract clause in a different channel, or flag that a pricing decision violates a rule the founder stated in Slack three months ago.

### Product Thesis

Pixell Cortex is a company brain that captures institutional knowledge, reasons across domains, and makes operational decisions with the founder's judgment — even when the founder isn't there.

### What Pixell Cortex IS

- An operations partner that monitors, recommends, and executes decisions
- A knowledge system that extracts and enforces brand rules from conversations and documents
- A cross-domain reasoning engine that connects ads, inventory, contracts, pricing, and compliance
- An institutional memory that never forgets and always cites sources

### What Pixell Cortex is NOT

- **Not a search tool.** It doesn't just find information — it reasons over it and makes decisions.
- **Not a chatbot.** It speaks only when it has something valuable to say. No tips, no summaries, no small talk.
- **Not a workflow tool.** It doesn't model processes or build automations. It thinks.
- **Not a dashboard.** It doesn't display metrics for humans to interpret. It interprets them itself.
- **Not a copilot.** It doesn't suggest while you type. It works independently and reports back.

---

## 2. Target Market

### Primary ICP

D2C brand founders operating at $1-20M GMV across multiple sales channels, where one operator (founder or ops lead) makes the majority of operational decisions.

### Three Qualifying Criteria

1. **High-volume decisions:** 30+ operational decisions per week across ads, inventory, pricing, content, and channel management
2. **Knowledge in one head:** Critical brand rules (margin floors, channel conflicts, compliance constraints, relationship dynamics) live primarily in the founder's memory
3. **Quantifiable bleed:** Missed decisions or forgotten rules cost measurable dollars — failed rebate triggers, overspent budgets, compliance violations, stockouts

### Initial Wedge

K-beauty brands in the Asia-to-US D2C corridor. These brands have:
- High channel complexity (Amazon, Olive Young, TikTok Shop, DTC, wholesale)
- Dense regulatory constraints (FDA claims, K-beauty ingredient rules)
- Cross-border operations creating timezone-driven decision gaps
- Founder-dependent tribal knowledge with no documentation culture

### Expansion Path

```
K-beauty Asia→US  →  All Asia→US D2C  →  All multi-channel D2C
(3-5 brands)         (20-50 brands)        (200+ brands)
```

---

## 3. Users & Permissions

### User Roles

| Role | Modes | Can Approve | Can Create Rules | Receives DMs |
|------|-------|-------------|-----------------|--------------|
| **Founder / Decision-maker** | 1, 2, 3 | All decisions | Yes | Yes (urgent blocks) |
| **Ops Lead** | 2, 3 | Routine/reversible only | Yes | No |
| **Team Member** | 3 only | No | No | No |

### Founder / Decision-maker

The primary user. Checks `#brain` channel for briefings and decision cards. Approves or rejects recommendations. Delegates tasks to @pixell. Creates and edits rules. Receives DMs only for urgent, time-sensitive blocks.

### Ops Lead

Second-in-command for operations. Can delegate tasks to @pixell (Mode 2) and query knowledge (Mode 3). Can approve routine, reversible decisions (pause ads, adjust bids within limits). Cannot approve non-reversible actions or override constraints.

### Team Member

Can query @pixell for knowledge (Mode 3 only). Cannot approve decisions or create rules. Primary use case: onboarding, finding processes, understanding "how we do things here."

### Permission Model

Slack-native. No separate auth system. Permissions are determined by:
- Who @mentions @pixell (determines who the response goes to)
- Who responds to decision cards (determines approval authority)
- Channel membership in `#brain` (determines who sees monitoring output)

---

## 4. Three Modes of Work

### Mode 1: Scheduled Monitoring (brain pushes)

**Trigger:** Cron jobs on a fixed schedule (6x/day on weekdays, daily briefings at 8am, weekly reviews Monday 9am).

**Slack surface:** Posts to `#brain` channel. Never interrupts other channels.

**What the brain does:**
1. Pulls current operational state from data sources (BuyBox, ad metrics, inventory, rebate progress)
2. Checks state against all active rules in the knowledge base
3. Identifies decisions needed, opportunities, blocks, anomalies, and confirmations
4. Posts findings as structured cards with sources, impact estimates, and action buttons

**Output format:** Decision cards with:
- Emoji + headline + dollar impact
- 2-3 sentence reasoning
- Source citations (minimum 2)
- Confidence level (HIGH / MEDIUM / LOW)
- Reversibility (YES / NO)
- Approve / Reject buttons (for decision-makers only)

**Output ratio (typical day):**
- 2-3 decisions or opportunities requiring action
- 1-2 status confirmations (on track, no action needed)
- 0-1 urgent blocks (time-sensitive, potential loss)

### Mode 2: Task Execution (user pushes)

**Trigger:** User @mentions @pixell in any channel and asks it to do something.

**Slack surface:** Responds in-thread where mentioned. May also post results to `#brain` if the task produces a decision or report.

**What the brain does:**
1. Parses the task request
2. Determines what data and rules are needed
3. Executes analysis using knowledge base + data fetchers
4. Returns results with reasoning and citations

**Examples:**
- "Check if we can run 20% promo on Serum next week" → checks inventory, margins, channel conflicts, OY calendar
- "Draft a creator brief for Cleansing Powder" → pulls brand voice, compliance rules, past templates
- "Update the OY rebate threshold to $250K" → updates rule, sets confidence to high, logs change

### Mode 3: Knowledge Query (user asks)

**Trigger:** User @mentions @pixell with a question.

**Slack surface:** Responds in-thread. Short, cited answers.

**What the brain does:**
1. Searches rule library, decision history, and ingested sources
2. Assembles answer with source citations
3. Returns concise, factual response

**Examples:**
- "What's our margin floor on Spot Patch?" → "$14.50 cost, $18.00 minimum. Source: /rules/thresholds/..."
- "Why did we hold ad spend last Tuesday?" → links to decision file with reasoning and outcome
- "How do we handle damaged item returns?" → process from rule library with exceptions and source thread

### Language Behavior

@pixell auto-detects the language of the user's message and responds in the same language. Primary languages: Korean and English. No configuration needed — follow the user.

### What the Brain Does NOT Do

- Comment on conversations in other channels
- Offer unsolicited suggestions on messages
- Pop up with tips or reminders
- Summarize threads unless asked
- React to messages with emojis
- DM users except for urgent blocks (founder only)

The brain reads all channels passively for knowledge extraction. It speaks only in `#brain`, in threads where it's @mentioned, or via rare DMs. When the brain speaks, it matters.

---

## 5. Scenarios

### Scenario 1: Morning Briefing

**Context:** Tuesday 8:00 AM. Founder opens Slack, navigates to `#brain`.

**What happens:**

@pixell has posted the daily briefing at 8:00 AM:

> **📋 Daily Briefing — May 6**
>
> **Overnight:** BHA Spot Patch velocity up 40% vs 7-day avg. Current inventory covers 12 days at this rate.
>
> **3 cards below:**
> 1. ✅ Routine: Resume Serum SP campaign (paused for BuyBox recovery, now at 94%)
> 2. ✅ Routine: Increase Cleansing Powder bid from $1.20 to $1.45 (CVR up, ACOS still at 18%)
> 3. 🔔 Opportunity: Creator @skincarejane posted yesterday, 847K views. Contract allows one more repost.

Founder reads the briefing. Taps "approve" on both routine decisions — they auto-execute within minutes. Reads the opportunity card, decides to wait and see if views keep growing, replies "hold — check again tomorrow if it hits 1M."

@pixell acknowledges, sets a reminder, logs the hold with reason.

**Total time:** 3 minutes. Two decisions executed, one deferred with context preserved.

---

### Scenario 2: The Eerie Recall

**Context:** Wednesday 2:00 PM. Ops lead requests a budget increase for Soothing Serum on Amazon.

**What happens:**

The ops lead messages in #amazon-ads: "Let's bump Serum SP budget from $4,200 to $6,800 — ROAS has been solid this week."

@pixell's 3 PM monitoring cycle catches the scheduled budget change and posts to `#brain`:

> 🚫 **Block: Do not increase Serum SP budget — $34K OY rebate at risk**
>
> Olive Young Q2 rebate trigger is at $200K Korea retail GMV. We're at $186K with 11 days remaining. Increasing Amazon spend on an OY-overlap SKU during peak window risks cannibalizing the rebate.
>
> **Sources:**
> - [Contract] OY amendment Section 4.2: "quarterly retail GMV rebate triggers at ₩260M" — /sources/contracts/oy-amendment-2025.md
> - [Slack] Heejee, Mar 14: "we can't push A on Amazon during OY peak" — /sources/slack/general/2026-03-14-heejee.md
> - [Data] Current OY GMV: $186K / $200K trigger (11 days remaining)
> - [Data] Scheduled Amazon increase: $4,200 → $6,800 (tomorrow 9am)
>
> **Confidence:** HIGH
> **Reversible:** YES (can increase later once rebate secured)
> **Impact:** $34,000 rebate at risk
>
> Reply "approve" to hold budget, or "reject: [reason]" to proceed with increase.

The founder sees this. They had completely forgotten about the OY rebate timing. They reply "approve" — the budget stays at $4,200.

Eleven days later, OY GMV hits $200K. Rebate secured. @pixell logs the outcome to the decision file.

**Why this matters:** The brain connected a contract clause, a Slack message from 3 months ago, real-time GMV data, and a scheduled ad change — across three different domains. No human would have caught this in time.

---

### Scenario 3: Task Delegation

**Context:** Thursday 10:30 AM. Founder wants to run a promotion but isn't sure if it's safe.

**What happens:**

Founder messages in #general: "@pixell check if we can run BOGO on Cleansing Powder next week"

@pixell responds in-thread within 2 minutes:

> **Analysis: BOGO on Cleansing Powder — next week**
>
> ✅ **Recommendation: Safe to proceed** with one constraint.
>
> **Checked:**
> - Inventory: 4,200 units in FBA. BOGO at projected velocity burns ~800 units. 3,400 remaining = 18 days coverage. ✅
> - Margin: Unit cost $8.40, BOGO effective price $12.50/unit. Above $11.00 floor. ✅
> - Channel conflicts: No active Olive Young promo on this SKU. ✅
> - Active promos: No existing coupon or deal on this ASIN. ✅
> - Timing: No Prime Day or major event conflict. ✅
>
> **Constraint:** Don't extend beyond 7 days — inventory drops below 14-day safety threshold at day 8.
>
> **Sources:**
> - /rules/thresholds/cleansing-powder-margin.md
> - /rules/constraints/inventory-coverage-minimum.md
> - fetch-data inventory (pulled just now)
>
> Want me to draft the promo setup?

Founder replies: "Yes, set it up for Monday-Sunday. 7 days max." @pixell drafts the configuration and posts a decision card for approval.

---

### Scenario 4: New Hire Ramp

**Context:** New customer service team member, second day on the job. Customer emails about a damaged product.

**What happens:**

New hire messages in #cs-team: "@pixell how do we handle returns for damaged items?"

@pixell responds in-thread:

> **Returns — Damaged Items**
>
> **Standard process:**
> 1. Ask customer for photo of damage
> 2. If damage confirmed: full refund + free replacement, no return required
> 3. Log in returns tracker with "damaged-in-transit" tag
> 4. If 3+ damaged reports on same SKU in 7 days → flag to ops lead for packaging review
>
> **Exceptions:**
> - Items over $50: require ops lead approval before replacement
> - International orders: refund only, no replacement (shipping cost)
>
> **Sources:**
> - Slack thread, Gahye, Jan 22: "just refund and replace, don't make them ship it back" — /sources/slack/cs-team/2026-01-22-returns-policy.md
> - Rule: /rules/constraints/returns-damaged-items.md
>
> Need anything else?

The new hire handles the customer email without interrupting anyone. No Slack search, no asking the founder, no guessing.

---

### Scenario 5: Rejection Creates a Rule

**Context:** Friday 3:00 PM. @pixell recommends a discount on BHA Spot Patch.

**What happens:**

@pixell posts to `#brain`:

> 💰 **Opportunity: 15% coupon on BHA Spot Patch — estimated +$2,400/week revenue**
>
> BHA velocity plateaued at 42 units/day for 2 weeks. Historical data shows 15% coupon lifts velocity 60-80% on this SKU. Current margin supports it.
>
> **Confidence:** MEDIUM
> **Reversible:** YES

Founder rejects: "reject: we never discount BHA below $18. It's our premium positioning anchor."

@pixell acknowledges and creates a new rule:

> ✅ **New rule created:** /rules/constraints/bha-minimum-price.md
>
> "BHA Spot Patch minimum advertised price is $18.00. No coupons or promotions that bring effective price below $18. Reason: premium positioning anchor."
>
> **Confidence:** HIGH (direct from founder)
> **Source:** Founder rejection, May 6 in #brain

Two days later, @pixell's monitoring considers another BHA discount opportunity. It checks the rule library, finds the new constraint, and doesn't recommend it. The rule is working.

---

### Scenario 6: Founder Vacation

**Context:** Founder is in Korea for a week. Timezone makes real-time approval impractical.

**What happens:**

Before leaving, founder tells @pixell: "I'll be in Korea this week. Approve routine stuff, hold anything over $5K impact or non-reversible for when I'm back."

@pixell adjusts its behavior for the week:

**Over 7 days:**
- 38 decisions auto-executed (all reversible, all under $5K impact): bid adjustments, campaign pauses/resumes, inventory reroutes, listing copy updates
- 2 decisions held for approval (one non-reversible partnership response, one $8K budget reallocation)
- 0 critical failures
- Decision velocity: 5.4 decisions/day (vs. normal 4.8/day with founder present)

When founder returns, `#brain` has a summary:

> **📊 Week in Review (May 12-18, Founder Away)**
>
> **Executed:** 38 decisions, 100% within policy
> **Held:** 2 (awaiting your approval below)
> **New rules extracted:** 3 (from team Slack, low confidence — need your confirmation)
> **Revenue impact:** +$4,200 estimated from timely bid adjustments
>
> [Decision cards for the 2 held items follow]

The brand operated normally for a week without the founder. This is the product working.

---

### Scenario 7: Rule Conflict

**Context:** @pixell detects two rules that contradict each other during a decision.

**What happens:**

While evaluating whether to increase TikTok ad spend, @pixell finds:

- Rule A: "When TikTok ROAS > 4x, increase budget by 20%" (from /rules/triggers/tiktok-roas-scaling.md, confidence: medium)
- Rule B: "Total monthly ad spend cannot exceed $15K across all channels" (from /rules/constraints/total-ad-budget-cap.md, confidence: high)

Current state: TikTok ROAS is 4.3x, but total spend is at $14,200. A 20% TikTok increase would push total to $15,800.

@pixell posts to `#brain`:

> ⚠️ **Rule Conflict Detected**
>
> Two rules contradict on TikTok budget:
>
> **Rule A** (triggers/tiktok-roas-scaling.md): Increase TikTok budget 20% when ROAS > 4x
> - Source: Founder instruction, Apr 3 — /sources/slack/ads/2026-04-03-tiktok-scaling.md
> - Confidence: MEDIUM
>
> **Rule B** (constraints/total-ad-budget-cap.md): Total monthly ad spend cannot exceed $15K
> - Source: Budget planning session, Mar 1 — /sources/slack/finance/2026-03-01-budget.md
> - Confidence: HIGH
>
> **Current state:** ROAS at 4.3x, total spend at $14,200. Increasing TikTok by 20% would hit $15,800.
>
> **Options:**
> 1. Respect the cap (Rule B wins — higher confidence)
> 2. Raise the cap to $17K given strong ROAS
> 3. Reduce other channel spend to make room for TikTok
>
> Which approach? I'll update the rules accordingly.

Founder responds: "Option 2 — raise cap to $17K. TikTok is printing money right now."

@pixell updates the budget cap rule, increases TikTok spend, and logs the resolution.

---

## 6. Knowledge Architecture

### Five Rule Types

| Type | Definition | Example |
|------|-----------|---------|
| **Constraint** | "Don't do X during Y" | Don't increase Amazon ads during OY peak window |
| **Trigger** | "If metric > threshold, do Z" | If BuyBox < 80%, pause ads on that ASIN |
| **Threshold** | "Never cross N" | BHA minimum price is $18; total ad spend cap $15K |
| **Voice** | "Never say X in claims" | Don't use "anti-aging" in US marketing; don't claim FDA approval |
| **Relationship** | "Person A approves type B" | Gahye approves budgets over $5K; Heejee owns OY relationship |

### Rule Lifecycle

```
Source Material (Slack, contracts, documents)
    │
    ▼
EXTRACTION — Brain identifies implicit/explicit rules
    │
    ▼
CONFIDENCE ASSIGNMENT — Brain assigns high/medium/low based on source quality
    │
    ▼
CONFIRMATION — User confirms, adjusts, or rejects extracted rule
    │
    ▼
ACTIVATION — Rule enters active library, applied to future decisions
    │
    ▼
USE — Rule cited in decisions, validated by outcomes
    │
    ▼
DECAY / UPDATE — Rules not cited in 90 days flagged for review;
                  contradicted rules surfaced for resolution
```

### Rule Confidence Model

Confidence is expressed as HIGH / MEDIUM / LOW, not numeric scores. The brain assigns confidence based on source quality:

| Confidence | Assignment Criteria | Example |
|------------|-------------------|---------|
| **HIGH** | Direct founder statement, signed contract, explicit instruction | "We never discount BHA below $18" (founder said it) |
| **MEDIUM** | Inferred from behavior pattern, team member statement, single data point | Founder rejected 3 discounts on BHA → inferred price floor |
| **LOW** | Weak signal, old source, ambiguous context, contradicted by newer info | Pricing mentioned in passing 6 months ago, no recent confirmation |

Users can adjust confidence at any time. New brain-extracted rules start at the assigned level and go through confirmation:
- HIGH confidence rules: activated immediately, mentioned in next briefing for awareness
- MEDIUM confidence rules: posted to `#brain` for confirmation within 48 hours
- LOW confidence rules: batched in weekly review for bulk confirmation/rejection

### Decision Lifecycle

```
DETECTION — Monitoring finds a situation requiring a decision
    │
    ▼
RECOMMENDATION — Brain posts decision card with reasoning + sources
    │
    ▼
APPROVAL / REJECTION — User responds
    │
    ├── Approved → EXECUTION (if reversible) or LOGGING (if recommend-only)
    │
    └── Rejected → RULE EXTRACTION (why was this wrong? what's the implicit rule?)
         │
         ▼
    OUTCOME LOGGING — Result tracked, decision file updated with actual impact
```

### Source Citation Requirement

Every rule and every decision must cite at least one source. If the brain cannot cite a source, it must say so explicitly ("I don't have a source for this — proceeding based on general best practice. Confidence: LOW."). This is non-negotiable. Unsourced claims erode trust.

---

## 7. Data Source Adapters

Pixell Cortex uses a pluggable adapter pattern for data ingestion. Each adapter handles authentication, rate limiting, data normalization, and storage into Sayou.

### Phase 1: Slack

- Message history (all public channels, opted-in private channels)
- Thread contents and reactions
- File attachments (contracts, spreadsheets, images)
- User metadata (who said what, when)

### Phase 2: Amazon Seller Central

- Advertising: SP/SB/SD campaigns, bids, budgets, ACOS, ROAS
- BuyBox: ownership percentage, competing sellers, pricing
- Inventory: FBA levels, velocity, days of coverage, restock recommendations
- Reviews: new reviews, rating changes, sentiment
- Listings: content, A+ pages, suppression status

### Phase 3: TikTok Shop + Shopify

- TikTok: creator metrics, ad performance, GMV, content analytics
- Shopify: DTC orders, inventory sync, discount usage, customer data

### Future Adapters

- Google Drive: synced documents, spreadsheets, slide decks
- Notion: pages, databases, linked content
- Email: creator communications, supplier correspondence
- Call transcripts: meeting recordings, supplier calls
- CRM: customer relationships, deal pipeline (if applicable)

### Adapter Design Principles

- Read-only by default. Write access (execution) is a separate system.
- All fetched data stored in Sayou under `/sources/{adapter}/` with full provenance metadata.
- Adapters run on schedule (cron) or on-demand (brain requests via `fetch-data` CLI).
- Failed fetches logged, retried, and surfaced in daily briefing if persistent.

---

## 8. Decision Execution Model

### Reversible Actions (auto-execute on approval)

Actions that can be undone within minutes if something goes wrong:

| Action | Undo Path |
|--------|-----------|
| Pause/resume ad campaigns | Re-pause or re-resume |
| Adjust bid within ±30% | Revert to previous bid |
| Adjust daily budget within ±50% | Revert to previous budget |
| Update listing copy (title, bullets, description) | Revert to previous version |
| Reroute inventory between fulfillment centers | Reroute back |
| Apply/remove coupon or promotion | Remove/reapply |

These execute immediately upon approval. The ops lead can approve these without the founder.

### Non-Reversible Actions (recommend only)

Actions with permanent or hard-to-reverse consequences:

| Action | Why Non-Reversible |
|--------|-------------------|
| Delete a listing | Amazon reinstatement is slow/uncertain |
| Send external email (to creator, supplier) | Can't unsend |
| Commit to channel exclusivity deal | Contractual obligation |
| Place a purchase order | Financial commitment |
| Respond to Amazon case/violation | Creates official record |
| Price below MAP on record | May trigger contractual penalties |

These are recommendation-only. @pixell provides the analysis and draft, but a human must execute manually. Only the founder can approve these.

### Execution Logging

Every executed action is logged to a decision file in Sayou:

```yaml
executed: true
executed_at: 2026-05-06T14:32:00Z
execution_method: exec-action pause-ads --campaign CAMP123
result: success
rollback_command: exec-action resume-ads --campaign CAMP123
outcome_check_at: 2026-05-07T08:00:00Z
```

If an execution fails, @pixell posts immediately to `#brain` with the error and suggested remediation.

---

## 9. Competitive Map

| Category | Players | What They Do | What They Can't Do |
|----------|---------|--------------|-------------------|
| **Amazon Ad Optimization** | Intentwise, Pacvue, Perpetua | Single-channel bid/budget optimization, keyword harvesting, dayparting | Can't see contracts, can't reason across channels, no institutional knowledge, no rule extraction |
| **D2C Analytics** | Triple Whale, Northbeam | Attribution, ROAS tracking, creative analytics, customer LTV | Reporting only — no decisions, no execution, no cross-domain reasoning, no knowledge accumulation |
| **Multi-Channel Management** | ChannelAdvisor, Feedvisor | Listing sync, repricing, inventory management across marketplaces | No knowledge layer, no rule extraction, no institutional memory, no proactive decisions |
| **Enterprise Knowledge** | Glean, Notion AI, Slack AI | Search across company docs, summarization, Q&A | Search, not decisions. No rule extraction, no execution, no monitoring, no cross-domain reasoning |
| **AI Ecommerce Agents** | Genstore, Enrich Labs | Task execution for specific functions (customer service, content generation) | No company brain — no institutional knowledge, no rule accumulation, no cross-domain reasoning |
| **Inventory Planning** | Inventory Planner, SoStocked | Demand forecasting, reorder point calculation | No brand rules, no channel conflict awareness, no contract constraints |
| **Creator Management** | CreatorIQ, Grin | Creator discovery, campaign management, payment tracking | No compliance reasoning, no brand voice enforcement, no cross-domain impact analysis |

### Cortex's Moat

**Cross-domain reasoning over institutional knowledge.**

No point solution can block an ad budget increase because of a contract clause in a different channel. No knowledge tool can execute decisions. No execution tool has institutional memory. Cortex does all three because it has:

1. **The rules** (from Sayou) — extracted from Slack, contracts, and founder decisions
2. **The agent** (from Hermes) — reasoning, scheduling, execution, learning
3. **The integrations** — data from all channels in one brain

The compound effect: every decision made, every rule extracted, every rejection processed makes the brain smarter. Competitors would need to rebuild the entire knowledge graph from scratch for each customer.

---

## 10. Success Metrics

### Primary Metrics

| Metric | Target | Why It Matters |
|--------|--------|---------------|
| Rules under management | 200+ per brand within 30 days | Measures knowledge capture depth |
| Decision cards per week | 30+ | Measures operational coverage |
| Acceptance rate | 75%+ | Measures decision quality |
| "Eerie recall" moments per week | 1+ | Measures cross-domain reasoning value |
| Domain coverage | 4+ of 7 domains | Measures breadth of operational reach |

### Secondary Metrics

| Metric | Target | Why It Matters |
|--------|--------|---------------|
| Founder vacation impact on decision velocity | <10% drop | Measures true autonomy |
| New hire time-to-first-knowledge-query | Within first week | Measures onboarding value |
| Rule conflict detection rate | 1+ per month | Measures knowledge integrity maintenance |
| Rejected decisions that create new rules | 80%+ of rejections | Measures learning velocity |
| Average time from detection to approval | <2 hours (business hours) | Measures workflow integration |
| Decision outcome accuracy | 90%+ positive outcomes | Measures long-term decision quality |

### Anti-Metrics (things we do NOT optimize for)

- Number of messages sent (we want fewer, higher-value messages)
- Response time to queries (accuracy > speed)
- Number of integrations connected (depth > breadth)
- Rules created per day (quality > quantity)

---

## 11. Phased Rollout

### Phase 1: Foundation (Demo-Ready)

**Goal:** One brand (SINSURU), one "eerie moment" card, working Slack interaction.

**PRD features delivered:**
- Mode 3 (Knowledge Query) — fully working
- Mode 2 (Task Execution) — basic analysis tasks
- Mode 1 (Scheduled Monitoring) — manual trigger, no cron
- Rule extraction from Slack history and contracts
- Approve/reject flow via text replies
- Source citation on all outputs

**Success gate:** At least one decision card cites a source the founder forgot.

### Phase 2: Decision Engine

**Goal:** Automated monitoring, multiple decision domains, real execution.

**PRD features delivered:**
- Mode 1 fully automated (cron jobs, 6x/day monitoring)
- Decision execution (reversible actions)
- Amazon data adapter (BuyBox, ads, inventory)
- Slack Block Kit decision cards with buttons
- Decision logging with outcomes
- Rule conflict detection
- 4+ decision domains active

**Success gate:** 30+ decision cards/week from real operational state, 75%+ acceptance rate.

### Phase 3: Multi-Brand

**Goal:** Second and third paying customers, repeatable deployment.

**PRD features delivered:**
- Full user permissions model (founder / ops lead / team member)
- Onboarding skill (automated initial rule extraction)
- TikTok Shop + Shopify adapters
- Non-reversible action recommendations
- Weekly review reports
- Rule confidence confirmation flow
- Founder vacation mode

**Success gate:** 2+ paying customers at $2K+/month.

### Phase 4: Scale

**Goal:** 10+ customers, operational efficiency.

**PRD features delivered:**
- Centralized monitoring across instances
- Automated provisioning
- Skill distribution (update all instances from central repo)
- Advanced rule lifecycle (decay, review, bulk confirmation)
- Cross-brand pattern detection (anonymized)

**Success gate:** 10+ customers, consistent gross margin > 90%.

---

## 12. Out of Scope

The following are explicitly excluded from Pixell Cortex:

- **Web dashboard or standalone UI** — Slack is the interface. Period.
- **Mobile app** — Slack mobile covers this.
- **Bid optimization algorithms** — Use existing tools (Intentwise, Pacvue) as substrate; Cortex reasons over their outputs.
- **Multi-tenant single instance** — One Hermes instance per customer. Skills accumulate per-brand.
- **Public marketing site** — Not needed pre-product-market-fit.
- **MCP** — Skills + CLI only. MCP tool schemas waste tokens on every LLM turn. Terminal is the universal interface.
- **Real-time streaming suggestions** — Brain speaks only when it has something valuable. No copilot behavior.
- **Custom Hermes fork** — All customization via skills, CLI scripts, and configuration.
- **Analytics/charting** — Text-based reporting in Slack. No visualization layer.
- **Workflow builder** — Brain thinks, not automates. No drag-and-drop process modeling.

---

## Appendix: Technical Architecture Reference

See [PIXELL_CORTEX_PLAN.md](./PIXELL_CORTEX_PLAN.md) for:
- Infrastructure diagram (per-customer Vultr VPS)
- Component list (Hermes, Sayou, CLI scripts)
- Skill directory structure
- Sayou knowledge schema (frontmatter formats)
- Hermes configuration (SOUL.md, cron jobs, gateway)
- Cost model ($60-170/mo infrastructure, $2-5K/mo customer price, 95%+ margin)
- Risk register
- Customer deployment checklist
