"""Graph PATCH to merge Outlook categories on a message (write-back)."""

from __future__ import annotations

import urllib.parse
from typing import Optional, Sequence

from .http_client import GRAPH_ROOT, GraphHttpClient

# Prepended to each model-predicted category on Graph write-back so Outlook tags
# are identifiable as applied by this app (avoids double-prefix if already present).
OUTLOOK_AI_CATEGORY_PREFIX = "AI-"


def outlook_category_label(model_category: str, prefix: str = OUTLOOK_AI_CATEGORY_PREFIX) -> str:
    """Map a configured category name to the string stored on the message in Outlook."""
    if model_category.startswith(prefix):
        return model_category
    return f"{prefix}{model_category}"


def patch_message_categories(
    client: GraphHttpClient,
    mailbox_id: str,
    message_id: str,
    categories: Sequence[str],
    merge_with_existing: bool = True,
    existing_categories: Optional[Sequence[str]] = None,
) -> None:
    """
    PATCH /users/{mailbox}/messages/{id} with categories list.

    If merge_with_existing is True, pass existing_categories from the message
    body you already fetched; otherwise categories replaces the list on the server.
    """
    encoded_mailbox = urllib.parse.quote(mailbox_id, safe="")
    encoded_msg = urllib.parse.quote(message_id, safe="")
    url = f"{GRAPH_ROOT}/users/{encoded_mailbox}/messages/{encoded_msg}"
    if merge_with_existing:
        merged = list(dict.fromkeys(list(existing_categories or []) + list(categories)))
        body = {"categories": merged}
    else:
        body = {"categories": list(categories)}
    resp = client.patch(url, body)
    resp.raise_for_status()
