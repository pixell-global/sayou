"""LLM-based answer generation and judging."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# LLM client (reuses pattern from benchmarks/generate.py)
# ---------------------------------------------------------------------------


def _get_openai_key() -> str | None:
    """Get OpenAI API key from environment or .env file."""
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("SAYOU_AGENT_OPENAI_API_KEY")
    if key:
        return key
    # Try loading from .env file
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("OPENAI_API_KEY", "SAYOU_AGENT_OPENAI_API_KEY"):
                    return v.strip()
    return None


@dataclass
class LLMClient:
    """Thin async wrapper around OpenAI."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    _client: Any = field(default=None, repr=False)

    def __post_init__(self):
        import openai
        api_key = _get_openai_key()
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def generate(self, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=self.temperature,
        )
        return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ANSWER_SYSTEM_PROMPT = """\
You are answering a question using ONLY the context provided.
If the context does not contain enough information, say \
"Insufficient context to answer."

Answer concisely, citing specific facts from the context."""

ANSWER_USER_TEMPLATE = """\
CONTEXT:
{context}

QUESTION: {question}"""

JUDGE_SYSTEM_PROMPT = """\
You are evaluating a generated answer against a reference answer.

## Scoring Rubric

3 — COMPLETE: Contains ALL key facts from the reference. May use different \
wording but captures every important detail.
2 — PARTIAL: Contains MOST key facts (>50%) but misses some specific \
details, numbers, or entities.
1 — MINIMAL: Contains at most one relevant fact, or is vaguely related \
but missing most specifics.
0 — WRONG: Factually incorrect, irrelevant, or says "insufficient context" \
when the information was available. Also score 0 if the answer \
addresses a completely different topic.

## Calibration Examples

Example 1:
  Question: "What password hashing library was chosen?"
  Reference: "bcrypt v5.1.0, chosen over Argon2 due to wider ecosystem support"
  Answer: "bcrypt was selected for password hashing"
  Score: 2 (correct library but missing version and reasoning)

Example 2:
  Question: "What caused the slow login?"
  Reference: "N+1 query in user permission loading plus a missing index on user_roles.user_id"
  Answer: "There was a database performance issue"
  Score: 1 (vaguely related but no specifics)

Example 3:
  Question: "How many API endpoints were documented?"
  Reference: "8 REST endpoints covering auth, users, roles, and health"
  Answer: "The API documentation covered 8 endpoints including authentication, \
user management, role management, and health checks"
  Score: 3 (all key facts present)

## Your Task

First, list the key facts in the reference answer.
Then, check which key facts appear in the generated answer.
Finally, assign a score.

Output ONLY valid JSON: {"key_facts": [...], "matched": [...], "missing": [...], \
"score": <0-3>, "reasoning": "<1 sentence>"}"""

JUDGE_USER_TEMPLATE = """\
QUESTION: {question}
REFERENCE ANSWER: {reference}
GENERATED ANSWER: {answer}"""


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------


async def generate_answer(client: LLMClient, question: str, context: str) -> str:
    """Generate an answer to a question given retrieved context."""
    if not context.strip():
        return "Insufficient context to answer."

    user_msg = ANSWER_USER_TEMPLATE.format(context=context, question=question)
    return await client.generate(ANSWER_SYSTEM_PROMPT, user_msg, max_tokens=512)


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------


@dataclass
class JudgeScore:
    """Parsed judge output."""

    score: int
    key_facts: list[str]
    matched: list[str]
    missing: list[str]
    reasoning: str


async def judge_answer(
    client: LLMClient,
    question: str,
    reference: str,
    answer: str,
) -> JudgeScore:
    """Score a generated answer against the reference using the LLM judge."""
    user_msg = JUDGE_USER_TEMPLATE.format(
        question=question,
        reference=reference,
        answer=answer,
    )
    raw = await client.generate(JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=1024)
    return _parse_judge_response(raw)


