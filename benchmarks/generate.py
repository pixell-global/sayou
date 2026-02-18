"""
Generate full conversation dataset from scenario outlines.

Usage:
    # With OpenAI (default)
    OPENAI_API_KEY=sk-... python -m benchmarks.generate

    # With Anthropic
    ANTHROPIC_API_KEY=sk-ant-... python -m benchmarks.generate --provider anthropic

    # Generate a single scenario
    python -m benchmarks.generate --scenario 01

    # Dry run (show what would be generated)
    python -m benchmarks.generate --dry-run

    # Skip quality gate (faster, for iteration)
    python -m benchmarks.generate --skip-quality-gate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCENARIOS_DIR = Path(__file__).parent / "dataset" / "scenarios"
OUTPUT_DIR = Path(__file__).parent / "dataset" / "generated"

MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# LLM client abstraction
# ---------------------------------------------------------------------------

@dataclass
class LLMClient:
    provider: str  # "openai" or "anthropic"
    model: str = ""
    _client: Any = field(default=None, repr=False)

    def __post_init__(self):
        if self.provider == "openai":
            import openai
            self.model = self.model or "gpt-4o"
            self._client = openai.AsyncOpenAI()
        elif self.provider == "anthropic":
            import anthropic
            self.model = self.model or "claude-sonnet-4-5-20250929"
            self._client = anthropic.AsyncAnthropic()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def generate(self, system: str, user: str, max_tokens: int = 8192) -> str:
        if self.provider == "openai":
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=0.8,
            )
            return resp.choices[0].message.content or ""
        else:
            resp = await self._client.messages.create(
                model=self.model,
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=0.8,
            )
            return resp.content[0].text


# ---------------------------------------------------------------------------
# Forbidden phrases — patterns that make conversations sound robotic
# ---------------------------------------------------------------------------

FORBIDDEN_PHRASES = [
    "Sounds good",
    "Looks good",
    "You're welcome",
    "Absolutely!",
    "Great idea",
    "Great question",
    "That's a great",
    "Let me know if you need anything",
    "Let me know if you have any",
    "Feel free to",
    "Happy to help",
    "No problem!",
    "Of course!",
    "I'd be happy to",
    "I'm happy to",
    "Perfect!",
    "Excellent!",
    "Wonderful!",
    "Fantastic!",
]

# Openings that are too common — checked only for the first user message
FORBIDDEN_OPENINGS = [
    "Hey,",
    "Hey!",
    "Hey ",
    "Hi,",
    "Hi!",
    "Hello,",
    "Hello!",
]


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SESSION_SYSTEM_PROMPT = """\
You are generating a realistic multi-turn conversation between a human user and an AI \
assistant. This conversation is for a benchmark dataset evaluating AI memory systems, \
so authenticity is critical.

## PERSONA
The user has a specific communication style defined by their persona. You MUST write \
the user's messages to match this persona exactly — their vocabulary, sentence length, \
use of abbreviations, level of formality, and behavioral quirks. The persona is NOT \
optional flavor text; it is the primary constraint on how the user speaks.

## NATURALNESS REQUIREMENTS

The conversation must feel like a real Slack DM or chat session, not a screenplay:

1. **Varied openings**: The user does NOT start with greetings like "Hey", "Hi", or \
"Hello". They jump straight into their request, question, or context. Examples of good \
openings: "so I've been looking at the auth setup and...", "quick q about the deploy", \
"need to figure out the email verification flow", "remember that perf issue from last week?"

2. **User pushback**: In at least ONE turn, the user must disagree, question the \
assistant's suggestion, express doubt, propose an alternative, or say something like \
"wait, why not just X?" or "that seems over-engineered" or "I'm not sure about that". \
The assistant should respond constructively — sometimes conceding, sometimes explaining why.

3. **Human imperfections**: Include at least ONE of these per conversation:
   - A typo or autocorrect error (e.g., "teh", "adn", "recieve")
   - An abbreviation (e.g., "tbh", "imo", "prob", "rn", "lmk", "nvm")
   - An incomplete thought that gets corrected ("we should — actually wait, let me think")
   - A mid-sentence topic shift

