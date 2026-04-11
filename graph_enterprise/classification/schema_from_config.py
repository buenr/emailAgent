"""Runtime JSON schema for Gemini structured output from per-mailbox categories."""

from __future__ import annotations

from typing import Any, Dict, List

from ..config.models import MailboxPipelineConfig


def mailbox_category_names(config: MailboxPipelineConfig) -> List[str]:
    return [c.name for c in config.categories]


def build_classification_json_schema(config: MailboxPipelineConfig) -> Dict[str, Any]:
    """
    Build a JSON Schema object for response_json_schema: ``category``.

    The caller attaches ``email_id`` in code; the model must not echo message ids.
    """
    names = mailbox_category_names(config)
    props: Dict[str, Any] = {
        "category": {"type": "STRING", "enum": names},
    }
    required: List[str] = ["category"]
    return {
        "type": "OBJECT",
        "properties": props,
        "required": required,
    }