def _parse_judge_response(raw: str) -> JudgeScore:
    """Parse the judge's JSON output, with fallback for malformed responses."""
    text = raw.strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        match = re.search(r'\{[^{}]*"score"\s*:\s*\d[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return _fallback_score(text)
        else:
            return _fallback_score(text)

    score = data.get("score", 0)
    if not isinstance(score, int) or score < 0 or score > 3:
        score = max(0, min(3, int(score))) if isinstance(score, (int, float)) else 0

    return JudgeScore(
        score=score,
        key_facts=data.get("key_facts", []),
        matched=data.get("matched", []),
        missing=data.get("missing", []),
        reasoning=data.get("reasoning", ""),
    )


def _fallback_score(text: str) -> JudgeScore:
    """Extract score from non-JSON response as a last resort."""
    # Look for "Score: N" or "score: N" patterns
    match = re.search(r'[Ss]core[:\s]+(\d)', text)
    score = int(match.group(1)) if match else 0
    score = max(0, min(3, score))

    return JudgeScore(
        score=score,
        key_facts=[],
        matched=[],
        missing=[],
        reasoning=f"[parse fallback] {text[:200]}",
    )


# ---------------------------------------------------------------------------
# Binary judge (LOCOMO — industry-standard CORRECT/WRONG)
# ---------------------------------------------------------------------------

BINARY_JUDGE_SYSTEM_PROMPT = """\
You are evaluating whether a generated answer is correct given a reference answer.

Judge CORRECT if the generated answer captures the essential meaning of the \
reference answer. Minor wording differences are acceptable. The answer does NOT \
need to be word-for-word identical — it just needs to convey the same key facts.

Judge WRONG if:
- The answer is factually incorrect
- The answer misses the main point of the reference
- The answer says "insufficient context" or similar when the reference has substance
- The answer addresses a different topic

Output ONLY valid JSON: {"verdict": "CORRECT" or "WRONG", "reasoning": "<1 sentence>"}"""

BINARY_JUDGE_USER_TEMPLATE = """\
QUESTION: {question}
REFERENCE ANSWER: {reference}
GENERATED ANSWER: {answer}"""


@dataclass
class BinaryJudgeResult:
    """Result from binary (CORRECT/WRONG) judging."""

    correct: bool
    reasoning: str


async def judge_answer_binary(
    client: LLMClient,
    question: str,
    reference: str,
    answer: str,
) -> BinaryJudgeResult:
    """Binary CORRECT/WRONG judge for LOCOMO evaluation."""
    user_msg = BINARY_JUDGE_USER_TEMPLATE.format(
        question=question, reference=reference, answer=answer,
    )
    raw = await client.generate(BINARY_JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=256)
    return _parse_binary_response(raw)


def _parse_binary_response(raw: str) -> BinaryJudgeResult:
    """Parse binary judge JSON output."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'"verdict"\s*:\s*"(CORRECT|WRONG)"', text)
        if match:
            return BinaryJudgeResult(
                correct=match.group(1) == "CORRECT",
                reasoning="[parsed from partial JSON]",
            )
        # Fallback: look for CORRECT/WRONG in text
        correct = "CORRECT" in text.upper() and "WRONG" not in text.upper()
        return BinaryJudgeResult(correct=correct, reasoning=f"[parse fallback] {text[:200]}")

    verdict = data.get("verdict", "WRONG").upper()
    return BinaryJudgeResult(
        correct=verdict == "CORRECT",
        reasoning=data.get("reasoning", ""),
    )


# ---------------------------------------------------------------------------
# Task context judge (1-5 holistic score)
# ---------------------------------------------------------------------------

TASK_JUDGE_SYSTEM_PROMPT = """\
Rate how useful the retrieved context is for completing this task.

5 — COMPLETE: Context provides everything needed — all relevant decisions, \
constraints, prior work, and specifics. Agent could complete the task immediately.
4 — MOSTLY COMPLETE: Has most key context but missing some details the agent \
would need to look up.
3 — PARTIAL: Has some relevant information but significant gaps. Agent would \
need to ask clarifying questions.
2 — THIN: Only surface-level context. Agent would essentially be starting from \
scratch on key aspects.
1 — USELESS: Context is irrelevant to the task or empty.

Output ONLY valid JSON: {"score": <1-5>, "reasoning": "<1-2 sentences>"}"""

TASK_JUDGE_USER_TEMPLATE = """\
TASK: {question}

RETRIEVED CONTEXT:
{context}"""


@dataclass
class TaskJudgeResult:
    """Result from task context judging (1-5 holistic + evidence coverage)."""

    holistic_score: int  # 1-5
    reasoning: str
    evidence_found: list[str]
    evidence_missing: list[str]
    coverage_pct: float  # 0.0-1.0


async def judge_task_context(
    client: LLMClient,
    question: str,
    context: str,
) -> tuple[int, str]:
    """Judge how useful retrieved context is for a task (1-5)."""
    user_msg = TASK_JUDGE_USER_TEMPLATE.format(question=question, context=context)
    raw = await client.generate(TASK_JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=256)
    return _parse_task_score(raw)


def _parse_task_score(raw: str) -> tuple[int, str]:
    """Parse task judge response, return (score, reasoning)."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        score = int(data.get("score", 1))
        score = max(1, min(5, score))
        return score, data.get("reasoning", "")
    except (json.JSONDecodeError, ValueError):
        match = re.search(r'[Ss]core[:\s]+(\d)', text)
        score = int(match.group(1)) if match else 1
        score = max(1, min(5, score))
        return score, f"[parse fallback] {text[:200]}"


# ---------------------------------------------------------------------------
# Evidence coverage judge (per-item FOUND/MISSING)
# ---------------------------------------------------------------------------

EVIDENCE_JUDGE_SYSTEM_PROMPT = """\
Given retrieved context and a list of required evidence items, check which items \
are present in the context. For each item, respond FOUND if the context contains \
that information (exact wording not required — semantic match is sufficient) \
or MISSING if it does not.

Output ONLY valid JSON: {"items": [{"item": "<evidence text>", "found": true/false}]}"""

EVIDENCE_JUDGE_USER_TEMPLATE = """\
REQUIRED EVIDENCE ITEMS:
{items_text}

RETRIEVED CONTEXT:
{context}"""


async def judge_evidence_coverage(
    client: LLMClient,
    required_evidence: list[str],
    context: str,
) -> tuple[list[str], list[str], float]:
    """Check which evidence items appear in context.

    Returns:
        (found_items, missing_items, coverage_pct)
    """
    items_text = "\n".join(f"- {item}" for item in required_evidence)
    user_msg = EVIDENCE_JUDGE_USER_TEMPLATE.format(
        items_text=items_text, context=context,
    )
    raw = await client.generate(EVIDENCE_JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=1024)
    return _parse_evidence_response(raw, required_evidence)


def _parse_evidence_response(
    raw: str, required_evidence: list[str],
) -> tuple[list[str], list[str], float]:
    """Parse evidence coverage response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    found: list[str] = []
    missing: list[str] = []

    try:
        data = json.loads(text)
        items = data.get("items", [])
        for entry in items:
            item_text = entry.get("item", "")
            if entry.get("found", False):
                found.append(item_text)
            else:
                missing.append(item_text)
    except json.JSONDecodeError:
        # Fallback: count all as missing
        missing = list(required_evidence)

    total = len(required_evidence)
    coverage = len(found) / total if total > 0 else 0.0
    return found, missing, coverage