4. **No robotic assistant language**: The assistant must NEVER use these phrases:
   - "Absolutely!", "Great question!", "Great idea!", "That's a great..."
   - "Happy to help!", "I'd be happy to", "Feel free to"
   - "Let me know if you need anything", "Let me know if you have any questions"
   - "You're welcome", "No problem!", "Of course!", "Perfect!", "Excellent!"
   - "Wonderful!", "Fantastic!", "Sounds good!"
   Instead, the assistant should respond naturally: "Yeah, that works", "Here's what I'd do", \
"So the tricky part is...", "One thing to watch out for...", "Hmm, that depends on..."

5. **No performative agreement**: The user should NOT respond to every suggestion with \
approval ("Sounds good", "Looks good", "Perfect", "Great"). Instead they should \
sometimes just move on to the next question, ask a follow-up, or challenge the approach.

6. **Tone matches context**: A 2 AM incident response sounds different from a product \
planning session. Match urgency, formality, and pacing to the scenario. Late-night \
debugging is terse and urgent. Planning sessions have longer messages with more back-and-forth.

7. **Session continuity**: If this is NOT the first session, the user should naturally \
reference previous work at least once — "remember when we decided X?", "building on \
that auth middleware from last time", "so after the perf fix we did...". Do NOT \
re-introduce context the assistant already knows.

## ARTIFACTS
- Code blocks must be COMPLETE — real imports, real function names, realistic logic
- Documents must have real sentences and numbers, not placeholder text
- Emails must sound like a real person wrote them
- EVERY artifact specified in the outline MUST appear in the conversation
- Never truncate with "..." or "// rest of implementation"

## OUTPUT FORMAT
A JSON array of message objects: [{"role": "user"|"assistant", "content": "..."}]
- 6-15 messages (3-8 turns)
- The first user message rephrases the user_request naturally in the persona's voice
- All decisions, discoveries, and artifacts from the outline MUST appear
- Output ONLY the JSON array — no markdown fences, no explanation"""

SESSION_USER_TEMPLATE = """\
Generate a conversation for this session.

SCENARIO: {title}
DOMAIN: {domain}

{persona_section}

SESSION {session_id} (Day {day}{time_section}):
User's request: {user_request}

{previous_sessions_context}

Topics to cover in conversation:
{topics}

{decisions_section}

{discoveries_section}

