# Datasheet: Sayou Agent Memory Benchmark

Following the framework from [Gebru et al. (2021), "Datasheets for Datasets"](https://arxiv.org/abs/1803.09010).

## 1. Motivation

### For what purpose was the dataset created?

This dataset was created to evaluate persistent memory systems for AI coding and productivity assistants. Existing benchmarks (LOCOMO, MemBench, MSC) focus on personal chitchat or single-session dialogue. They do not test the kinds of memory that matter for agent systems: remembering technical decisions, recalling artifact contents, tracing reasoning across multi-session projects, and maintaining context over weeks of collaborative work.

### Who created the dataset and on behalf of which entity?

The dataset was created by the Sayou team at Pixell as part of developing and evaluating the Sayou workspace memory system.

### Who funded the creation of the dataset?

Pixell funded the dataset creation. LLM generation costs (OpenAI GPT-4o) were the primary expense.

### Any other comments?

The dataset is designed to be system-agnostic — it evaluates memory retrieval capabilities regardless of the underlying storage or retrieval mechanism.

## 2. Composition

### What do the instances that comprise the dataset represent?

Each instance is a **scenario**: a multi-session conversation between a human user and an AI assistant, simulating a realistic work project. A scenario contains:

- **Metadata**: ID, title, domain, category, persona
- **Sessions** (4-7 per scenario): Each session contains a multi-turn conversation (6-15 messages) with user requests, assistant responses, code artifacts, documents, and emails
- **QA pairs** (8-16 per scenario): Questions that test memory retrieval, with ground-truth answers and evidence session references

### How many instances are there in total?

| Metric | Count |
|--------|-------|
| Scenarios | 10 |
| Sessions | 62 |
| QA pairs | 131 |
| Total messages | ~500 |

### What data does each instance consist of?

Conversations in JSON format with `role` (user/assistant) and `content` fields. Content includes natural language, code blocks (Python, JavaScript, SQL, YAML, Terraform), document artifacts (emails, reports, RFCs, post-mortems), and data artifacts (metrics, performance results).

### Is there a label or target associated with each instance?

Yes. Each scenario includes QA pairs with:
- `question`: A natural-language question about the conversation
- `answer`: The ground-truth answer
- `evidence_sessions`: Which sessions contain the evidence
- `type`: Category (fact_recall, decision_reasoning, discovery_recall, artifact_content, cross_session, temporal, communication)
- `difficulty`: single-hop, detail, or multi-hop

### Is any information missing from individual instances?

Some sessions may not have all optional fields (time-of-day, entities, builds_on references). This is intentional — not all sessions have time constraints or entity references.

### Are there recommended data splits?

No predefined train/test splits. The dataset is designed for evaluation only, not training. We recommend using all 10 scenarios for evaluation and reporting per-scenario and per-category scores.

### Does the dataset contain data that might be considered confidential?

No. All conversations are synthetic. Company names, people, and technical details are fictional.

### Does the dataset contain data that, if viewed directly, might be offensive?

No. The conversations are professional workplace interactions.

## 3. Collection Process

### How was the data associated with each instance acquired?

The data was generated through a two-stage pipeline:

1. **Human-authored scenario outlines** (YAML): Domain experts wrote detailed outlines specifying session structure, decisions, discoveries, artifact specifications, and QA pairs. Each outline defines the conversation's content but not its exact wording.

2. **LLM-generated conversations** (JSON): GPT-4o generated realistic multi-turn conversations from the outlines, guided by per-scenario persona definitions and strict quality constraints.

### What mechanisms or procedures were used to collect the data?

- Scenario outlines were written in YAML following a structured schema
- Each scenario includes a `persona` block defining the user's communication style, quirks, and work context
- Generation uses a detailed system prompt that forbids robotic patterns (e.g., "Absolutely!", "Sounds good") and requires human-like imperfections (typos, abbreviations, pushback)
- An automated quality gate checks each generated session for:
  - Forbidden phrases in assistant responses
  - Formulaic opening patterns
  - Presence of user pushback/disagreement
  - Human imperfections (typos, abbreviations)
  - Artifact completeness
  - Cross-session continuity references
- Sessions failing the quality gate are regenerated (up to 3 retries)

### Who was involved in the data collection process?

Scenario outlines were authored by the Sayou development team. Conversation generation was performed by GPT-4o. Quality validation was automated with manual spot-checks.

### Over what timeframe was the data collected?

February 2026.

### Were any ethical review processes conducted?

The dataset contains only synthetic professional conversations. No human subjects were involved.

## 4. Preprocessing / Cleaning / Labeling

### Was any preprocessing applied to the data?

- Generated conversations are validated against a quality gate before acceptance
- QA pairs are validated to ensure answers are supported by evidence sessions
- Quality metrics (Distinct-N, Self-BLEU, opening diversity) are computed to verify corpus-level diversity

### Was the "raw" data saved in addition to the preprocessed data?

Scenario outlines (YAML) and generated conversations (JSON) are both preserved. The outlines serve as the ground-truth specification; the conversations are the generated output.

### Is the software used to preprocess the data available?

Yes. The generation script (`benchmarks/generate.py`), validation script (`benchmarks/validate_qa.py`), and metrics script (`benchmarks/quality_metrics.py`) are all included in the repository.

## 5. Uses

### Has the dataset been used for any tasks already?

The dataset is designed to evaluate the Sayou workspace memory system and compare it against alternative memory approaches.

### What (other) tasks could the dataset be used for?

- Evaluating any persistent memory or RAG system for conversational AI
- Benchmarking long-context retrieval in multi-session settings
- Testing cross-session reasoning capabilities
- Evaluating artifact recall (code, documents, emails)

### Is there anything about the composition of the dataset that might impact future uses?

- The dataset focuses on **professional/technical** conversations. It would not be appropriate for evaluating personal or social chatbot memory.
- Scenarios are English-only.
- The 10 scenarios cover 5 categories (build, investigate, communicate, operate, plan) but are not exhaustive of all possible work patterns.

### Are there tasks for which the dataset should not be used?

- **Training LLMs**: The dataset is too small and specific for pre-training or fine-tuning language models.
- **Evaluating factual knowledge**: The conversations contain fictional technical details (fake company names, made-up metrics). They test memory retrieval, not factual accuracy.

## 6. Distribution

### Will the dataset be distributed to third parties outside of the entity on behalf of which the dataset was created?

Yes. The dataset will be publicly released.

### How will the dataset be distributed?

Via the Sayou GitHub repository and potentially Hugging Face Datasets.

### When will the dataset be distributed?

With the v0.3.0 release of Sayou.

### Will the dataset be distributed under a copyright or other intellectual property (IP) license?

MIT License, consistent with the Sayou project.

### Have any third parties imposed IP-based or other restrictions on the data?

No.

## 7. Maintenance

### Who will be supporting/hosting/maintaining the dataset?

The Sayou team at Pixell.

### How can the owner/curator/manager of the dataset be contacted?

Via the Sayou GitHub repository issues.

### Will the dataset be updated?

Yes. We plan to:
- Add scenarios covering additional domains (legal, scientific, creative)
- Add non-English scenarios
- Expand QA pair coverage for under-represented question types
- Update generation quality based on community feedback

### If others want to extend/augment/build on/contribute to the dataset, is there a mechanism for them to do so?

Yes. The scenario outline format is documented, and the generation pipeline is open-source. Contributors can add new scenarios by creating YAML outlines following the existing schema.
