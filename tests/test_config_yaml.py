"""Campaign names in config/*.yaml must survive YAML parsing.

YAML treats " #" as the start of a comment, so an unquoted list
item such as `- Campaign #2` is read as "Campaign" and the rule
silently matches nothing. This test fails when a campaign-name
line (a list item or a `prefix:` value) contains " #" and the
parsed config does not hold the full name. Fix: quote the name,
or put a real comment on its own line.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILES = sorted((ROOT / "config").glob("*.yaml"))

# "- name" or "prefix: name", not a comment line.
NAME_LINE = re.compile(r"^\s*(?:-\s+|prefix:\s+)(?P<value>[^#\s].*)$")


def _strings(node):
    """Every string value anywhere in a parsed YAML document."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _unquote(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


@pytest.mark.parametrize("path", CONFIG_FILES, ids=lambda p: p.name)
def test_campaign_names_with_hash_are_read_in_full(path):
    text = path.read_text(encoding="utf-8")
    parsed = set(_strings(yaml.safe_load(text)))
    misread = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = NAME_LINE.match(line)
        if not match or " #" not in match.group("value"):
            continue
        name = _unquote(match.group("value"))
        if name not in parsed:
            misread.append(f"{path.name}:{number}: {line.strip()}")
    assert not misread, (
        "YAML reads text after ' #' as a comment; quote these names:\n"
        + "\n".join(misread)
    )
