---
language:
  - en
license: mit
task_categories:
  - question-answering
  - text-retrieval
tags:
  - memory
  - multi-session
  - agent
  - benchmark
  - conversational
  - retrieval
  - synthetic
size_categories:
  - n<1K
---

# Sayou Agent Memory Benchmark (SAMB)

## Dataset Description

SAMB evaluates persistent memory systems for AI agents operating in professional/technical contexts. Unlike existing conversational memory benchmarks that focus on personal chitchat, SAMB tests the kinds of memory that matter for coding assistants, research tools, and productivity agents: recalling technical decisions, retrieving artifact contents (code, documents, emails), tracing reasoning across sessions, and maintaining project context over weeks.

### Key Properties

- **Multi-session**: 10 scenarios with 4-7 sessions each (62 total), simulating projects spanning 1-3 weeks
- **Artifact-rich**: Conversations produce real code, documents, emails, reports, and data — not just text
- **Diverse personas**: 10 distinct user personas varying in seniority (junior to CTO), communication style (terse to verbose), geography (London, Toronto, Berlin, Singapore, Nairobi, Sydney, Sao Paulo, Amsterdam, Seoul, Chicago), and industry (fintech, healthcare, e-commerce, edtech, logistics, legaltech, ride-sharing)
- **7 question types**: fact_recall, decision_reasoning, discovery_recall, artifact_content, cross_session, temporal, communication
- **Quality-gated generation**: Automated checks enforce naturalness (no formulaic patterns, required user pushback, human-like imperfections)

## Comparison with Prior Work

| Feature | LOCOMO | MemBench | MSC | **SAMB** |
|---------|--------|----------|-----|----------|
| Domain | Personal chitchat | General knowledge | Social chat | **Professional/technical** |
| Sessions per scenario | 1-5 | 1 | 2-5 | **4-7** |
| Artifact types | None | None | None | **Code, docs, emails, data** |
| Question types | 4 | 3 | 2 | **7** |
| Persona diversity | Limited | None | Crowdsourced | **10 distinct personas** |
| Quality gates | Manual | Manual | Crowdsource QA | **Automated + manual** |
| Decision reasoning | No | No | No | **Yes** |
| Cross-session questions | Limited | No | No | **Yes (multi-hop)** |
| Temporal questions | No | No | No | **Yes** |

## Dataset Structure

### Scenarios by Category

| Category | Scenarios | Sessions | QA Pairs |
|----------|-----------|----------|----------|
| **Build** | 01-build-auth-system, 07-design-data-pipeline | 13 | 32 |
| **Investigate** | 02-investigate-user-churn, 08-cloud-migration-research | 13 | 26 |
| **Communicate** | 03-product-launch-emails, 04-quarterly-business-review | 12 | 25 |
| **Operate** | 05-setup-cicd-pipeline, 06-production-incident-response | 11 | 22 |
| **Plan** | 09-monolith-to-microservices, 10-feature-scoping-estimation | 13 | 26 |

### QA Pair Types

| Type | Count | Description |
|------|-------|-------------|
| fact_recall | ~35 | Direct factual questions (e.g., "What library was used?") |
| decision_reasoning | ~25 | Why was a particular choice made? |
| artifact_content | ~25 | Questions about code, documents, or email content |
| cross_session | ~18 | Questions requiring info from 2+ sessions |
| discovery_recall | ~12 | What was discovered during investigation? |
| temporal | ~10 | Questions about timing and ordering of events |
| communication | ~6 | What was communicated to stakeholders? |

### Difficulty Levels

| Difficulty | Count | Description |
|------------|-------|-------------|
| single-hop | ~60 | Answer found in one session, one fact |
| detail | ~35 | Answer requires specific details (numbers, lists) |
| multi-hop | ~36 | Answer requires synthesizing information across sessions |

## File Format

Each generated scenario is a JSON file:

```json
{
  "scenario_id": "scenario-01",
  "title": "Build User Authentication for a Web App",
  "domain": "software-engineering",
  "category": "build",
  "description": "...",
  "persona": {
    "role": "Senior backend engineer, 5 years experience",
    "communication_style": "concise and direct...",
    "quirks": ["types fast with occasional typos", "..."],
    "context": "Series B fintech startup in London..."
  },
  "sessions": [
    {
      "id": "s1",
      "day": 1,
      "time": null,
      "user_request": "...",
      "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
      ]
    }
  ],
  "qa_pairs": [
    {
      "question": "What password hashing library does the auth system use?",
      "answer": "bcrypt v5.1.0",
      "evidence_sessions": ["s1"],
      "type": "fact_recall",
      "difficulty": "single-hop"
    }
  ]
}
```

## Evaluation Protocol

### Memory System Evaluation

1. **Ingest**: Feed all sessions from a scenario into the memory system sequentially
2. **Query**: For each QA pair, query the memory system with the question
3. **Score**: Compare retrieved answer against ground truth using:
   - **Exact match** for fact_recall questions with short answers
   - **Semantic similarity** (embedding cosine similarity > 0.8) for longer answers
   - **Key term recall** for detail and multi-hop questions

### Metrics

- **QA Accuracy**: % of questions answered correctly (overall and per-type)
- **Evidence Retrieval Precision**: Does the system retrieve the correct evidence sessions?
- **Cross-session Accuracy**: Accuracy on multi-hop questions specifically
- **Latency**: Time to retrieve answers (P50, P95)

## Limitations

1. **Synthetic data**: Conversations are LLM-generated, not recorded from real users. Despite quality gates and persona diversity, some patterns may not fully capture human communication.
2. **English only**: All scenarios are in English. Multilingual memory evaluation is not covered.
3. **Professional domain**: Focuses on technical/business contexts. Does not cover personal, creative, or academic scenarios.
4. **Scale**: 10 scenarios is sufficient for system-level evaluation but may not support fine-grained statistical comparisons across all 7 question types.
5. **Single-user**: All scenarios feature one user. Multi-user collaboration scenarios are not included.

## Citation

If you use this dataset, please cite:

```bibtex
@misc{samb2026,
  title={SAMB: Sayou Agent Memory Benchmark},
  author={Pixell Team},
  year={2026},
  url={https://github.com/pixell-global/sayou}
}
```