Artifacts to produce (include FULL content in assistant's responses):
{artifacts_section}

{entities_section}

CRITICAL REMINDERS:
- Write the user's messages in character — match the persona's style, vocabulary, and quirks
- The user must NOT open with "Hey", "Hi", or "Hello" — jump straight into the topic
- Include at least ONE moment where the user pushes back, disagrees, or questions the approach
- Include at least ONE typo, abbreviation, or incomplete thought from the user
- The assistant must NOT use filler phrases like "Absolutely!", "Great question!", "Happy to help"
- If previous sessions exist, the user should reference prior work naturally at least once
- ALL artifacts listed above must appear in full in the assistant's messages

Output ONLY the JSON array."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_scenario(path: Path) -> dict:
    """Load a scenario YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def format_persona(persona: dict | None) -> str:
    if not persona:
        return "PERSONA: (none specified — use a natural, professional tone)"
    lines = ["PERSONA:"]
    lines.append(f"  Role: {persona['role']}")
    lines.append(f"  Communication style: {persona['communication_style']}")
    if persona.get("quirks"):
        lines.append(f"  Quirks: {', '.join(persona['quirks'])}")
    if persona.get("context"):
        lines.append(f"  Work context: {persona['context']}")
    return "\n".join(lines)


def format_decisions(decisions: list[dict] | None) -> str:
    if not decisions:
        return ""
    lines = ["Decisions made during this session:"]
    for d in decisions:
        lines.append(f"  - Choice: {d['choice']}")
        lines.append(f"    Reasoning: {d['reasoning']}")
        if d.get("alternatives_considered"):
            lines.append(f"    Alternatives rejected: {', '.join(d['alternatives_considered'])}")
    return "\n".join(lines)


def format_discoveries(discoveries: list[dict] | None) -> str:
    if not discoveries:
        return ""
    lines = ["Discoveries/findings during this session:"]
    for d in discoveries:
        lines.append(f"  - Finding: {d['finding']}")
        lines.append(f"    Detail: {d['detail']}")
    return "\n".join(lines)


def format_artifacts(artifacts: list[dict] | None) -> str:
    if not artifacts:
        return ""
    lines = ["Artifacts to produce:"]
    for a in artifacts:
        lines.append(f"  - Type: {a['type']}")
        lines.append(f"    Description: {a['description']}")
        if a.get("key_facts"):
            lines.append("    Key facts to include:")
            for fact in a["key_facts"]:
                lines.append(f"      * {fact}")
    return "\n".join(lines)


def format_previous_sessions(sessions_so_far: list[dict]) -> str:
    if not sessions_so_far:
        return "This is the first session — no prior context."
    lines = ["Previous sessions (the user and assistant have already discussed these):"]
    for s in sessions_so_far:
        lines.append(f"  Session {s['id']} (Day {s.get('day', '?')}): {s.get('user_request', 'N/A')}")
        if s.get("decisions"):
            for d in s["decisions"]:
                lines.append(f"    - Decided: {d['choice']}")
        if s.get("discoveries"):
            for d in s["discoveries"]:
                lines.append(f"    - Found: {d['finding']}")
    return "\n".join(lines)


def parse_json_response(raw: str) -> list[dict]:
    """Parse JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return json.loads(text)


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------

def quality_check(
    messages: list[dict],
    session: dict,
    persona: dict | None,
    is_first_session: bool,
) -> tuple[bool, list[str]]:
    """Check generated conversation for quality issues.

    Returns (passed, list_of_issues).
    """
    issues: list[str] = []

    user_messages = [m for m in messages if m.get("role") == "user"]
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]

    if not user_messages or not assistant_messages:
        issues.append("Missing user or assistant messages")
        return False, issues

    # --- Check forbidden phrases in assistant messages ---
    for msg in assistant_messages:
        content = msg.get("content", "")
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in content.lower():
                issues.append(f"Assistant used forbidden phrase: '{phrase}'")

    # --- Check forbidden openings in first user message ---
    first_user = user_messages[0].get("content", "").strip()
    for opening in FORBIDDEN_OPENINGS:
        if first_user.lower().startswith(opening.lower()):
            issues.append(f"First user message starts with forbidden opening: '{opening}'")

    # --- Check user pushback exists ---
    pushback_indicators = [
        "why not", "what about", "i'm not sure", "im not sure",
        "that seems", "couldn't we", "couldnt we", "wait,", "wait ",
        "hmm", "actually,", "actually ", "but what if",
        "do we really need", "is that necessary", "why can't we",
        "i disagree", "i'd rather", "id rather", "not convinced",
        "over-engineered", "overengineered", "overkill",
        "hold on", "hang on", "alternatively",
        "are you sure", "idk about that", "i don't think",
        "nah", "eh,", "meh",
    ]
    has_pushback = False
    for msg in user_messages:
        content = msg.get("content", "").lower()
        if any(indicator in content for indicator in pushback_indicators):
            has_pushback = True
            break
    if not has_pushback:
        issues.append("No user pushback found — user should disagree or question at least once")

    # --- Check for human imperfections ---
    imperfection_indicators = [
        # Common typos
        "teh ", "adn ", "taht ", "recieve", "wiht ", "jsut ",
        "hte ", "nto ", "coudl ", "shoudl ", "woudl ",
        # Abbreviations
        "tbh", "imo", "imho", "prob ", "rn ", "lmk", "nvm",
        "btw", "fwiw", "afaik", "iirc", "tldr", "wfh",
        "pls ", "thx", "ty ", "np ",
        # Incomplete thoughts / self-corrections
        "— actually", "-- actually", "wait,", "hmm,",
        "nvm", "scratch that", "forget that",
        "...", "—", "- actually", "well,",
    ]
    has_imperfection = False
    for msg in user_messages:
        content = msg.get("content", "").lower()
        if any(indicator in content for indicator in imperfection_indicators):
            has_imperfection = True
            break
    if not has_imperfection:
        issues.append("No human imperfections found — need at least one typo, abbreviation, or self-correction")

    # --- Check artifacts are present ---
    artifacts = session.get("artifacts", [])
    if artifacts:
        all_assistant_text = " ".join(m.get("content", "") for m in assistant_messages).lower()
        for artifact in artifacts:
            desc = artifact.get("description", "").lower()
            # Check for code artifacts by looking for code fences
            if artifact["type"] == "code":
                if "```" not in all_assistant_text:
                    issues.append(f"Missing code artifact: {artifact['description']}")
            # Check key facts appear (spot check — first and last)
            key_facts = artifact.get("key_facts", [])
            if key_facts:
                # Check at least half the key facts are mentioned
                found = sum(1 for fact in key_facts if _fact_present(fact, all_assistant_text))
                if found < len(key_facts) / 2:
                    issues.append(
                        f"Artifact '{artifact['description']}': only {found}/{len(key_facts)} key facts found"
                    )

    # --- Check session continuity (non-first sessions) ---
    if not is_first_session:
        all_user_text = " ".join(m.get("content", "") for m in user_messages).lower()
        continuity_phrases = [
            "last time", "earlier", "remember", "before",
            "previous", "we decided", "we discussed", "we set up",
            "we built", "from the", "that fix", "the one we",
            "already", "back when", "you mentioned", "we agreed",
        ]
        has_continuity = any(phrase in all_user_text for phrase in continuity_phrases)
        if not has_continuity:
            issues.append("Non-first session but user never references previous work")

    return len(issues) == 0, issues


