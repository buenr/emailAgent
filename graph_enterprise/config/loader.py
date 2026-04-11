"""Load one or many mailbox configs from JSON (single object or {mailboxes: [...]} )."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import MailboxPipelineConfig


def load_mailbox_configs(path: Path) -> List[MailboxPipelineConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "mailboxes" in raw:
        return [MailboxPipelineConfig.model_validate(item) for item in raw["mailboxes"]]
    if isinstance(raw, list):
        return [MailboxPipelineConfig.model_validate(item) for item in raw]
    return [MailboxPipelineConfig.model_validate(raw)]
