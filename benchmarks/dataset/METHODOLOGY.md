# Generation Methodology

This document describes how the Sayou Agent Memory Benchmark (SAMB) dataset was created, including design decisions, generation pipeline, quality assurance, and known limitations.

## 1. Scenario Design

### Category Framework

We identified 5 categories of agent-assisted work that require persistent memory:

| Category | Description | Why memory matters |
|----------|-------------|-------------------|
| **Build** | Implementing features over multiple sessions | Decisions compound: auth choices affect all later code |
| **Investigate** | Analyzing data or debugging over time | Findings from early sessions inform later analysis |
| **Communicate** | Drafting, iterating, and tracking communications | Prior drafts, feedback, and metrics inform revisions |
| **Operate** | Incident response, CI/CD, infrastructure work | Root cause analysis depends on recalling system state |
| **Plan** | Architecture, estimation, roadmapping | Scope changes reference original estimates and constraints |

Each category has 2 scenarios (10 total), ensuring balanced coverage.

### Scenario Outline Structure

Each scenario outline is a hand-authored YAML file defining:

- **Metadata**: Title, domain, category, persona
- **Sessions**: 4-7 sessions per scenario, each specifying:
  - User request (what they want help with)
  - Conversation topics (themes to cover)
  - Decisions (choices made, with reasoning and alternatives)
  - Discoveries (findings, with detail)
  - Artifacts (code, documents, emails, data — with key facts)
  - Entities (tools, libraries, services mentioned)
  - Build dependencies (which prior sessions this builds on)
- **QA pairs**: 8-16 questions per scenario covering 7 types

The outlines define *what* must be discussed but not *how* the conversation unfolds. This separation allows the LLM to generate natural conversation flow while ensuring all required content is present.

### Depth Over Breadth

We chose 10 deep scenarios (62 sessions, 131 QA pairs) rather than 100 shallow ones. Rationale:

1. **Real work is deep**: A developer doesn't have 100 unrelated 2-message chats. They have 5-10 projects with 5-7 sessions each, where context compounds.
2. **Cross-session questions require depth**: Testing whether a system can connect decisions from session 1 to consequences in session 5 requires scenarios that span multiple sessions.
3. **Artifact quality requires length**: Generating realistic code, documents, and emails requires multi-turn conversations with enough context for the artifacts to be substantive.

## 2. Persona Design

Each scenario has a distinct user persona to ensure diversity across:

| Dimension | Range | Examples |
|-----------|-------|---------|
| **Seniority** | Junior to CTO | 1.5yr junior engineer, 12yr CTO |
| **Communication style** | Terse to verbose | Sentence fragments ↔ structured paragraphs |
| **Industry** | 7 industries | Fintech, healthcare, e-commerce, edtech, logistics, legaltech, ride-sharing |
| **Geography** | 10 cities on 6 continents | London, Toronto, Berlin, Singapore, Nairobi, Sydney, Sao Paulo, Amsterdam, Seoul, Chicago |
| **Behavioral quirks** | Unique per persona | Typos, abbreviations, emoji, consulting jargon, one-word follow-ups |

### Why Personas Matter

Without personas, LLM-generated conversations converge to a homogeneous tone — every user sounds like a polite mid-level engineer at a Silicon Valley startup. Personas provide concrete constraints:

- A junior engineer asks "why?" more and admits confusion
- A CTO sends terse one-word follow-ups and references "the board"
- An on-call engineer at 2 AM skips capitalization entirely
- A consultant uses "LTV:CAC" and "rule of 40" naturally

## 3. Generation Pipeline

### Overview

```
Scenario Outlines (YAML)
    ↓
generate.py (GPT-4o, temp=0.8)
    ↓
Quality Gate (automated checks)
    ↓  ← retry up to 3x if failed
Generated Conversations (JSON)
    ↓
validate_qa.py (QA validation)
    ↓
quality_metrics.py (corpus metrics)
```

### System Prompt Design

The generation system prompt was iteratively designed to address specific quality issues observed in initial generations:

| Issue | Prompt Instruction | Quality Gate Check |
|-------|-------------------|-------------------|
| Every user opens with "Hey" | "Do NOT start with greetings — jump straight into the topic" | First user message checked for forbidden openings |
| User always agrees | "In at least ONE turn, the user must disagree or question" | Pushback indicators checked |
| Assistant is formulaic | 19 forbidden phrases listed explicitly | Exact phrase matching |
| No human messiness | "Include at least ONE typo, abbreviation, or incomplete thought" | Imperfection indicators checked |
| Identical tone | "Tone matches context — 2 AM incident ≠ marketing planning" | Persona block enforced |
| Missing artifacts | "EVERY artifact specified in the outline MUST appear" | Key facts checked against assistant text |
| No session continuity | "Reference previous work at least once" | Continuity phrases checked in non-first sessions |

### Quality Gate

Each generated session passes through an automated quality gate before acceptance:

