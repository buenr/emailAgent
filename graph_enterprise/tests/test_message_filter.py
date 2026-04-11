"""Unit tests for Graph $filter composition (no network)."""

from __future__ import annotations

import unittest

from graph_enterprise.config.models import (
    AttachmentFilter,
    FetchTimeWindowMode,
    InboxFetchFilter,
    SubjectKeywordMode,
)
from graph_enterprise.microsoft_graph.message_filter import (
    build_search_from_body_keywords,
    extra_filter_clauses_from_fetch_filter,
    odata_str_literal,
    sender_predicate,
)


class TestODataLiterals(unittest.TestCase):
    def test_escape_single_quote(self) -> None:
        self.assertEqual(odata_str_literal("a'b"), "'a''b'")

    def test_sender_email(self) -> None:
        p = sender_predicate("User@Example.COM")
        self.assertIn("eq 'user@example.com'", p)

    def test_sender_at_domain(self) -> None:
        p = sender_predicate("@Contoso.com")
        self.assertIn("contains", p)
        self.assertIn("@contoso.com", p)

    def test_sender_bare_domain(self) -> None:
        p = sender_predicate("contoso.com")
        self.assertIn("endswith", p)
        self.assertIn("@contoso.com", p)


class TestExtraClauses(unittest.TestCase):
    def test_empty_filter(self) -> None:
        ff = InboxFetchFilter()
        self.assertEqual(extra_filter_clauses_from_fetch_filter(ff), [])

    def test_deny_and_allow(self) -> None:
        ff = InboxFetchFilter(
            sender_allowlist=["a@x.com"],
            sender_denylist=["b@y.com"],
        )
        clauses = extra_filter_clauses_from_fetch_filter(ff)
        self.assertEqual(len(clauses), 2)
        self.assertTrue(clauses[0].startswith("("))
        self.assertIn("not (", clauses[1])

    def test_subject_all_and_any(self) -> None:
        ff_any = InboxFetchFilter(
            subject_keywords=["foo", "bar"],
            subject_keyword_mode=SubjectKeywordMode.any,
        )
        c_any = extra_filter_clauses_from_fetch_filter(ff_any)
        self.assertEqual(len(c_any), 1)
        self.assertIn(" or ", c_any[0])

        ff_all = InboxFetchFilter(
            subject_keywords=["foo", "bar"],
            subject_keyword_mode=SubjectKeywordMode.all,
        )
        c_all = extra_filter_clauses_from_fetch_filter(ff_all)
        self.assertIn(" and ", c_all[0])

    def test_importance_attachments_categories(self) -> None:
        ff = InboxFetchFilter(
            importance_levels=["high"],
            has_attachments=AttachmentFilter.yes,
            category_include_any=["Red"],
            category_exclude_any=["Spam"],
        )
        clauses = extra_filter_clauses_from_fetch_filter(ff)
        text = " ".join(clauses)
        self.assertIn("importance eq 'high'", text)
        self.assertIn("hasAttachments eq true", text)
        self.assertIn("categories/any", text)
        self.assertIn("not categories/any", text)


class TestInboxFetchFilterValidation(unittest.TestCase):
    def test_rolling_mode_requires_hours(self) -> None:
        with self.assertRaises(Exception):
            InboxFetchFilter(
                time_window_mode=FetchTimeWindowMode.rolling_hours,
                rolling_hours=None,
            )

    def test_search_string(self) -> None:
        self.assertIsNone(build_search_from_body_keywords([]))
        s = build_search_from_body_keywords(["a", "b"])
        self.assertIn('"a"', s)
        self.assertIn(" AND ", s)


if __name__ == "__main__":
    unittest.main()
