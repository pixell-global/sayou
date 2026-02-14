"""
Seed a persistent workspace with ~28 research files across 5 folders.

Writes to a file-backed SQLite database at examples/.data/sayou.db
so the data survives across runs. Re-running is idempotent (creates
new versions, never errors).

Usage:
    python examples/seed_data.py
"""

import asyncio
import os
from pathlib import Path

from sayou import Workspace

# Persistent storage alongside this script
DATA_DIR = Path(__file__).parent / ".data"
DB_PATH = DATA_DIR / "sayou.db"
STORAGE_PATH = DATA_DIR / "storage"

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
ORG_ID = "example-org"
USER_ID = "researcher"


# ── File definitions ─────────────────────────────────────────────────

COMPETITORS = {
    "competitors/notion.md": """\
---
company: Notion
sector: productivity
status: active
tags: [collaboration, docs, wiki]
---

# Notion Competitive Analysis

All-in-one workspace combining docs, wikis, and project management.
Founded 2013, valued at $10B+ as of 2024.

## Strengths
- Extremely flexible block-based editor
- Strong template marketplace and community
- Freemium model drives viral adoption within teams
- AI features integrated directly into the editor

## Weaknesses
- Performance degrades with large workspaces
- Offline support is limited
- Pricing escalates quickly for large teams
- Search can be slow across many pages

## Pricing
- Free for personal use
- Plus: $10/user/month
- Business: $18/user/month
- Enterprise: custom pricing

## Key Takeaway
Notion dominates the "second brain" category but struggles with
enterprise-scale deployments. Their AI integration is aggressive
but quality varies. Watch for pricing pressure from open-source
alternatives.
""",
    "competitors/linear.md": """\
---
company: Linear
sector: developer-tools
status: active
tags: [project-management, engineering, issue-tracking]
---

# Linear Competitive Analysis

Modern project management tool built for software teams.
Known for speed, keyboard shortcuts, and opinionated workflows.

## Strengths
- Blazing fast UI with local-first architecture
- Cycles and roadmaps align well with agile sprints
- GitHub/GitLab integrations are best-in-class
- Strong developer community and brand loyalty

## Weaknesses
- Limited customization compared to Jira
- No built-in documentation or wiki
- Smaller integration ecosystem
- Less suited for non-engineering teams

## Pricing
- Free for small teams (up to 250 issues)
- Standard: $8/user/month
- Plus: $14/user/month

## Key Takeaway
Linear has captured the developer mindshare for issue tracking.
Their focus on speed and DX sets a high bar. Consider partnering
rather than competing directly in this space.
""",
    "competitors/airtable.md": """\
---
company: Airtable
sector: data-management
status: active
tags: [spreadsheet, database, no-code, automation]
---

# Airtable Competitive Analysis

Spreadsheet-database hybrid with automation and app-building.
Valued at $11B, serves both technical and non-technical users.

## Strengths
- Intuitive interface bridges spreadsheet and database worlds
- Rich field types (attachments, linked records, formulas)
- Automations reduce manual workflow steps
- Interface designer enables custom internal tools

## Weaknesses
- Row limits on lower tiers frustrate power users
- Complex formulas are harder to debug than SQL
- Pricing jumps significantly at scale
- API rate limits constrain heavy integrations

## Pricing
- Free: 1,000 records per base
- Team: $20/user/month
- Business: $45/user/month
- Enterprise: custom

## Key Takeaway
Airtable owns the "structured data for everyone" category. Their
pricing model creates natural upgrade pressure. We should ensure
our data layer is more developer-friendly than Airtable's API.
""",
    "competitors/figma.md": """\
---
company: Figma
sector: design
status: monitoring
tags: [design, collaboration, prototyping]
---

# Figma Competitive Analysis

Browser-based design tool acquired by Adobe (deal later abandoned).
Dominant in UI/UX design with strong multiplayer collaboration.

## Strengths
- Real-time multiplayer editing in the browser
- Dev mode bridges designer-developer handoff
- FigJam for whiteboarding complements core product
- Plugin ecosystem is extensive and growing
- Free tier is generous for individuals

## Weaknesses
- Heavy files can lag in the browser
- Offline support requires desktop app
- Adobe acquisition uncertainty affected roadmap
- Less capable for print or illustration work

## Pricing
- Free: 3 files, unlimited viewers
- Professional: $15/editor/month
- Organization: $45/editor/month
- Enterprise: $75/editor/month

## Key Takeaway
Figma's collaboration model is the gold standard. We should study
their multiplayer architecture for our own real-time features.
Not a direct competitor but a design partner worth integrating with.
""",
    "competitors/retool.md": """\
---
company: Retool
sector: internal-tools
status: active
tags: [low-code, internal-tools, developer-platform]
---

# Retool Competitive Analysis

Low-code platform for building internal tools. Targets developers
who want to build admin panels, dashboards, and workflows quickly.

## Strengths
- Component library covers 90% of internal tool needs
- Native database and API connectors are extensive
- Retool Workflows handles automation and scheduling
- Self-hosted option appeals to enterprise security teams

## Weaknesses
- Learning curve steeper than pure no-code tools
- Pricing is opaque and expensive at scale
- Vendor lock-in risk with proprietary component model
- Mobile support is limited

## Pricing
- Free: 5 users, limited features
- Team: $10/user/month
- Business: $50/user/month
- Enterprise: custom

## Key Takeaway
Retool proves that developers want low-code for internal tools,
not customer-facing products. Our SDK approach could complement
or compete with their visual builder. Consider the build-vs-buy
calculus for our own admin tooling.
""",
    "competitors/vercel.md": """\
---
company: Vercel
sector: developer-platform
status: monitoring
tags: [deployment, frontend, infrastructure, DX]
---

# Vercel Competitive Analysis

Frontend cloud platform and creators of Next.js. Leading the
edge computing and serverless deployment space.

## Strengths
- Next.js framework dominance gives them distribution
- Deploy preview URLs for every PR are industry-standard
- Edge Functions enable global low-latency computing
- v0 AI tool generates UI components from prompts
- Developer experience is their core moat

## Weaknesses
- Vendor lock-in with Next.js-specific features
- Pricing surprises on bandwidth and function invocations
- Limited backend/database story (partnering with Neon, Supabase)
- Enterprise features lag behind AWS/GCP

## Pricing
- Hobby: free
- Pro: $20/user/month
- Enterprise: custom
- Usage-based billing for compute and bandwidth

## Key Takeaway
Vercel's bet on DX and AI-assisted development (v0) aligns with
broader industry trends. Their pricing model is controversial but
effective. We should adopt their preview deployment pattern for
our own CI/CD pipeline.
""",
}