1. **Forbidden phrase check**: 19 robotic phrases (e.g., "Absolutely!", "Happy to help") cause rejection
2. **Opening check**: First user message must not start with "Hey", "Hi", or "Hello"
3. **Pushback check**: At least one user message must contain disagreement/questioning indicators
4. **Imperfection check**: At least one user message must contain typos, abbreviations, or self-corrections
5. **Artifact completeness**: Code artifacts must have code fences; at least 50% of key facts must appear
6. **Session continuity**: Non-first sessions must reference prior work

Sessions failing the gate are regenerated up to 3 times. After 3 retries, the best attempt is kept with issues logged.

### LLM Configuration

- **Model**: GPT-4o (or Claude Sonnet 4.5 via `--provider anthropic`)
- **Temperature**: 0.8 (higher than default to encourage diversity)
- **Max tokens**: 8,192 per session
- **Sessions generated sequentially** within each scenario (for context continuity)

## 4. QA Pair Design

### Type Taxonomy

| Type | What it tests | Example |
|------|---------------|---------|
| **fact_recall** | Can the system retrieve a specific fact? | "What password hashing library was used?" → "bcrypt v5.1.0" |
| **decision_reasoning** | Can it explain *why* a choice was made? | "Why JWT over sessions?" → "Frontend is a React SPA on CDN, needs stateless auth" |
| **discovery_recall** | Can it recall what was found during investigation? | "What caused the slow login?" → "N+1 query + missing index" |
| **artifact_content** | Can it retrieve details from generated artifacts? | "How many API endpoints are documented?" → "8 endpoints" |
| **cross_session** | Can it connect information across sessions? | "How does password reset send emails?" → "Uses SendGrid from session 2" |
| **temporal** | Can it reason about timing/ordering? | "What was worked on in the second week?" → "Password reset, docs, client email" |
| **communication** | Can it recall what was communicated to stakeholders? | "What next steps were recommended?" → "Rate limiting, OAuth social login" |

### Difficulty Levels

- **single-hop**: Answer is a direct fact from one session
- **detail**: Answer requires remembering specific numbers, lists, or configurations
- **multi-hop**: Answer requires combining information from 2+ sessions

### Validation

QA pairs are validated against generated conversations using `validate_qa.py`:
- Key terms and numbers from the expected answer are checked against evidence session text
- A QA pair passes if >= 40% of key terms are found (lenient threshold because LLMs rephrase)
- Failed QA pairs indicate the generated conversation diverged from the outline

## 5. Quality Metrics

### Corpus-Level Metrics

Computed by `quality_metrics.py`:

| Metric | What it measures | Target |
|--------|-----------------|--------|
| **Distinct-1** | Unique unigrams / total unigrams | > 0.4 |
| **Distinct-2** | Unique bigrams / total bigrams | > 0.6 |
| **Self-BLEU** | Average BLEU of each text against all others | < 0.3 |
| **Opening diversity** | % unique first-5-words across user openings | > 80% |
| **Forbidden phrases** | Count of robotic phrases in assistant messages | 0 |

### Why These Metrics

- **Distinct-N** (Li et al., 2016): Standard measure of lexical diversity in dialogue. Low Distinct-N indicates the LLM is reusing the same phrases.
- **Self-BLEU** (Zhu et al., 2018): Measures intra-corpus similarity. High Self-BLEU means conversations sound too similar to each other.
- **Opening diversity**: A custom metric addressing a specific failure mode we observed — LLMs tend to start every conversation the same way.

## 6. Known Limitations

1. **Synthetic bias**: Despite quality gates, LLM-generated conversations may still exhibit subtle patterns that distinguish them from real human-AI interactions. The quality gates address the most egregious patterns but cannot guarantee full naturalness.

2. **Persona adherence is approximate**: The LLM may not perfectly maintain persona quirks throughout long conversations. A "terse" persona might occasionally write long messages.

3. **Artifact realism**: Code artifacts are syntactically realistic but not tested for correctness (they won't compile/run). Documents and emails are plausible but may contain generic phrasing.

4. **QA pair completeness**: The 131 QA pairs do not exhaustively cover every fact in the conversations. Some details are only testable through the QA pairs we designed.

5. **English only**: All personas, scenarios, and conversations are in English. Cultural and linguistic diversity is limited to geographic context, not language.

6. **Single evaluator**: Scenario outlines and QA pairs were designed by a small team. Inter-annotator agreement has not been measured.

## 7. Reproducibility

To regenerate the dataset:

```bash
# Install dependencies
pip install openai pyyaml

# Generate all scenarios
OPENAI_API_KEY=sk-... python -m benchmarks.generate

# Validate QA pairs
python -m benchmarks.validate_qa

# Compute quality metrics
python -m benchmarks.quality_metrics
```

Note: Due to LLM stochasticity (temperature=0.8), regenerated conversations will differ from the published version. Quality gate pass rates and metric scores should be similar but not identical.