def _fact_present(fact: str, text: str) -> bool:
    """Check if a key fact is substantively represented in the text."""
    # Extract numbers and key terms from the fact
    numbers = re.findall(r'\d+(?:\.\d+)?', fact)
    # If the fact has numbers, check at least one appears
    if numbers:
        return any(n in text for n in numbers)
    # Otherwise check for key words (3+ chars) from the fact
    words = [w.lower() for w in fact.split() if len(w) > 3]
    if not words:
        return True
    matched = sum(1 for w in words if w in text)
    return matched >= len(words) * 0.3


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

async def generate_session(
    llm: LLMClient,
    scenario: dict,
    session: dict,
    previous_sessions: list[dict],
    skip_quality_gate: bool = False,
) -> tuple[list[dict], int]:
    """Generate a full conversation for one session.

    Returns (messages, retry_count).
    """
    persona = scenario.get("persona")
    is_first_session = len(previous_sessions) == 0

    time_section = ""
    if session.get("time"):
        time_section = f", {session['time']}"

    user_prompt = SESSION_USER_TEMPLATE.format(
        title=scenario["title"],
        domain=scenario["domain"],
        persona_section=format_persona(persona),
        session_id=session["id"],
        day=session.get("day", "?"),
        time_section=time_section,
        user_request=session["user_request"],
        previous_sessions_context=format_previous_sessions(previous_sessions),
        topics="\n".join(f"  - {t}" for t in session.get("conversation_topics", [])),
        decisions_section=format_decisions(session.get("decisions")),
        discoveries_section=format_discoveries(session.get("discoveries")),
        artifacts_section=format_artifacts(session.get("artifacts")),
        entities_section=(
            f"Entities/tools mentioned: {', '.join(session.get('entities', []))}"
            if session.get("entities") else ""
        ),
    )

    retries = 0
    while True:
        raw = await llm.generate(SESSION_SYSTEM_PROMPT, user_prompt)

        try:
            messages = parse_json_response(raw)
        except json.JSONDecodeError:
            if retries < MAX_RETRIES:
                retries += 1
                print(f"[JSON parse error, retry {retries}]", end=" ", flush=True)
                continue
            print(f"  WARNING: Failed to parse JSON for session {session['id']}")
            return [{"role": "assistant", "content": raw, "_parse_error": True}], retries

        if skip_quality_gate:
            return messages, retries

        passed, issues = quality_check(messages, session, persona, is_first_session)
        if passed:
            return messages, retries

        if retries >= MAX_RETRIES:
            print(f"\n    Quality issues after {MAX_RETRIES} retries: {'; '.join(issues[:3])}")
            return messages, retries

        retries += 1
        print(f"[quality retry {retries}: {issues[0][:60]}]", end=" ", flush=True)

    return messages, retries


