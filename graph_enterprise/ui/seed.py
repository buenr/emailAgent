"""Seed Microsoft SQL Server classifier config from current code defaults."""

from __future__ import annotations

from ..config.default_categories import DEFAULT_CATEGORIES
from . import db

DEFAULT_TEMPLATE_NAME = "Logistics/Trucking Default Prompt"
DEFAULT_SET_NAME = "Logistics/Trucking Default Classification Set"
DEFAULT_INBOX = "afterhours@mytruckingcompany.com"

DEFAULT_PROMPT_TEMPLATE = """You triage email for the Logistics/Trucking after-hours operations desk.
The mailbox is {{ mailbox_id }}. After-hours staff cover overnight and weekend freight operations:
drivers in the field, equipment issues, load execution, and urgent customer or broker issues.

Prioritize like an experienced after-hours coordinator: (1) life-safety and major incidents,
(2) equipment down or temperature risk, (3) active load or appointment problems and external
escalations, (4) driver check-calls and routing, (5) internal handoffs or automated notices.

Base the category on the **latest substantive operational message** when possible—not only the
subject line. For internal staff relaying driver location, miles out, or ETA only, prefer **Driver**
over **ETAOrTracking**. Multi-row trackers with no dominant fix: **BulkStatusDigest** or **General**.
Do not use **EquipmentBreakdownRoadside** for a whole tracker because one row says breakdown unless
the latest top-level reply is clearly about equipment down. Welfare or cab safety: **DriverWelfareSafety**
or **Critical**; not **PickupDeliveryExecution** for a vague acknowledgment on a welfare thread.
Customs only when the latest content is mainly border/customs docs; short internal routing:
**InternalHandoffRouting**, not **CustomsBorder**. Empty trailers / yard positioning: **TrailerEmptyYard**;
external escalation or claims: **CustomerBroker**.

When several topics appear, classify by the most urgent operational problem in the latest
substantive content. Use General only when intent is unclear or no bucket fits well.

### Allowed categories (use exact name)
{{ categories_block }}

### Attachments (filenames and MIME types only; files are not downloaded)
{{ attachments_block }}

### Email
{{ email_block }}

### Instructions
Choose exactly one category from the allowed list.
Return JSON matching the required schema with field ``category``.
"""


def seed() -> None:
    db.init_db()
    with db.get_connection() as conn:
        prompts = db.list_prompt_templates(conn)
        if not prompts:
            prompt_id = db.create_prompt_template(conn, DEFAULT_TEMPLATE_NAME, DEFAULT_PROMPT_TEMPLATE)
        else:
            prompt_id = int(prompts[0]["id"])

        sets = db.list_classification_sets(conn)
        if not sets:
            set_id = db.create_classification_set(conn, DEFAULT_SET_NAME)
            db.replace_categories(
                conn,
                set_id,
                [{"name": c.name, "description": c.description} for c in DEFAULT_CATEGORIES],
            )
        else:
            set_id = int(sets[0]["id"])

        inboxes = db.list_inboxes(conn)
        if not inboxes:
            db.create_inbox(
                conn,
                mailbox_id=DEFAULT_INBOX,
                prompt_template_id=prompt_id,
                classification_set_id=set_id,
                timezone="UTC",
                mail_folder="inbox",
                max_messages_per_run=500,
                patch_max_workers=4,
            )


def main() -> None:
    seed()
    print("Seeded classifier configuration in SQL Server (MSSQL_ODBC_CONNECTION_STRING).")


if __name__ == "__main__":
    main()
