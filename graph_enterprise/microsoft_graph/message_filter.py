"""Build Microsoft Graph $filter fragments and $search strings from InboxFetchFilter."""

from __future__ import annotations

from typing import List, Optional

from ..config.models import AttachmentFilter, InboxFetchFilter, SubjectKeywordMode


def odata_str_literal(value: str) -> str:
    """Escape a string for OData single-quoted literals."""
    return "'" + value.replace("'", "''") + "'"


def sender_predicate(entry: str) -> str:
    """
    One predicate for matching from/emailAddress/address.

    - ``user@host`` → case-insensitive equality.
    - ``@domain`` or bare ``domain`` → address contains ``@domain`` / ends with ``@domain``.
    """
    e = entry.strip().lower()
    if not e:
        return ""
    addr = "tolower(from/emailAddress/address)"
    if e.startswith("@"):
        return f"contains({addr},{odata_str_literal(e)})"
    if "@" in e:
        return f"{addr} eq {odata_str_literal(e)}"
    suf = odata_str_literal("@" + e)
    return f"endswith({addr},{suf})"


def extra_filter_clauses_from_fetch_filter(ff: InboxFetchFilter) -> List[str]:
    """Return additional $filter clauses (AND-ed) beyond receivedDateTime and isRead."""
    clauses: List[str] = []

    allow = [sender_predicate(x) for x in ff.sender_allowlist]
    allow = [p for p in allow if p]
    if allow:
        clauses.append("(" + " or ".join(allow) + ")")

    deny = [sender_predicate(x) for x in ff.sender_denylist]
    deny = [p for p in deny if p]
    if deny:
        clauses.append("not (" + " or ".join(deny) + ")")

    subj: List[str] = []
    for kw in ff.subject_keywords:
        subj.append(f"contains(subject,{odata_str_literal(kw)})")
    if subj:
        joiner = " and " if ff.subject_keyword_mode == SubjectKeywordMode.all else " or "
        clauses.append("(" + joiner.join(subj) + ")")

    if ff.importance_levels:
        imp_parts = [f"importance eq {odata_str_literal(x)}" for x in ff.importance_levels]
        clauses.append("(" + " or ".join(imp_parts) + ")")

    if ff.has_attachments == AttachmentFilter.yes:
        clauses.append("hasAttachments eq true")
    elif ff.has_attachments == AttachmentFilter.no:
        clauses.append("hasAttachments eq false")

    inc = [odata_str_literal(c) for c in ff.category_include_any if c]
    if inc:
        inner = " or ".join(f"c eq {lit}" for lit in inc)
        clauses.append(f"categories/any(c:({inner}))")

    exc = [odata_str_literal(c) for c in ff.category_exclude_any if c]
    if exc:
        inner = " or ".join(f"c eq {lit}" for lit in exc)
        clauses.append(f"not categories/any(c:({inner}))")

    return clauses


def build_search_from_body_keywords(keywords: List[str]) -> Optional[str]:
    """
    Microsoft Graph $search string for message body-related terms (AND semantics).

    Escapes embedded double quotes. Returns None when there is nothing to search.
    """
    if not keywords:
        return None
    parts: List[str] = []
    for kw in keywords:
        k = kw.strip()
        if not k:
            continue
        escaped = k.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'"{escaped}"')
    if not parts:
        return None
    return " AND ".join(parts)