async def generate_scenario(
    llm: LLMClient,
    scenario_path: Path,
    skip_quality_gate: bool = False,
) -> dict:
    """Generate all sessions for one scenario."""
    scenario = load_scenario(scenario_path)
    print(f"\nGenerating: {scenario['title']}")
    persona = scenario.get("persona")
    if persona:
        print(f"  Persona: {persona.get('role', 'unknown')} ({persona.get('communication_style', '')[:50]})")
    print(f"  Sessions: {len(scenario['sessions'])}")

    generated_sessions = []
    previous_sessions = []
    total_retries = 0

    for session in scenario["sessions"]:
        label = f"  Session {session['id']} (day {session.get('day', '?')}"
        if session.get("time"):
            label += f", {session['time']}"
        label += ")..."
        print(label, end=" ", flush=True)

        messages, retries = await generate_session(
            llm, scenario, session, previous_sessions,
            skip_quality_gate=skip_quality_gate,
        )
        total_retries += retries
        retry_note = f" ({retries} retries)" if retries > 0 else ""
        print(f"{len(messages)} messages{retry_note}")

        generated_sessions.append({
            "id": session["id"],
            "day": session.get("day"),
            "time": session.get("time"),
            "user_request": session["user_request"],
            "messages": messages,
        })

        previous_sessions.append(session)

    if total_retries > 0:
        print(f"  Total retries for scenario: {total_retries}")

    result = {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "domain": scenario["domain"],
        "category": scenario["category"],
        "description": scenario["description"],
        "sessions": generated_sessions,
        "qa_pairs": scenario.get("qa_pairs", []),
    }
    if persona:
        result["persona"] = persona

    return result


async def main():
    parser = argparse.ArgumentParser(
        description="Generate benchmark conversations from scenario outlines"
    )
    parser.add_argument(
        "--provider", choices=["openai", "anthropic"], default="openai",
        help="LLM provider (default: openai)",
    )
    parser.add_argument("--model", default="", help="Model override")
    parser.add_argument(
        "--scenario", default=None,
        help="Generate only this scenario number (e.g., '01')",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be generated without calling LLM",
    )
    parser.add_argument(
        "--skip-quality-gate", action="store_true",
        help="Skip quality checks (faster, for iteration)",
    )
    args = parser.parse_args()

    scenario_files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    if not scenario_files:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    if args.scenario:
        scenario_files = [f for f in scenario_files if f.name.startswith(f"{args.scenario}-")]
        if not scenario_files:
            print(f"No scenario found matching '{args.scenario}'")
            sys.exit(1)

    print(f"Found {len(scenario_files)} scenario(s)")

    if args.dry_run:
        for sf in scenario_files:
            s = load_scenario(sf)
            print(f"\n  {s['id']}: {s['title']}")
            persona = s.get("persona")
            if persona:
                print(f"    Persona: {persona.get('role', '?')} — {persona.get('communication_style', '?')[:60]}")
            print(f"    Sessions: {len(s['sessions'])}, QA pairs: {len(s.get('qa_pairs', []))}")
            for sess in s["sessions"]:
                print(f"      {sess['id']} (day {sess.get('day', '?')}): {sess['user_request'][:80]}...")
        return

    llm = LLMClient(provider=args.provider, model=args.model)
    print(f"Using: {llm.provider} / {llm.model}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for sf in scenario_files:
        result = await generate_scenario(llm, sf, skip_quality_gate=args.skip_quality_gate)

        output_path = OUTPUT_DIR / f"{sf.stem}.json"
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {output_path}")

    print(f"\nDone! Generated {len(scenario_files)} scenario(s) in {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
