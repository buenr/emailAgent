"""Format Graph message attachment metadata for prompts (no file download)."""

from __future__ import annotations

from typing import Any, Dict, List


def format_attachments_block(message: Dict[str, Any]) -> str:
    """
    Build a single line for ``{{ attachments_block }}`` from a Graph message dict.

    Expects optional ``attachments`` collection (from ``$expand``) and/or
    ``hasAttachments``.
    """
    if not message.get("hasAttachments"):
        return "Attachments: none."

    raw = message.get("attachments")
    if not raw:
        return "Attachments: (metadata not loaded; hasAttachments is true)."

    items: List[Dict[str, Any]]
    if isinstance(raw, list):
        items = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, dict) and isinstance(raw.get("value"), list):
        items = [x for x in raw["value"] if isinstance(x, dict)]
    else:
        return "Attachments: (unrecognized attachments shape)."

    if not items:
        return "Attachments: none."

    parts: List[str] = []
    for i, att in enumerate(items, start=1):
        name = str(att.get("name") or att.get("id") or "unnamed")
        ctype = str(att.get("contentType") or "unknown")
        parts.append(f"{i}. {name} ({ctype})")
    return "Attachments: " + ", ".join(parts) + "."
