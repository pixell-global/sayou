"""F6: Frontmatter robustness - lenient parsing, never crashes."""

import pytest

from sayou.core.frontmatter import parse_frontmatter


def test_standard_delimiters():
    content = "---\ntitle: Hello\nstatus: active\n---\n# Body"
    fm, body = parse_frontmatter(content)
    assert fm["title"] == "Hello"
    assert fm["status"] == "active"
    assert body == "# Body"


def test_missing_closing_delimiter():
    content = "---\ntitle: Hello\nstatus: active\n\n# Body content"
    fm, body = parse_frontmatter(content)
    assert fm["title"] == "Hello"
    assert fm["status"] == "active"
    assert "# Body content" in body


def test_unquoted_strings_with_colons():
    """YAML can't parse unquoted colons in values — parser falls back gracefully."""
    content = "---\ntitle: Hello: World\nurl: https://example.com\n---\nBody"
    fm, body = parse_frontmatter(content)
    # YAML interprets "Hello: World" as a nested mapping, which fails.
    # Lenient parser returns empty dict (never crashes).
    assert isinstance(fm, dict)

    # Quoted colons work fine
    content2 = '---\ntitle: "Hello: World"\nurl: "https://example.com"\n---\nBody'
    fm2, body2 = parse_frontmatter(content2)
    assert fm2["title"] == "Hello: World"
    assert fm2["url"] == "https://example.com"


def test_empty_content():
    fm, body = parse_frontmatter("")
    assert fm == {}
    assert body == ""


def test_no_frontmatter():
    content = "# Just a heading\n\nSome paragraph text."
    fm, body = parse_frontmatter(content)
    assert fm == {}
    assert body == content


def test_invalid_yaml_returns_empty():
    content = "---\n[invalid yaml: {{\n---\nBody"
    fm, body = parse_frontmatter(content)
    assert fm == {}


def test_nested_objects():
    content = "---\nmeta:\n  author: alice\n  version: 2\ntags:\n  - a\n  - b\n---\nBody"
    fm, body = parse_frontmatter(content)
    assert fm["meta"]["author"] == "alice"
    assert fm["meta"]["version"] == 2
    assert fm["tags"] == ["a", "b"]


def test_bare_key_value_pairs():
    content = "title: My Document\nstatus: draft\n\n# Content here"
    fm, body = parse_frontmatter(content)
    assert fm["title"] == "My Document"
    assert fm["status"] == "draft"
    assert "# Content here" in body


def test_single_bare_key_not_parsed():
    """Bare keys need at least 2 pairs to be detected."""
    content = "title: My Document\n\n# Content"
    fm, body = parse_frontmatter(content)
    assert fm == {}
    assert body == content


def test_whitespace_only_content():
    fm, body = parse_frontmatter("   \n\n  \n")
    assert fm == {}


def test_none_content():
    fm, body = parse_frontmatter(None)
    assert fm == {}
    assert body == ""


def test_frontmatter_with_list_values():
    content = "---\ntags: [alpha, beta, gamma]\n---\nContent"
    fm, body = parse_frontmatter(content)
    assert fm["tags"] == ["alpha", "beta", "gamma"]


def test_frontmatter_with_boolean_values():
    content = "---\npublished: true\ndraft: false\n---\nContent"
    fm, body = parse_frontmatter(content)
    assert fm["published"] is True
    assert fm["draft"] is False