TRENDS = {
    "trends/ai-agents.md": """\
---
title: AI Agents and Autonomous Systems
sector: artificial-intelligence
status: tracking
author: research-team
quarter: Q1-2026
date: "2026-01-15"
tags: [AI, agents, automation, LLM]
---

# AI Agents and Autonomous Systems

The shift from chatbots to autonomous agents represents the biggest
paradigm change since mobile. Key developments to track:

## Market Signals
- OpenAI, Anthropic, and Google all shipping agent frameworks
- Enterprise adoption growing 3x quarter-over-quarter
- Venture funding in agent startups exceeds $5B in 2025
- Open-source agent frameworks fragmenting the space

## Technical Trends
- Tool use and function calling becoming standardized
- Memory and context management still unsolved at scale
- Multi-agent orchestration patterns emerging
- Sandboxed execution environments gaining traction

## Impact on Our Strategy
- Agent-first architecture should inform all product decisions
- Our workspace API is well-positioned as agent infrastructure
- Consider partnerships with agent framework providers
- Pricing model should account for agent-driven usage patterns

## Risks
- Regulatory uncertainty around autonomous decision-making
- Quality and reliability concerns limit enterprise adoption
- Race to the bottom on pricing for LLM inference
- Security vulnerabilities in agent tool-use patterns
""",
    "trends/api-first.md": """\
---
title: API-First Product Development
sector: developer-tools
status: active
author: engineering-lead
quarter: Q1-2026
date: "2026-01-20"
tags: [API, developer-experience, platform, SDK]
---

# API-First Product Development

Building products where the API is the primary interface, with
UI as one of many possible clients.

## Why This Matters
- Developer adoption drives B2B growth (bottom-up GTM)
- APIs enable integration ecosystems that create moats
- Agent workflows require programmatic access
- CLI and SDK users have higher retention than UI-only users

## Industry Examples
- Stripe: API-first payments created a $95B company
- Twilio: Communication APIs before any UI dashboard
- Vercel: CLI deploys before web dashboard existed
- Linear: GraphQL API enables deep IDE integrations

## Our Position
- Workspace API is our core asset
- MCP server gives us Claude Code distribution
- SDK adoption should be tracked as a key metric
- Documentation quality directly correlates with adoption

## Action Items
- Invest in API reference documentation
- Build more SDK examples and tutorials
- Track API adoption metrics separately from UI metrics
- Consider developer relations hires
""",
    "trends/vertical-saas.md": """\
---
title: Vertical SaaS Consolidation
sector: enterprise
status: tracking
author: research-team
quarter: Q1-2026
date: "2026-02-01"
tags: [vertical-SaaS, enterprise, consolidation, market]
---

# Vertical SaaS Consolidation

Industry-specific software is consolidating as horizontal tools
add vertical features and vertical players expand horizontally.

## Key Observations
- Horizontal tools (Notion, Airtable) adding industry templates
- Vertical players (Toast, Procore) expanding feature sets
- AI enabling faster vertical customization of horizontal tools
- Acquisition activity increasing in healthcare and fintech verticals

## Market Implications
- Pure horizontal play increasingly crowded
- Vertical expertise creates defensible positioning
- Data network effects strongest within industry verticals
- Pricing power higher in vertical markets (willingness to pay)

## Strategic Considerations
- Should we pursue vertical-specific features?
- Agent customization could enable pseudo-vertical positioning
- Research which verticals have the strongest pull for our tools
- Partnership model may be better than building vertical features
""",
    "trends/developer-experience.md": """\
---
title: Developer Experience as Competitive Advantage
sector: developer-tools
status: active
author: engineering-lead
quarter: Q1-2026
date: "2026-01-25"
tags: [DX, developer-experience, tooling, adoption]
---

# Developer Experience as Competitive Advantage

DX has evolved from a nice-to-have to a primary differentiator.
Companies with superior DX consistently win developer mindshare.

## What Great DX Looks Like
- Zero-to-hello-world in under 5 minutes
- Error messages that tell you how to fix the problem
- Interactive documentation with runnable examples
- Type safety and IDE autocomplete out of the box
- Predictable, well-documented behavior (no surprises)

## Metrics That Matter
- Time to first API call
- Documentation page views vs. support tickets
- SDK download trends
- Developer satisfaction (NPS, surveys)
- Community contributions (PRs, plugins, examples)

## Our DX Audit
- Workspace API: good ergonomics, needs more examples
- MCP server: zero-config is excellent, docs need improvement
- SDK: type hints are solid, error messages need work
- Onboarding: no guided tutorial exists yet

## Recommendations
- Create an interactive getting-started tutorial
- Add more error context to exception messages
- Build a playground environment for experimentation
- Track DX metrics in our analytics dashboard
""",
    "trends/open-source.md": """\
---
title: Open Source as Distribution Strategy
sector: developer-tools
status: tracking
author: research-team
quarter: Q1-2026
date: "2026-02-05"
tags: [open-source, distribution, community, licensing]
---

# Open Source as Distribution Strategy

Open source has become the dominant distribution channel for
developer tools. Understanding licensing and community dynamics
is critical for our go-to-market strategy.

## Successful Models
- Open core: free OSS base + paid enterprise features (GitLab)
- Cloud-hosted: free self-host + paid managed service (Supabase)
- Dual license: AGPL + commercial (MongoDB, Elastic)
- Source-available: readable but restricted (BSL, SSPL)

## Community Dynamics
- Contributors become advocates and enterprise champions
- GitHub stars correlate with awareness but not revenue
- Documentation contributions are the highest-value signal
- Discord/Slack communities drive retention

## Our Open Source Position
- Sayou is Apache-2.0 licensed — permissive and adoption-friendly
- Community building should be an explicit goal
- Consider which features stay open vs. become commercial
- Track contributor funnel: star → issue → PR → champion

## Risks
- AWS/big cloud vendors can fork and compete
- Maintaining OSS community requires dedicated resources
- License changes (rug-pulls) damage trust permanently
- Support burden can overwhelm small teams
""",
    "trends/privacy-regulation.md": """\
---
title: Privacy Regulation and Data Sovereignty
sector: compliance
status: monitoring
author: legal-team
quarter: Q1-2026
date: "2026-02-10"
tags: [privacy, GDPR, compliance, data-sovereignty, regulation]
---

# Privacy Regulation and Data Sovereignty

Global privacy regulations are tightening. Data sovereignty
requirements are reshaping infrastructure decisions.

## Regulatory Landscape
- GDPR enforcement increasing with larger fines
- US state-level privacy laws creating patchwork compliance
- AI-specific regulations emerging (EU AI Act)
- Data localization requirements in Asia-Pacific markets

## Technical Implications
- Multi-region data storage becoming mandatory for global products
- Right-to-deletion requires careful data architecture
- Consent management adds UX complexity
- Audit trails needed for compliance verification

## Impact on Our Product
- Workspace data must support region-pinned storage
- Deletion must cascade through all versions and storage backends
- Agent interactions may need consent tracking
- Self-hosted deployment option addresses sovereignty concerns

## Action Items
- Audit current data flows for compliance gaps
- Implement region-aware storage routing
- Add data retention and deletion policies
- Consult legal on AI-specific regulatory exposure
""",
}

