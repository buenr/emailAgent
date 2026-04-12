"""Load mailbox pipeline config from Microsoft SQL Server (see ``MSSQL_ODBC_CONNECTION_STRING``)."""

from __future__ import annotations

from .models import (
    AppModelDefinition,
    CategoryDefinition,
    MailboxPipelineConfig,
    RunPolicy,
    parse_inbox_fetch_filter,
    parse_last_run_at_utc,
    parse_subject_classify_rules,
)
from ..ui import db


def _row_to_config(inbox: dict) -> MailboxPipelineConfig:
    set_id = int(inbox["classification_set_id"])
    # get_inbox_config / get_inbox_by_id attach categories
    categories = inbox.get("categories") or []
    is_active = bool(inbox.get("is_active", True))
    polling = int(inbox.get("polling_interval_minutes") or 5)
    iid = inbox.get("id")
    app_model = None
    if inbox.get("app_model_id"):
        app_model = AppModelDefinition(
            id=int(inbox["app_model_id"]),
            name=str(inbox.get("app_model_name") or ""),
        )
    ff_raw = inbox["fetch_filter"] if "fetch_filter" in inbox else inbox.get("fetch_filter_json")
    ff = parse_inbox_fetch_filter(ff_raw)
    last_run = parse_last_run_at_utc(inbox.get("last_run_at"))
    rules_raw = inbox.get("subject_classify_rules")
    if rules_raw is None:
        rules_raw = inbox.get("subject_classify_rules_json")
    return MailboxPipelineConfig(
        inbox_id=int(iid) if iid is not None else None,
        is_active=is_active,
        graph_write_back_enabled=bool(inbox.get("graph_write_back_enabled", True)),
        mailbox_id=str(inbox["mailbox_id"]),
        categories=[
            CategoryDefinition(name=str(r["name"]), description=str(r.get("description") or ""))
            for r in categories
        ],
        run_policy=RunPolicy(
            polling_interval_minutes=polling,
            max_messages_per_run=inbox.get("max_messages_per_run"),
            timezone=str(inbox.get("timezone") or "UTC"),
            mail_folder=str(inbox.get("mail_folder") or "inbox"),
            patch_max_workers=int(inbox.get("patch_max_workers") or 4),
        ),
        prompt_template=str(inbox.get("prompt_template") or ""),
        app_model=app_model,
        fetch_filter=ff,
        last_run_at=last_run,
        subject_classify_enabled=bool(inbox.get("subject_classify_enabled", False)),
        subject_classify_rules=parse_subject_classify_rules(rules_raw),
    )


def load_mailbox_config_from_db(mailbox_id: str) -> MailboxPipelineConfig:
    with db.get_connection() as conn:
        inbox = db.get_inbox_config(conn, mailbox_id)
        if not inbox:
            raise ValueError(f"No inbox config found in DB for mailbox_id={mailbox_id!r}")
    return _row_to_config(inbox)


def load_mailbox_config_by_inbox_id(inbox_id: int) -> MailboxPipelineConfig:
    with db.get_connection() as conn:
        inbox = db.get_inbox_by_id(conn, inbox_id)
        if not inbox:
            raise ValueError(f"No inbox config found in DB for inbox_id={inbox_id!r}")
    return _row_to_config(inbox)
