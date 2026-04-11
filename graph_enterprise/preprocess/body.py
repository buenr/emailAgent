"""Body normalization for token control; align with local prototype patterns."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Optional

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[misc, assignment]
    _HAS_BS4 = False


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._ignore = False

    def handle_starttag(self, tag: str, attrs: list) -> None:  # noqa: ARG002
        if tag in ("style", "script"):
            self._ignore = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script"):
            self._ignore = False

    def handle_data(self, data: str) -> None:  # noqa: D401
        if not self._ignore:
            self._chunks.append(data + " ")

    def text(self) -> str:
        return " ".join(self._chunks)


_WS = re.compile(r"\s+")


def _strip_html_bs4(raw: str) -> str:
    """Extract text with BeautifulSoup + lxml when available (more tolerant of bad HTML)."""
    assert BeautifulSoup is not None
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:
        soup = BeautifulSoup(raw, "html.parser")
    text = unescape(soup.get_text(separator=" "))
    return _WS.sub(" ", text).strip()


def strip_html_to_text(raw: Optional[str]) -> str:
    if not raw:
        return ""
    if _HAS_BS4:
        try:
            return _strip_html_bs4(raw)
        except Exception:
            pass
    parser = _HTMLStripper()
    parser.feed(raw)
    parser.close()
    text = unescape(parser.text())
    return _WS.sub(" ", text).strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def head_first_words(text: str, n: int) -> str:
    """Return the first ``n`` whitespace-delimited words (prefix / latest reply in top-posted mail)."""
    if n <= 0 or not text:
        return text
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n])


def tail_last_words(text: str, n: int) -> str:
    """Return the last ``n`` whitespace-delimited words (suffix of the body)."""
    if n <= 0 or not text:
        return text
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[-n:])


def normalize_body_for_model(
    body_preview: Optional[str],
    body_html: Optional[str] = None,
    *,
    max_chars: int = 8000,
    first_n_words: Optional[int] = 1000,
) -> str:
    """
    Prefer full body when ``body_html`` is set (strip HTML); else plain preview.
    Keep the first ``first_n_words`` words (typical latest reply when the client
    top-posts), then cap length with ``max_chars``. Do not log full bodies in
    operational logs (Part 3).
    """
    if body_html:
        base = strip_html_to_text(body_html)
    else:
        base = (body_preview or "").strip()
    if first_n_words is not None:
        base = head_first_words(base, first_n_words)
    return truncate_text(base, max_chars)