PRODUCTS = {
    "products/workspace-v2.md": """\
---
title: Workspace V2 — Multi-tenant Collaboration
status: in-progress
priority: high
author: product-lead
tags: [workspace, collaboration, multi-tenant, core]
---

# Workspace V2: Multi-tenant Collaboration

Upgrade the workspace from single-user to multi-tenant with
role-based access control and real-time collaboration.

## Goals
- Multiple users can read/write the same workspace
- Permission model: owner, writer, reader roles
- Audit log tracks who changed what and when
- Workspace-level settings (retention policy, storage quota)

## Technical Design
- Add workspace_members table with role column
- Permission checks in WorkspaceService before each operation
- Event sourcing for real-time sync (future phase)
- Storage quotas enforced at write time

## Success Criteria
- 3+ users can collaborate in a single workspace
- Reader role cannot write or delete files
- All mutations logged with user attribution
- No performance regression vs. single-user mode

## Timeline
- Phase 1 (current): Permission model and member management
- Phase 2: Real-time notifications on file changes
- Phase 3: Conflict resolution for concurrent edits

## Dependencies
- Database migration for workspace_members table
- API endpoints for member management
- Frontend UI for sharing and permissions
""",
    "products/search-overhaul.md": """\
---
title: Search Overhaul — Semantic and Faceted Search
status: planned
priority: high
author: engineering-lead
tags: [search, semantic, embeddings, discovery]
---

# Search Overhaul: Semantic and Faceted Search

Current search is keyword-based. Upgrade to semantic search with
embedding-based similarity and faceted filtering.

## Motivation
- Users can't find files when they don't remember exact terms
- Frontmatter filters are powerful but require knowing field names
- Agent queries are often natural language, not keywords
- Competitive products (Notion, Confluence) have better search

## Proposed Approach
- Generate embeddings on write (OpenAI text-embedding-3-small)
- Store vectors in pgvector extension (Postgres) or sqlite-vss
- Hybrid search: combine keyword BM25 + vector similarity
- Faceted search: auto-discover frontmatter fields as facets

## API Changes
- `ws.search(query="...")` becomes semantic by default
- New parameter: `ws.search(query="...", mode="keyword|semantic|hybrid")`
- New endpoint: `ws.facets()` returns available filter dimensions

## Risks
- Embedding cost at scale (~$0.02 per 1M tokens)
- Vector storage adds infrastructure complexity
- Semantic search can return surprising results
- Migration path from current keyword search

## Success Metrics
- Search recall improves by 40%+
- Average time to find a file decreases
- Agent query accuracy improves on ambiguous questions
""",
    "products/mobile-app.md": """\
---
title: Mobile App — Read-Only Workspace Access
status: backlog
priority: medium
author: product-lead
tags: [mobile, iOS, Android, read-only]
---

# Mobile App: Read-Only Workspace Access

Provide mobile access to workspace files for on-the-go review.
Start with read-only to validate demand before investing in editing.

## Scope (V1)
- Browse workspace folders and files
- Read files with frontmatter display
- Basic search (keyword)
- Push notifications for file changes (optional)

## Out of Scope (V1)
- File creation or editing
- Offline access
- Agent interactions
- File uploads or attachments

## Technical Approach
- React Native for cross-platform
- Reuse existing API — no backend changes needed
- Authentication via Firebase (already supported)
- Markdown rendering with syntax highlighting

## Market Validation
- Survey existing users for mobile interest
- Track mobile web traffic to gauge demand
- Competitive analysis: Notion, Obsidian both have mobile apps

## Success Criteria
- 20% of active users install within 3 months
- 5+ sessions per user per month
- App Store rating above 4.0
""",
    "products/sso-integration.md": """\
---
title: SSO Integration — SAML and OIDC
status: planned
priority: high
author: engineering-lead
tags: [SSO, SAML, OIDC, enterprise, security]
---

# SSO Integration: SAML and OIDC

Enterprise customers require Single Sign-On. Support SAML 2.0
and OpenID Connect for corporate identity providers.

## Requirements
- SAML 2.0 for Okta, Azure AD, OneLogin
- OIDC for Google Workspace, Auth0
- Just-in-time user provisioning
- Organization-level SSO enforcement
- SCIM 2.0 for user directory sync (future)

## Technical Design
- Add SSO configuration to organization settings
- SAML assertion consumer service (ACS) endpoint
- OIDC callback handler alongside existing OAuth
- Session management: SSO sessions expire per IdP policy

## Pricing Implications
- SSO is a standard enterprise gate ($$$)
- Consider including in Business tier vs. Enterprise-only
- Competitive pricing analysis needed

## Dependencies
- Organization settings UI
- Admin role for SSO configuration
- Testing accounts with major IdPs
- Security audit of SAML implementation

## Timeline
- SAML 2.0 support: 4-6 weeks
- OIDC support: 2-3 weeks (simpler protocol)
- SCIM provisioning: 3-4 weeks (future phase)
""",
    "products/analytics-dashboard.md": """\
---
title: Analytics Dashboard — Workspace Usage Insights
status: planned
priority: medium
author: product-lead
tags: [analytics, dashboard, metrics, usage]
---

# Analytics Dashboard: Workspace Usage Insights

Give workspace owners visibility into how their workspace is used.
Track file activity, user engagement, and storage trends.

## Key Metrics
- Files created/updated per day/week
- Most active files and folders
- Storage usage over time
- User activity heatmap
- Search queries and result quality

## Design
- Dashboard page in workspace settings
- Time range selector (7d, 30d, 90d, custom)
- Export to CSV for further analysis
- API endpoint for programmatic access

## Data Collection
- Leverage existing mutation logs (already captured)
- Aggregate into daily rollup tables for performance
- No new tracking required — mine existing data

## Privacy Considerations
- Only workspace owners and admins see analytics
- Individual user activity visible only to admins
- Option to anonymize user-level data
- Retention policy for analytics data (90 days default)

## Success Criteria
- 50% of workspace owners visit dashboard monthly
- Identify top 3 user-requested metrics and include them
- Dashboard loads in under 2 seconds
""",
    "products/api-v2.md": """\
---
title: API V2 — Typed SDK and Webhook Events
status: planned
priority: high
author: engineering-lead
tags: [API, SDK, webhooks, developer-experience, platform]
---

# API V2: Typed SDK and Webhook Events

Upgrade the API with full type safety, SDK code generation,
and webhook events for real-time integrations.

## SDK Improvements
- Auto-generated TypeScript and Python SDKs from OpenAPI spec
- Full type hints for all request/response objects
- Retry logic and rate limiting built into SDK
- Streaming support for large file reads

## Webhook Events
- `file.created`, `file.updated`, `file.deleted`
- `workspace.member_added`, `workspace.member_removed`
- Webhook management API (create, list, delete, test)
- Signature verification for security
- Retry with exponential backoff on failure

## API Versioning
- URL-based versioning: `/api/v2/...`
- V1 maintained for 12 months after V2 launch
- Migration guide and compatibility layer
- Deprecation warnings in V1 responses

## Developer Experience
- Interactive API explorer (Swagger UI + examples)
- Webhook event log for debugging
- Rate limit headers in all responses
- Better error messages with suggested fixes

## Success Metrics
- SDK adoption reaches 60% of API users
- Webhook delivery success rate above 99.5%
- Time to first successful API call under 5 minutes
- Support tickets related to API decrease by 30%
""",
}

