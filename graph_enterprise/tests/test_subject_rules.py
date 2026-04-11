"""Tests for SQL LIKE-style subject matching."""

from __future__ import annotations

import pytest

from graph_enterprise.classification.subject_rules import subject_matches_pattern


@pytest.mark.parametrize(
    "subject,pattern,expected",
    [
        ("Foo Automated Bar", "%Automated%", True),
        ("foo automated bar", "%AUTOMATED%", True),
        ("No match here", "%Automated%", False),
        ("A_B", "A_B", True),
        ("AXB", "A_B", True),
        ("AB", "A_B", False),
        ("Hello", "%", True),
        ("", "%", True),
        ("", "", False),
        ("  ", "%", True),
    ],
)
def test_subject_matches_pattern(subject: str, pattern: str, expected: bool) -> None:
    assert subject_matches_pattern(subject, pattern) is expected


def test_percent_is_literal_when_escaped_not_supported() -> None:
    """We only support % and _ as wildcards; backslash is not an escape in patterns."""
    assert subject_matches_pattern("50%", "50%") is True
    assert subject_matches_pattern("50x", "50%") is True
