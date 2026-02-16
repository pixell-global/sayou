"""Auto-metadata generation via LLM providers.

Provider abstraction with Protocol interface. NullMetadataProvider as fallback.
Only touches `_auto_` prefixed fields — never user fields.
"""

from __future__ import annotations

import json
from typing import Protocol


class MetadataProvider(Protocol):
    """Protocol for metadata generation providers."""

    @property
    def provider_name(self) -> str: ...

    async def generate(self, content: str, existing_schema: list[dict] | None = None) -> dict: ...


class NullMetadataProvider:
    """Fallback when no metadata provider is configured."""

    @property
    def provider_name(self) -> str:
        return ""

    async def generate(self, content: str, existing_schema: list[dict] | None = None) -> dict:
        return {}


class OpenAIMetadataProvider:
    """Generate metadata using OpenAI chat completion."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._api_key = api_key
        self._model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for auto-metadata. "
                    "Install with: pip install sayou[ai]"
                )
        return self._client

    async def generate(self, content: str, existing_schema: list[dict] | None = None) -> dict:
        client = self._get_client()
        prompt = build_metadata_prompt(content, existing_schema)
        response = await client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        text = response.choices[0].message.content or ""
        return _parse_metadata_response(text)


def build_metadata_prompt(content: str, existing_schema: list[dict] | None = None) -> str:
    """Build the LLM prompt for metadata generation.

    Includes existing schema for consistency (e.g., reuse category vocabulary).
    """
    # Truncate content to avoid token limits
    max_content = 3000
    truncated = content[:max_content]
    if len(content) > max_content:
        truncated += "\n... (truncated)"

    prompt = f"""Analyze this document and generate metadata. Return ONLY a JSON object with these fields:

- _auto_summary: 1-2 sentence summary
- _auto_tags: list of 3-7 relevant tags (lowercase)
- _auto_category: single category word
- _auto_language: ISO 639-1 language code (e.g., "en", "ja")

Document:
---
{truncated}
---

"""

    if existing_schema:
        # Include existing auto categories for consistency
        auto_categories = []
        auto_tags = []
        for field in existing_schema:
            if field["field_name"] == "_auto_category" and field.get("sample_values"):
                auto_categories = field["sample_values"][:10]
            if field["field_name"] == "_auto_tags" and field.get("sample_values"):
                # Flatten tag lists
                for sv in field["sample_values"][:5]:
                    if isinstance(sv, list):
                        auto_tags.extend(sv)
                    elif isinstance(sv, str):
                        auto_tags.append(sv)

        if auto_categories:
            prompt += f"\nExisting categories in workspace (prefer reusing): {auto_categories}"
        if auto_tags:
            unique_tags = sorted(set(auto_tags))[:20]
            prompt += f"\nExisting tags in workspace (prefer reusing when relevant): {unique_tags}"

    prompt += "\n\nReturn ONLY valid JSON, no markdown fences:"
    return prompt


def _parse_metadata_response(text: str) -> dict:
    """Parse LLM response into metadata dict."""
    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (fences)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}

    # Only keep _auto_ prefixed fields
    return {k: v for k, v in data.items() if k.startswith("_auto_")}


def merge_auto_metadata(existing_frontmatter: dict, auto_metadata: dict) -> dict:
    """Merge auto-generated metadata into existing frontmatter.

    HARD RULE: Only touches `_auto_` prefixed keys. Never modifies user fields.
    """
    merged = dict(existing_frontmatter)
    for key, value in auto_metadata.items():
        if key.startswith("_auto_"):
            merged[key] = value
    return merged


def get_metadata_provider(
    provider: str = "",
    api_key: str = "",
    model: str = "",
) -> MetadataProvider:
    """Factory: return the configured metadata provider or NullProvider."""
    if not provider or not api_key:
        return NullMetadataProvider()

    if provider == "openai":
        return OpenAIMetadataProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
        )

    return NullMetadataProvider()