INSIGHTS = {
    "insights/churn-analysis.md": """\
---
title: Q4 2025 Churn Analysis
status: final
author: data-team
quarter: Q4-2025
tags: [churn, retention, analysis, metrics]
---

# Q4 2025 Churn Analysis

Analysis of user churn patterns from October-December 2025.
Total churn rate: 8.2% (down from 11.5% in Q3).

## Key Findings

### Who Churns
- Solo users churn at 3x the rate of team users
- Users who never use search churn within 30 days
- Free-to-paid conversion failures account for 40% of churn
- Users with fewer than 10 files rarely return after week 2

### Why They Leave
- "Too complex for my needs" — 35% of exit surveys
- "Missing integrations" — 25% (especially calendar, email)
- "Pricing too high" — 20%
- "Found alternative" — 15% (Notion, Obsidian most cited)
- "Other" — 5%

### Retention Signals
- Users who create 20+ files in first week: 85% retained at 90 days
- Users who invite a teammate: 70% retained at 90 days
- Users who use search weekly: 90% retained
- API/SDK users: 95% retained (highest cohort)

## Recommendations
- Focus onboarding on getting users to 10+ files quickly
- Surface search prominently in empty-state UI
- Add lightweight integrations (calendar, bookmarks)
- Consider lower-priced solo tier to reduce pricing churn
- Invest in team features to reduce solo user proportion
""",
    "insights/user-interviews.md": """\
---
title: User Interview Synthesis — January 2026
status: final
author: research-team
quarter: Q1-2026
tags: [user-research, interviews, feedback, qualitative]
---

# User Interview Synthesis — January 2026

Summary of 15 user interviews conducted January 5-20, 2026.
Mix of power users (8), new users (4), and churned users (3).

## Common Themes

### What Users Love
- "It just works" — reliability and speed mentioned by 12/15
- Frontmatter metadata system praised by power users
- Version history saved one user from a major data loss
- API access enables custom workflows (3 users built integrations)

### Pain Points
- Onboarding is confusing — no guided tour or templates
- Search doesn't understand natural language queries
- No way to share a single file (only whole workspaces)
- Mobile access requested by 8/15 users
- Pricing confusing — unclear what each tier includes

### Feature Requests (ranked by frequency)
1. Semantic search (10/15)
2. Mobile app (8/15)
3. File sharing links (7/15)
4. Commenting on files (6/15)
5. Templates and starter content (5/15)

## Quotes
- "I moved my entire research process here. If search were better,
  I'd cancel three other subscriptions." — Power user, researcher
- "I signed up, stared at an empty workspace, and closed the tab.
  I came back a week later only because a colleague showed me." — New user
- "The API is incredible. I built a Slack bot that searches my
  workspace. More people should know about this." — Developer user

## Action Items
- Prioritize semantic search (aligns with product roadmap)
- Create onboarding templates for common use cases
- Investigate shareable file links (security implications)
- Mobile app validates demand signal from interviews
""",
    "insights/market-sizing.md": """\
---
title: TAM/SAM/SOM Analysis — Developer Workspace Tools
status: final
author: strategy-team
quarter: Q1-2026
tags: [market-sizing, TAM, strategy, competitive, analysis]
---

# TAM/SAM/SOM Analysis — Developer Workspace Tools

Market sizing for AI-native developer workspace tools.

## Total Addressable Market (TAM)
- Global knowledge management software: $48B (2025)
- Growing at 12% CAGR through 2030
- Includes: wikis, docs, note-taking, project management
- Source: Gartner, IDC reports

## Serviceable Addressable Market (SAM)
- Developer-focused knowledge tools: $8.2B
- Subset: teams with 10-500 developers
- Geographies: North America, Europe, Asia-Pacific
- Includes: Notion, Obsidian, Confluence, GitBook, README

## Serviceable Obtainable Market (SOM)
- AI-native workspace tools for dev teams: $420M
- Early-adopter segment willing to pay for agent-native tools
- Realistic capture: 2-5% in 3 years = $8.4M-$21M ARR

## Competitive Landscape
- Notion: $10B+ valuation, broad horizontal play
- Obsidian: strong in personal knowledge management
- Confluence: enterprise incumbent, losing developer mindshare
- GitBook: developer docs focus, different use case
- New entrants: Cursor (code), Pieces (snippets), Mem (AI notes)

## Our Differentiation
- Agent-native: built for AI agents, not retrofitted
- Versioned: every write creates an immutable snapshot
- Programmable: API-first with MCP server
- Open: Apache-2.0 license, no vendor lock-in
""",
    "insights/pricing-research.md": """\
---
title: Pricing Model Research and Recommendations
status: draft
author: strategy-team
quarter: Q1-2026
tags: [pricing, monetization, strategy, competitive]
---

# Pricing Model Research and Recommendations

Analysis of pricing strategies for developer tools and
recommendations for our pricing model.

## Competitive Pricing Survey

| Product | Free | Pro/Team | Business | Enterprise |
|---------|------|----------|----------|------------|
| Notion | Yes | $10/user | $18/user | Custom |
| Linear | 250 issues | $8/user | $14/user | Custom |
| Airtable | 1K records | $20/user | $45/user | Custom |
| Obsidian | Yes (local) | $50/yr (sync) | N/A | N/A |
| GitBook | Yes | $8/user | Custom | Custom |

## Pricing Models Considered

### Per-Seat Pricing
- Pros: predictable revenue, industry standard
- Cons: discourages adoption, penalizes large teams
- Best for: collaboration-heavy products

### Usage-Based Pricing
- Pros: aligns cost with value, low barrier to start
- Cons: unpredictable bills, hard to forecast revenue
- Best for: API-heavy products, infrastructure

### Hybrid (Seat + Usage)
- Pros: base revenue + growth upside
- Cons: complex to communicate, confusing tiers
- Best for: products with variable compute costs

## Recommendation
Start with **seat-based pricing** with a generous free tier:
- Free: 1 user, 100 files, 100MB storage
- Team: $12/user/month, unlimited files, 10GB storage
- Business: $25/user/month, SSO, audit logs, priority support
- Enterprise: custom pricing, SLA, dedicated support

## Key Principles
- Free tier must be genuinely useful (not crippled)
- Pricing should encourage team adoption
- Agent API calls should NOT be metered separately in V1
- Storage-based limits are more intuitive than file count limits
""",
    "insights/developer-survey.md": """\
---
title: Developer Tooling Survey Results — 2026
status: final
author: research-team
quarter: Q1-2026
tags: [developer-survey, tools, preferences, research]
---

# Developer Tooling Survey Results — 2026

Survey of 250 developers on workspace and knowledge management
tool preferences. Conducted January 2026.

## Demographics
- 60% full-stack developers
- 20% backend-focused
- 15% DevOps/infrastructure
- 5% frontend-focused
- Company size: 45% startup (<50), 30% mid-market, 25% enterprise

## Tool Usage (multiple select)
- Notion: 68%
- GitHub Issues/Projects: 55%
- Obsidian: 42%
- Confluence: 38%
- Linear: 28%
- Google Docs: 65%
- Custom internal tools: 22%

## What Developers Want
1. **Speed** — 78% rate "fast UI" as critical
2. **Search quality** — 72% unsatisfied with current search
3. **API access** — 65% want programmatic access
4. **AI features** — 58% interested in AI-powered search/writing
5. **Version history** — 55% lost work due to missing versioning
6. **Offline access** — 45% need offline capability

## Willingness to Pay
- $0 (free only): 15%
- $1-10/month: 40%
- $11-20/month: 30%
- $21-50/month: 12%
- $50+/month: 3%

## Key Insight
Developers are willing to pay for tools that save them time,
but the bar for switching is high. "10x better at one thing"
beats "2x better at everything." Our bet on agent-native
workspace with superior search could be that 10x differentiator.
""",
}

