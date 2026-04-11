"""Subject line LIKE-style matching and hybrid classification (rules before Gemini)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config.models import MailboxPipelineConfig

logger = logging.getLogger(__name__)


def subject_matches_pattern(subject: str, pattern: str) -> bool:
    """
    Case-insensitive SQL LIKE semantics on the full subject: % = any sequence, _ = one char.
    Other characters are literal (regex-metacharacters in the pattern are escaped).
    """
    pat = (pattern or "").strip()
    if not pat:
        return False
    subj = subject or ""
    parts: List[str] = ["^"]
    i = 0
    n = len(pat)
    while i < n:
        c = pat[i]
        if c == "%":
            parts.append(".*")
            i += 1
        elif c == "_":
            parts.append(".")
            i += 1
        else:
            parts.append(re.escape(c))
            i += 1
    parts.append("$")
    try:
        rx = re.compile("".join(parts), re.IGNORECASE | re.DOTALL)
    except re.error:
        return False
    return rx.match(subj) is not None


def partition_messages_by_subject_rules(
    messages: List[Dict[str, Any]],
    mailbox: MailboxPipelineConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    First matching rule per message (category must be in taxonomy). Invalid rule categories
    are skipped (logged); message may match a later rule or fall through to AI list.
    """
    allowed = {c.name for c in mailbox.categories}
    rules = mailbox.subject_classify_rules
    subject_preds: List[Dict[str, Any]] = []
    for_ai: List[Dict[str, Any]] = []
    for msg in messages:
        mid = msg.get("id")
        if not mid:
            continue
        key = str(mid)
        subj = str(msg.get("subject") or "")
        matched: str | None = None
        for rule in rules:
            cat = (rule.category or "").strip()
            if cat not in allowed:
                logger.warning(
                    "Subject rule category %r not in taxonomy for mailbox %s; skipping rule",
                    cat,
                    mailbox.mailbox_id,
                )
                continue
            if subject_matches_pattern(subj, rule.pattern):
                matched = cat
                break
        if matched is not None:
            subject_preds.append({"email_id": key, "category": matched})
        else:
            for_ai.append(msg)
    return subject_preds, for_ai


def try_classify_by_subject_rules(
    mailbox: MailboxPipelineConfig,
    email: Dict[str, Any],
) -> Optional[str]:
    """If subject rules match, return allowed category name; else None."""
    if not mailbox.subject_classify_enabled or not mailbox.subject_classify_rules:
        return None
    allowed = {c.name for c in mailbox.categories}
    subj = str(email.get("subject") or "")
    for rule in mailbox.subject_classify_rules:
        cat = (rule.category or "").strip()
        if cat not in allowed:
            logger.warning(
                "Subject rule category %r not in taxonomy for mailbox %s; skipping rule",
                cat,
                mailbox.mailbox_id,
            )
            continue
        if subject_matches_pattern(subj, rule.pattern):
            return cat
    return None