STRATEGY = {
    "strategy/go-to-market.md": """\
---
title: Go-To-Market Strategy 2026
status: active
priority: high
author: strategy-team
tags: [GTM, marketing, distribution, growth, strategy]
---

# Go-To-Market Strategy 2026

Our go-to-market approach centers on developer-led adoption with
bottom-up distribution through the open-source project.

## Distribution Channels

### Primary: Open Source + Community
- Apache-2.0 license removes adoption friction
- GitHub stars and community contributions drive awareness
- Documentation and tutorials as content marketing
- Conference talks and developer advocacy

### Secondary: MCP Server Distribution
- Claude Code integration provides built-in distribution
- Every Claude Code user is a potential sayou user
- Zero-config setup reduces activation energy
- Agent ecosystem creates network effects

### Tertiary: Content Marketing
- Technical blog posts on agent architecture
- Case studies from early adopters
- SEO for "AI workspace", "agent memory", "persistent context"
- Developer newsletter (monthly)

## Funnel Metrics
- Awareness: GitHub stars, blog views, docs traffic
- Activation: First workspace created, first 10 files written
- Retention: Weekly active workspaces, files updated
- Revenue: Free-to-paid conversion, expansion revenue
- Referral: Workspace invites, community contributions

## Year 1 Goals
- 5,000 GitHub stars
- 1,000 active workspaces
- 100 paying teams
- 10 enterprise design partners
""",
    "strategy/positioning.md": """\
---
title: Product Positioning and Messaging
status: active
priority: high
author: marketing-lead
tags: [positioning, messaging, brand, differentiation, strategy]
---

# Product Positioning and Messaging

## Positioning Statement
For development teams who need persistent context for AI agents,
Sayou is an open-source workspace that provides versioned, searchable
file storage with a developer-first API. Unlike Notion or Google Docs,
Sayou is designed from the ground up for programmatic access by both
humans and AI agents.

## Key Differentiators
1. **Agent-native**: Built for AI agents, not retrofitted
2. **Version-everything**: Every write creates an immutable snapshot
3. **API-first**: Full functionality available via Python SDK and MCP
4. **Open source**: Apache-2.0, no vendor lock-in
5. **Workspace isolation**: Multi-tenant with role-based access

## Messaging by Audience

### For Developers
"The persistent workspace for AI agents. Write files, search content,
track versions — all through a clean Python API."

### For Engineering Leaders
"Give your AI agents a workspace they can actually use. Versioned,
searchable, and auditable — built for production."

### For AI/ML Teams
"Stop losing agent context between sessions. Sayou gives your agents
persistent memory with full version history."

## Competitive Positioning
- vs. Notion: "Programmatic, not visual. Built for agents, not humans."
- vs. S3: "Structured, versioned, searchable. Not just a blob store."
- vs. Vector DBs: "Full documents with metadata, not just embeddings."
- vs. Git: "Designed for AI write patterns, not human commit patterns."
""",
    "strategy/fundraising.md": """\
---
title: Fundraising Plan — Seed Round
status: draft
priority: high
author: CEO
tags: [fundraising, seed, investors, strategy, capital]
---

# Fundraising Plan — Seed Round

Target: $3-5M seed round at $15-20M post-money valuation.
Timeline: Begin conversations Q2 2026, close Q3 2026.

## Use of Funds
- Engineering (60%): 4 additional engineers over 18 months
- Go-to-market (20%): Developer advocacy, content, events
- Infrastructure (10%): Cloud costs, security audits
- Operations (10%): Legal, accounting, office

## Investor Profile
- Developer tools specialists (Heavybit, Boldstart, Greylock)
- AI/ML focused funds (AI Grant, Conviction, Radical Ventures)
- Angel investors from developer tool companies
- Strategic: cloud providers with agent ecosystems

## Pitch Narrative
1. AI agents need persistent workspace (problem)
2. Current tools weren't built for programmatic access (gap)
3. Sayou: open-source, versioned, searchable workspace (solution)
4. MCP server gives us Claude Code distribution (traction)
5. API-first design enables platform ecosystem (vision)

## Key Metrics to Hit Before Fundraising
- 2,000+ GitHub stars (social proof)
- 500+ active workspaces (adoption)
- 5+ enterprise design partners (revenue signal)
- 3 case studies published (proof of value)
- Clear path to $1M ARR within 12 months of funding

## Risk Mitigations
- Open source de-risks technology bet for investors
- Multi-cloud support reduces platform dependency
- Workspace model proven by Notion, Obsidian success
""",
    "strategy/hiring-plan.md": """\
---
title: Hiring Plan 2026
status: draft
priority: medium
author: CEO
tags: [hiring, team, engineering, growth, strategy]
---

# Hiring Plan 2026

Team growth plan aligned with fundraising and product roadmap.

## Current Team
- 2 founders (CEO + CTO)
- 1 senior engineer
- 1 part-time designer

## Planned Hires

### Q2 2026 (Pre-funding, revenue-funded)
1. **Senior Backend Engineer** — distributed systems, databases
   - Focus: search overhaul, workspace V2 performance
   - Compensation: $180-220K + significant equity

### Q3 2026 (Post-seed)
2. **Full-Stack Engineer** — React, Python, API design
   - Focus: dashboard, analytics, admin features
   - Compensation: $160-200K + equity

3. **Developer Advocate** — writing, speaking, community
   - Focus: docs, tutorials, conference talks, community
   - Compensation: $140-170K + equity

### Q4 2026 (Post-seed)
4. **Senior Frontend Engineer** — React, performance, a11y
   - Focus: mobile app, real-time collaboration
   - Compensation: $170-210K + equity

5. **Infrastructure Engineer** — Kubernetes, AWS, monitoring
   - Focus: multi-region, self-hosted deployment, reliability
   - Compensation: $180-220K + equity

## Hiring Principles
- Remote-first, async communication
- Hire for ownership, not just execution
- Small team = every hire matters enormously
- Prioritize developer tool experience
- Diversity in background and perspective

## Recruiting Channels
- Open source contributors (warm leads)
- Developer community networks
- Technical blog attracts candidates
- Referral bonus: $5K per hire
""",
    "strategy/partnerships.md": """\
---
title: Partnership Strategy
status: active
priority: medium
author: strategy-team
tags: [partnerships, integrations, ecosystem, strategy]
---

# Partnership Strategy

Strategic partnerships to accelerate distribution and build
an integration ecosystem around the workspace platform.

## Partnership Categories

### Tier 1: AI Platform Partners
- **Anthropic**: MCP server already built, deepen relationship
- **OpenAI**: Build assistants API integration
- **Google**: Gemini tool-use integration
- Goal: become the default workspace for major AI platforms

### Tier 2: Developer Tool Integrations
- **GitHub**: Sync workspace files from repos
- **VS Code**: Extension for workspace browsing
- **Slack**: Workspace search bot
- **Linear**: Attach research to issues
- Goal: meet developers where they already work

### Tier 3: Data Source Connectors
- **Google Workspace**: Import from Docs, Sheets
- **Notion**: Migration tool and ongoing sync
- **Confluence**: Enterprise migration path
- Goal: reduce switching cost for new users

## Partnership Evaluation Criteria
1. Distribution reach (how many developers?)
2. Integration depth (API access? Co-marketing?)
3. Revenue potential (referral fees? Co-selling?)
4. Resource requirement (engineering time to build?)
5. Strategic alignment (does it reinforce our positioning?)

## Active Conversations
- Anthropic: MCP server featured in docs, exploring deeper integration
- GitHub: Early discussions about marketplace listing
- Notion: Migration tool as open-source community project

## Anti-Patterns to Avoid
- Exclusive partnerships that limit other integrations
- Revenue-share models that distort product decisions
- Partnerships requiring dedicated account management
- Integrations that expose user data to partners
""",
}


ALL_FILES = {
    **COMPETITORS,
    **TRENDS,
    **PRODUCTS,
    **INSIGHTS,
    **STRATEGY,
}


async def main() -> None:
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with Workspace(
        org_id=ORG_ID,
        user_id=USER_ID,
        database_url=DATABASE_URL,
        storage_path=str(STORAGE_PATH),
        source="seed-data",
    ) as ws:
        counts: dict[str, int] = {}

        for path, content in ALL_FILES.items():
            result = await ws.write(path, content)
            folder = path.split("/")[0]
            counts[folder] = counts.get(folder, 0) + 1
            print(f"  wrote {path}  (v{result['version_number']}, {result['size_bytes']} bytes)")

        print()
        print("Summary:")
        for folder, count in sorted(counts.items()):
            print(f"  {folder}/  {count} files")
        print(f"  total: {sum(counts.values())} files")


if __name__ == "__main__":
    asyncio.run(main())
