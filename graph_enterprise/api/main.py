"""FastAPI server for Email Classifier configuration UI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Python does not read `.env` by itself; load repo-root `.env` before config imports.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .admin_auth import auth_disabled, auth_router, require_admin
from ..classification.gemini_category_batch import run_test_prompt_classification
from ..config.default_categories import DEFAULT_CATEGORIES
from ..config.db_loader import _row_to_config
from ..config.models import InboxFetchFilter, SubjectClassifyRule
from ..ui import db

_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


def _cors_allow_origins() -> list[str]:
    raw = (os.getenv("CORS_ORIGINS") or "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [part.strip() for part in raw.split(",") if part.strip()]


app = FastAPI(title="Email Classifier Config API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

public = APIRouter(prefix="/api")
protected = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


def _integrity(msg: str) -> HTTPException:
    return HTTPException(status_code=409, detail=msg)




# --- Schemas ---


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1)
    body: str


class PromptTemplateUpdate(BaseModel):
    name: str = Field(..., min_length=1)
    body: str


class ClassificationSetCreate(BaseModel):
    name: str = Field(..., min_length=1)


class ClassificationSetRename(BaseModel):
    name: str = Field(..., min_length=1)


class TaxonomyRow(BaseModel):
    name: str
    description: str = ""


class TaxonomyUpdate(BaseModel):
    categories: List[TaxonomyRow]


class AgentApiConfig(BaseModel):
    name: str = Field(..., min_length=1)
    api_url: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)


_MSG_AT_LEAST_ONE_CATEGORY = "At least one category is required."


def _subject_rules_json(rules: List[SubjectClassifyRule]) -> Optional[str]:
    if not rules:
        return None
    return json.dumps([r.model_dump(mode="json") for r in rules])


def _validate_subject_rules_against_set(
    conn: Any,
    classification_set_id: int,
    enabled: bool,
    rules: List[SubjectClassifyRule],
) -> None:
    if not enabled or not rules:
        return
    cats = db.list_categories(conn, classification_set_id)
    allowed = {str(c["name"]).strip() for c in cats}
    for rule in rules:
        name = rule.category.strip()
        if name not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Subject rule category {rule.category!r} is not in the selected classification set."
                ),
            )


class InboxCreate(BaseModel):
    mailbox_id: str = Field(..., min_length=1)
    prompt_template_id: int
    classification_set_id: int
    app_model_id: Optional[int] = None
    timezone: str = "UTC"
    mail_folder: str = "inbox"
    max_messages_per_run: Optional[int] = 500
    patch_max_workers: int = Field(default=4, ge=1, le=4)
    polling_interval_minutes: int = Field(default=5, ge=1, le=1440)
    is_active: bool = True
    graph_write_back_enabled: bool = True
    fetch_filter: Optional[InboxFetchFilter] = None
    subject_classify_enabled: bool = False
    subject_classify_rules: List[SubjectClassifyRule] = Field(default_factory=list)


class InboxUpdate(BaseModel):
    mailbox_id: str = Field(..., min_length=1)
    prompt_template_id: int
    classification_set_id: int
    app_model_id: Optional[int] = None
    timezone: str = "UTC"
    mail_folder: str = "inbox"
    max_messages_per_run: Optional[int] = 500
    patch_max_workers: int = Field(default=4, ge=1, le=4)
    polling_interval_minutes: int = Field(default=5, ge=1, le=1440)
    is_active: bool = True
    graph_write_back_enabled: bool = True
    fetch_filter: InboxFetchFilter = Field(default_factory=InboxFetchFilter)
    subject_classify_enabled: bool = False
    subject_classify_rules: List[SubjectClassifyRule] = Field(default_factory=list)


class BulkActivateRequest(BaseModel):
    inbox_ids: List[int] = Field(..., min_length=1)
    is_active: bool


class BulkDeleteRequest(BaseModel):
    inbox_ids: List[int] = Field(..., min_length=1)


class AppModelCreate(BaseModel):
    name: str = Field(..., min_length=1)


class GlobalPollingUpdate(BaseModel):
    paused: bool


class TestPromptRequest(BaseModel):
    """Run Gemini once against a mock message using an inbox's taxonomy and model."""

    inbox_id: int = Field(..., ge=1)
    body: str = Field(..., min_length=1, description="Mock email body (plain text).")
    subject: str = "Test subject"
    sender: str = "sender@example.com"
    received: Optional[str] = Field(
        None,
        description="ISO 8601 received time; defaults to now (UTC) if omitted.",
    )
    prompt_template_override: Optional[str] = Field(
        None,
        description="If set, use this template body instead of the saved DB template (unsaved edits).",
    )


# --- Health ---


@public.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "demo": db.is_demo_mode(),
        "admin_auth_disabled": auth_disabled(),
    }


# --- Dashboard ---


@protected.get("/inbox-summary")
def inbox_summary() -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.inbox_summary(conn)


# --- Prompt templates ---


@protected.get("/prompt-templates")
def list_prompt_templates() -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.list_prompt_templates(conn)


@protected.post("/prompt-templates", status_code=201)
def create_prompt_template(payload: PromptTemplateCreate) -> dict[str, int]:
    try:
        with db.get_connection() as conn:
            new_id = db.create_prompt_template(conn, payload.name.strip(), payload.body)
        return {"id": new_id}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Template name must be unique.") from e
        raise


@protected.put("/prompt-templates/{template_id}")
def update_prompt_template(template_id: int, payload: PromptTemplateUpdate) -> dict[str, str]:
    try:
        with db.get_connection() as conn:
            db.update_prompt_template(conn, template_id, payload.name.strip(), payload.body)
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Template name must be unique.") from e
        raise


@protected.delete("/prompt-templates/{template_id}")
def delete_prompt_template(template_id: int) -> dict[str, str]:
    try:
        with db.get_connection() as conn:
            db.delete_prompt_template(conn, template_id)
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Template is in use by an inbox and cannot be deleted.") from e
        raise


@protected.post("/test-prompt")
def test_prompt(payload: TestPromptRequest) -> dict[str, Any]:
    from datetime import datetime, timezone

    with db.get_connection() as conn:
        inbox = db.get_inbox_by_id(conn, payload.inbox_id)
        if not inbox:
            raise HTTPException(status_code=404, detail="Inbox not found.")
        row = dict(inbox)
        if payload.prompt_template_override is not None:
            row["prompt_template"] = payload.prompt_template_override
        mailbox = _row_to_config(row)

    recv = payload.received
    if not recv or not str(recv).strip():
        recv = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    mock_email: dict[str, Any] = {
        "id": "00000000-0000-0000-0000-000000000001",
        "subject": payload.subject,
        "sender": {"emailAddress": {"address": payload.sender}},
        "receivedDateTime": recv,
        "bodyPreview": payload.body,
    }

    try:
        return run_test_prompt_classification(mailbox, mock_email)
    except ValueError as e:
        msg = str(e)
        if any(
            x in msg
            for x in ("VERTEX_PROJECT", "VERTEX_REGION", "GEMINI_MODEL", "API_KEY", "credentials")
        ):
            raise HTTPException(status_code=503, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


# --- Classification sets ---


@protected.get("/classification-sets")
def list_classification_sets() -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.list_classification_sets(conn)


@protected.get("/classification-sets/{set_id}")
def get_classification_set_detail(set_id: int) -> dict[str, Any]:
    with db.get_connection() as conn:
        rows = db.list_classification_sets(conn)
        selected = next((s for s in rows if int(s["id"]) == set_id), None)
        if not selected:
            raise HTTPException(status_code=404, detail="Classification set not found.")
        categories = db.list_categories(conn, set_id)
    return {
        **dict(selected),
        "categories": categories,
    }


@protected.post("/classification-sets", status_code=201)
def create_classification_set(payload: ClassificationSetCreate) -> dict[str, int]:
    try:
        with db.get_connection() as conn:
            new_id = db.create_classification_set(conn, payload.name.strip())
        return {"id": new_id}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Set name must be unique.") from e
        raise


@protected.put("/classification-sets/{set_id}")
def rename_classification_set(set_id: int, payload: ClassificationSetRename) -> dict[str, str]:
    try:
        with db.get_connection() as conn:
            db.update_classification_set(conn, set_id, payload.name.strip())
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Set name must be unique.") from e
        raise


@protected.delete("/classification-sets/{set_id}")
def delete_classification_set(set_id: int) -> dict[str, str]:
    try:
        with db.get_connection() as conn:
            db.delete_classification_set(conn, set_id)
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Set is in use by an inbox and cannot be deleted.") from e
        raise


def _normalize_taxonomy_rows(rows: List[TaxonomyRow]) -> List[dict[str, str]]:
    out: List[dict[str, str]] = []
    for row in rows:
        name = row.name.strip()
        if not name:
            continue
        out.append({"name": name, "description": row.description.strip()})
    return out


@protected.put("/classification-sets/{set_id}/taxonomy")
def update_taxonomy(set_id: int, payload: TaxonomyUpdate) -> dict[str, str]:
    clean_cats = _normalize_taxonomy_rows(payload.categories)
    if not clean_cats:
        raise HTTPException(status_code=400, detail=_MSG_AT_LEAST_ONE_CATEGORY)
    with db.get_connection() as conn:
        rows = db.list_classification_sets(conn)
        if not any(int(s["id"]) == set_id for s in rows):
            raise HTTPException(status_code=404, detail="Classification set not found.")
        db.replace_categories(conn, set_id, clean_cats)
    return {"status": "ok"}


@protected.post("/classification-sets/{set_id}/seed-defaults")
def seed_classification_defaults(set_id: int) -> dict[str, str]:
    with db.get_connection() as conn:
        rows = db.list_classification_sets(conn)
        if not any(int(s["id"]) == set_id for s in rows):
            raise HTTPException(status_code=404, detail="Classification set not found.")
        db.replace_categories(
            conn,
            set_id,
            [{"name": c.name, "description": c.description} for c in DEFAULT_CATEGORIES],
        )
    return {"status": "ok"}


# --- Inboxes ---


@protected.get("/inboxes")
def list_inboxes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with db.get_connection() as conn:
        total = db.count_inboxes(conn, search=search, is_active=is_active)
        items = db.list_inboxes(
            conn, offset=offset, limit=page_size, search=search, is_active=is_active
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@protected.get("/inboxes/{inbox_id}")
def get_inbox(inbox_id: int) -> dict[str, Any]:
    with db.get_connection() as conn:
        row = db.get_inbox_by_id(conn, inbox_id)
    if not row:
        raise HTTPException(status_code=404, detail="Inbox not found.")
    return row


@protected.post("/inboxes", status_code=201)
def create_inbox(payload: InboxCreate) -> dict[str, int]:
    mf = payload.mail_folder.strip() or "inbox"
    ff_json = (
        payload.fetch_filter.model_dump_json()
        if payload.fetch_filter is not None
        else None
    )
    try:
        with db.get_connection() as conn:
            _validate_subject_rules_against_set(
                conn,
                payload.classification_set_id,
                payload.subject_classify_enabled,
                payload.subject_classify_rules,
            )
            new_id = db.create_inbox(
                conn,
                mailbox_id=payload.mailbox_id.strip(),
                prompt_template_id=payload.prompt_template_id,
                classification_set_id=payload.classification_set_id,
                app_model_id=payload.app_model_id,
                timezone=payload.timezone,
                mail_folder=mf,
                max_messages_per_run=payload.max_messages_per_run,
                patch_max_workers=payload.patch_max_workers,
                polling_interval_minutes=payload.polling_interval_minutes,
                is_active=payload.is_active,
                graph_write_back_enabled=payload.graph_write_back_enabled,
                fetch_filter_json=ff_json,
                subject_classify_enabled=payload.subject_classify_enabled,
                subject_classify_rules_json=_subject_rules_json(payload.subject_classify_rules),
            )
        return {"id": new_id}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Mailbox ID must be unique.") from e
        raise


@protected.put("/inboxes/{inbox_id}")
def update_inbox(inbox_id: int, payload: InboxUpdate) -> dict[str, str]:
    mf = payload.mail_folder.strip() or "inbox"
    ff_json = payload.fetch_filter.model_dump_json()
    try:
        with db.get_connection() as conn:
            _validate_subject_rules_against_set(
                conn,
                payload.classification_set_id,
                payload.subject_classify_enabled,
                payload.subject_classify_rules,
            )
            db.update_inbox(
                conn,
                inbox_id=inbox_id,
                mailbox_id=payload.mailbox_id.strip(),
                prompt_template_id=payload.prompt_template_id,
                classification_set_id=payload.classification_set_id,
                app_model_id=payload.app_model_id,
                timezone=payload.timezone,
                mail_folder=mf,
                max_messages_per_run=payload.max_messages_per_run,
                patch_max_workers=payload.patch_max_workers,
                polling_interval_minutes=payload.polling_interval_minutes,
                is_active=payload.is_active,
                graph_write_back_enabled=payload.graph_write_back_enabled,
                fetch_filter_json=ff_json,
                subject_classify_enabled=payload.subject_classify_enabled,
                subject_classify_rules_json=_subject_rules_json(payload.subject_classify_rules),
            )
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Mailbox ID must be unique.") from e
        raise


@protected.delete("/inboxes/{inbox_id}")
def delete_inbox(inbox_id: int) -> dict[str, str]:
    with db.get_connection() as conn:
        db.delete_inbox(conn, inbox_id)
    return {"status": "ok"}


@protected.post("/inboxes/bulk-activate")
def bulk_activate_inboxes(payload: BulkActivateRequest) -> dict[str, int]:
    with db.get_connection() as conn:
        updated = db.bulk_update_inbox_active(conn, payload.inbox_ids, payload.is_active)
    return {"updated": updated}


@protected.post("/inboxes/bulk-delete")
def bulk_delete_inboxes(payload: BulkDeleteRequest) -> dict[str, int]:
    with db.get_connection() as conn:
        deleted = db.bulk_delete_inboxes(conn, payload.inbox_ids)
    return {"deleted": deleted}


@protected.get("/fleet-summary")
def fleet_summary(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    with db.get_connection() as conn:
        total = db.count_inboxes(conn, search=search, is_active=is_active)
        items = db.fleet_summary(
            conn, offset=offset, limit=page_size, search=search, is_active=is_active
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@protected.get("/global-polling")
def get_global_polling() -> dict[str, bool]:
    with db.get_connection() as conn:
        return {"paused": db.get_global_polling_paused(conn)}


# --- Stats ---


@protected.get("/stats/token-trends")
def token_trends(days: int = Query(7, ge=0)) -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.token_trends(conn, days=days)


@protected.get("/stats/classification-breakdown")
def classification_breakdown(
    inbox_id: int = Query(..., ge=1),
    days: int = Query(7, ge=0),
) -> dict[str, Any]:
    with db.get_connection() as conn:
        return db.classification_breakdown(conn, inbox_id=inbox_id, days=days)


@protected.get("/stats/run-volume")
def run_volume(days: int = Query(30, ge=0)) -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.run_volume(conn, days=days)


@protected.put("/global-polling")
def put_global_polling(payload: GlobalPollingUpdate) -> dict[str, str]:
    with db.get_connection() as conn:
        db.set_global_polling_paused(conn, payload.paused)
    return {"status": "ok"}

@protected.get("/agent-apis")
def list_agent_apis() -> List[dict[str, str]]:
    with db.get_connection() as conn:
        return db.get_agent_api_configs(conn)


@protected.put("/agent-apis")
def put_agent_apis(payload: List[AgentApiConfig]) -> dict[str, str]:
    configs = [
        {"name": c.name.strip(), "api_url": c.api_url.strip(), "api_key": c.api_key}
        for c in payload
    ]
    with db.get_connection() as conn:
        db.set_agent_api_configs(conn, configs)
    return {"status": "ok"}

# --- App Models ---


@protected.get("/app-models")
def list_app_models() -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.list_app_models(conn)


@protected.post("/app-models", status_code=201)
def create_app_model(payload: AppModelCreate) -> dict[str, int]:
    try:
        with db.get_connection() as conn:
            new_id = db.create_app_model(conn, payload.name.strip())
        return {"id": new_id}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Model name must be unique.") from e
        raise


@protected.delete("/app-models/{model_id}")
def delete_app_model(model_id: int) -> dict[str, str]:
    try:
        with db.get_connection() as conn:
            db.delete_app_model(conn, model_id)
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Model is in use by an inbox and cannot be deleted.") from e
        raise


@protected.get("/inboxes/{inbox_id}/run-logs")
def get_inbox_run_logs(
    inbox_id: int, limit: int = Query(50, ge=1, le=500)
) -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        if not db.get_inbox_by_id(conn, inbox_id):
            raise HTTPException(status_code=404, detail="Inbox not found.")
        return db.list_run_logs_for_inbox(conn, inbox_id, limit=limit)


@protected.post("/inboxes/{inbox_id}/run")
def trigger_inbox_run(inbox_id: int) -> dict[str, Any]:
    """Trigger a mailbox classification run for the given inbox."""
    from ..jobs.mailbox_run import run_scheduled_mailbox_pipeline
    from ..jobs.run_lock import is_run_lock_held, release_run_lock, try_acquire_run_lock

    with db.get_connection() as conn:
        inbox = db.get_inbox_by_id(conn, inbox_id)
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found.")
    if not inbox.get("is_active"):
        raise HTTPException(status_code=400, detail="Inbox is not active")

    lock_acquired = False
    if not db.is_demo_mode():
        # Fast-path conflict check.
        if is_run_lock_held(inbox_id):
            raise HTTPException(status_code=409, detail="A run is already in progress for this inbox")
        # Atomic lock attempt to prevent race between concurrent trigger requests.
        lock_acquired = bool(try_acquire_run_lock(inbox_id))
        if not lock_acquired:
            if is_run_lock_held(inbox_id):
                raise HTTPException(
                    status_code=409, detail="A run is already in progress for this inbox"
                )
            raise HTTPException(
                status_code=503,
                detail="Run lock infrastructure unavailable. Configure Redis run locking and retry.",
            )

    try:
        metrics = run_scheduled_mailbox_pipeline(inbox_id)
    except ValueError as e:
        msg = str(e)
        if "not active" in msg.lower():
            raise HTTPException(status_code=400, detail="Inbox is not active") from e
        raise HTTPException(status_code=400, detail=msg) from e
    except RuntimeError as e:
        msg = str(e)
        if any(
            kw in msg
            for kw in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
                       "VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_API_KEY")
        ):
            raise HTTPException(
                status_code=503,
                detail=f"Missing credentials: {msg}",
            ) from e
        raise HTTPException(status_code=500, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if lock_acquired:
            release_run_lock(inbox_id)

    result: dict[str, Any] = {"status": metrics.status.lower()}
    if metrics.status == "Success":
        result["run_id"] = metrics.run_id
        result["status"] = "completed"
    return result


@protected.post("/inboxes/{inbox_id}/agentic-run")
def trigger_inbox_agentic_run(inbox_id: int) -> dict[str, Any]:
    """Trigger an independent agentic workflow run for the given inbox."""
    from ..jobs.mailbox_run import run_scheduled_agentic_pipeline
    from ..jobs.run_lock import is_run_lock_held, release_run_lock, try_acquire_run_lock

    with db.get_connection() as conn:
        inbox = db.get_inbox_by_id(conn, inbox_id)
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found.")
    if not inbox.get("is_active"):
        raise HTTPException(status_code=400, detail="Inbox is not active")

    lock_acquired = False
    if not db.is_demo_mode():
        if is_run_lock_held(inbox_id):
            raise HTTPException(status_code=409, detail="A run is already in progress for this inbox")
        lock_acquired = bool(try_acquire_run_lock(inbox_id))
        if not lock_acquired:
            if is_run_lock_held(inbox_id):
                raise HTTPException(
                    status_code=409, detail="A run is already in progress for this inbox"
                )
            raise HTTPException(
                status_code=503,
                detail="Run lock infrastructure unavailable. Configure Redis run locking and retry.",
            )

    try:
        summary = run_scheduled_agentic_pipeline(inbox_id)
    except ValueError as e:
        msg = str(e)
        if "not active" in msg.lower():
            raise HTTPException(status_code=400, detail="Inbox is not active") from e
        raise HTTPException(status_code=400, detail=msg) from e
    except RuntimeError as e:
        msg = str(e)
        if any(
            kw in msg
            for kw in (
                "AZURE_TENANT_ID",
                "AZURE_CLIENT_ID",
                "AZURE_CLIENT_SECRET",
                "VERTEX_PROJECT",
                "GOOGLE_APPLICATION_CREDENTIALS",
                "GOOGLE_CLOUD_API_KEY",
            )
        ):
            raise HTTPException(
                status_code=503,
                detail=f"Missing credentials: {msg}",
            ) from e
        raise HTTPException(status_code=500, detail=msg) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if lock_acquired:
            release_run_lock(inbox_id)

    return {
        "status": "completed",
        **summary,
    }


@protected.get("/run-logs/{run_log_id}/classifications")
def get_run_log_classifications(run_log_id: int) -> List[dict[str, Any]]:
    """Return per-email classifications for a specific run log entry."""
    with db.get_connection() as conn:
        return db.list_message_classifications_by_run(conn, run_log_id)


@protected.get("/inboxes/{inbox_id}/classifications")
def get_inbox_classifications(
    inbox_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    category: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
) -> dict[str, Any]:
    """Return per-email classifications for an inbox with optional filters and server-side pagination."""
    with db.get_connection() as conn:
        if not db.get_inbox_by_id(conn, inbox_id):
            raise HTTPException(status_code=404, detail="Inbox not found.")
        return db.list_message_classifications_by_inbox(
            conn, inbox_id, category=category, since=since, until=until,
            page=page, page_size=page_size,
        )


@protected.get("/inboxes/{inbox_id}/classifications/categories")
def get_inbox_classification_categories(inbox_id: int) -> List[str]:
    """Return distinct category values for an inbox (for filter dropdowns)."""
    with db.get_connection() as conn:
        if not db.get_inbox_by_id(conn, inbox_id):
            raise HTTPException(status_code=404, detail="Inbox not found.")
        return db.list_distinct_categories_by_inbox(conn, inbox_id)


# --- Export / Import ---


@protected.get("/export")
def export_data() -> dict[str, Any]:
    """Export all configuration data as JSON."""
    with db.get_connection() as conn:
        prompt_templates = db.list_prompt_templates(conn)
        classification_sets_raw = db.list_classification_sets(conn)
        classification_sets: list[dict[str, Any]] = []
        for cs in classification_sets_raw:
            categories = db.list_categories(conn, int(cs["id"]))
            classification_sets.append({**cs, "categories": categories})
        inboxes = db.list_inboxes(conn)
        app_models = db.list_app_models(conn)
    return {
        "prompt_templates": prompt_templates,
        "classification_sets": classification_sets,
        "inboxes": inboxes,
        "app_models": app_models,
    }


class ImportPayload(BaseModel):
    prompt_templates: List[dict[str, Any]] = Field(default_factory=list)
    classification_sets: List[dict[str, Any]] = Field(default_factory=list)
    inboxes: List[dict[str, Any]] = Field(default_factory=list)
    app_models: List[dict[str, Any]] = Field(default_factory=list)


@protected.post("/import")
def import_data(payload: ImportPayload) -> dict[str, Any]:
    """Upsert configuration data from JSON using one transaction (fail-fast on first invalid row)."""

    def _item_error(collection: str, index: int, message: str) -> HTTPException:
        return HTTPException(status_code=400, detail=f"{collection}[{index}]: {message}")

    def _as_int_required(
        value: Any,
        *,
        collection: str,
        index: int,
        field: str,
        minimum: int = 1,
    ) -> int:
        try:
            parsed = int(value)
        except Exception as exc:
            raise _item_error(collection, index, f"{field} must be an integer.") from exc
        if parsed < minimum:
            raise _item_error(collection, index, f"{field} must be >= {minimum}.")
        return parsed

    def _as_int_optional(
        value: Any,
        *,
        collection: str,
        index: int,
        field: str,
        minimum: int = 1,
    ) -> Optional[int]:
        if value is None or value == "":
            return None
        return _as_int_required(
            value, collection=collection, index=index, field=field, minimum=minimum
        )

    def _as_str_required(value: Any, *, collection: str, index: int, field: str) -> str:
        s = str(value or "").strip()
        if not s:
            raise _item_error(collection, index, f"{field} is required.")
        return s

    def _as_str_default(value: Any, *, default: str) -> str:
        s = str(value if value is not None else "").strip()
        return s or default

    def _as_bool(value: Any, *, collection: str, index: int, field: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
            raise _item_error(collection, index, f"{field} must be a boolean.")
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
        raise _item_error(collection, index, f"{field} must be a boolean.")

    imported = {"prompt_templates": 0, "classification_sets": 0, "inboxes": 0, "app_models": 0}
    with db.get_connection() as conn:
        prompt_id_map: dict[int, int] = {}
        set_id_map: dict[int, int] = {}
        model_id_map: dict[int, int] = {}
        existing_prompt_ids = {int(x["id"]) for x in db.list_prompt_templates(conn)}
        existing_set_ids = {int(x["id"]) for x in db.list_classification_sets(conn)}
        existing_model_ids = {int(x["id"]) for x in db.list_app_models(conn)}
        existing_inbox_ids = {int(x["id"]) for x in db.list_inboxes(conn)}

        # --- Prompt templates ---
        for idx, pt in enumerate(payload.prompt_templates):
            if not isinstance(pt, dict):
                raise _item_error("prompt_templates", idx, "item must be an object.")
            source_id = _as_int_optional(
                pt.get("id"),
                collection="prompt_templates",
                index=idx,
                field="id",
            )
            name = _as_str_required(
                pt.get("name"),
                collection="prompt_templates",
                index=idx,
                field="name",
            )
            body = str(pt.get("body") if pt.get("body") is not None else "")
            if source_id is not None and source_id in existing_prompt_ids:
                db.update_prompt_template(conn, source_id, name, body)
                actual_id = source_id
            else:
                actual_id = db.create_prompt_template(conn, name, body)
                existing_prompt_ids.add(int(actual_id))
            if source_id is not None:
                prompt_id_map[source_id] = int(actual_id)
            imported["prompt_templates"] += 1

        # --- Classification sets (with categories) ---
        for idx, cs in enumerate(payload.classification_sets):
            if not isinstance(cs, dict):
                raise _item_error("classification_sets", idx, "item must be an object.")
            source_id = _as_int_optional(
                cs.get("id"),
                collection="classification_sets",
                index=idx,
                field="id",
            )
            name = _as_str_required(
                cs.get("name"),
                collection="classification_sets",
                index=idx,
                field="name",
            )
            if source_id is not None and source_id in existing_set_ids:
                db.update_classification_set(conn, source_id, name)
                actual_id = source_id
            else:
                actual_id = db.create_classification_set(conn, name)
                existing_set_ids.add(int(actual_id))

            cats_raw = cs.get("categories", [])
            if cats_raw is None:
                cats_raw = []
            if not isinstance(cats_raw, list):
                raise _item_error("classification_sets", idx, "categories must be a list.")
            clean_cats: list[dict[str, str]] = []
            for cat_idx, cat in enumerate(cats_raw):
                if not isinstance(cat, dict):
                    raise _item_error(
                        "classification_sets", idx, f"categories[{cat_idx}] must be an object."
                    )
                cat_name = str(cat.get("name", "")).strip()
                if not cat_name:
                    raise _item_error(
                        "classification_sets",
                        idx,
                        f"categories[{cat_idx}].name is required.",
                    )
                clean_cats.append(
                    {
                        "name": cat_name,
                        "description": str(cat.get("description", "")).strip(),
                    }
                )
            if clean_cats:
                db.replace_categories(conn, int(actual_id), clean_cats)

            if source_id is not None:
                set_id_map[source_id] = int(actual_id)
            imported["classification_sets"] += 1

        # --- App models ---
        for idx, am in enumerate(payload.app_models):
            if not isinstance(am, dict):
                raise _item_error("app_models", idx, "item must be an object.")
            source_id = _as_int_optional(
                am.get("id"),
                collection="app_models",
                index=idx,
                field="id",
            )
            name = _as_str_required(
                am.get("name"),
                collection="app_models",
                index=idx,
                field="name",
            )
            if source_id is not None and source_id in existing_model_ids:
                actual_id = source_id
            else:
                actual_id = db.create_app_model(conn, name)
                existing_model_ids.add(int(actual_id))
            if source_id is not None:
                model_id_map[source_id] = int(actual_id)
            imported["app_models"] += 1

        # --- Inboxes ---
        for idx, inv in enumerate(payload.inboxes):
            if not isinstance(inv, dict):
                raise _item_error("inboxes", idx, "item must be an object.")
            source_id = _as_int_optional(
                inv.get("id"),
                collection="inboxes",
                index=idx,
                field="id",
            )
            mailbox_id = _as_str_required(
                inv.get("mailbox_id"),
                collection="inboxes",
                index=idx,
                field="mailbox_id",
            )
            prompt_template_id = _as_int_required(
                inv.get("prompt_template_id"),
                collection="inboxes",
                index=idx,
                field="prompt_template_id",
            )
            prompt_template_id = prompt_id_map.get(prompt_template_id, prompt_template_id)
            if prompt_template_id not in existing_prompt_ids:
                raise _item_error(
                    "inboxes",
                    idx,
                    f"prompt_template_id {prompt_template_id} does not exist in destination.",
                )
            classification_set_id = _as_int_required(
                inv.get("classification_set_id"),
                collection="inboxes",
                index=idx,
                field="classification_set_id",
            )
            classification_set_id = set_id_map.get(classification_set_id, classification_set_id)
            if classification_set_id not in existing_set_ids:
                raise _item_error(
                    "inboxes",
                    idx,
                    f"classification_set_id {classification_set_id} does not exist in destination.",
                )
            app_model_id = _as_int_optional(
                inv.get("app_model_id"),
                collection="inboxes",
                index=idx,
                field="app_model_id",
            )
            if app_model_id is not None:
                app_model_id = model_id_map.get(app_model_id, app_model_id)
                if app_model_id not in existing_model_ids:
                    raise _item_error(
                        "inboxes",
                        idx,
                        f"app_model_id {app_model_id} does not exist in destination.",
                    )
            timezone = _as_str_default(inv.get("timezone"), default="UTC")
            mail_folder = _as_str_default(inv.get("mail_folder"), default="inbox")
            max_messages_per_run = _as_int_optional(
                inv.get("max_messages_per_run"),
                collection="inboxes",
                index=idx,
                field="max_messages_per_run",
            )
            patch_max_workers = _as_int_required(
                inv.get("patch_max_workers", 4),
                collection="inboxes",
                index=idx,
                field="patch_max_workers",
            )
            polling_interval_minutes = _as_int_required(
                inv.get("polling_interval_minutes", 5),
                collection="inboxes",
                index=idx,
                field="polling_interval_minutes",
            )
            is_active = _as_bool(
                inv.get("is_active", True),
                collection="inboxes",
                index=idx,
                field="is_active",
            )
            graph_write_back_enabled = _as_bool(
                inv.get("graph_write_back_enabled", True),
                collection="inboxes",
                index=idx,
                field="graph_write_back_enabled",
            )
            subject_classify_enabled = _as_bool(
                inv.get("subject_classify_enabled", False),
                collection="inboxes",
                index=idx,
                field="subject_classify_enabled",
            )

            ff_json = None
            ff = inv.get("fetch_filter")
            if ff is not None:
                if isinstance(ff, str):
                    try:
                        ff_obj = json.loads(ff)
                    except Exception as exc:
                        raise _item_error("inboxes", idx, "fetch_filter must be valid JSON.") from exc
                elif isinstance(ff, dict):
                    ff_obj = ff
                else:
                    raise _item_error("inboxes", idx, "fetch_filter must be an object or JSON string.")
                try:
                    ff_json = InboxFetchFilter.model_validate(ff_obj).model_dump_json()
                except Exception as exc:
                    raise _item_error("inboxes", idx, f"invalid fetch_filter: {exc}") from exc

            sc_rules_raw = inv.get("subject_classify_rules", [])
            if sc_rules_raw is None:
                sc_rules_raw = []
            if not isinstance(sc_rules_raw, list):
                raise _item_error("inboxes", idx, "subject_classify_rules must be a list.")
            parsed_rules: list[SubjectClassifyRule] = []
            for ridx, rule in enumerate(sc_rules_raw):
                try:
                    parsed_rules.append(SubjectClassifyRule.model_validate(rule))
                except Exception as exc:
                    raise _item_error(
                        "inboxes",
                        idx,
                        f"subject_classify_rules[{ridx}] is invalid: {exc}",
                    ) from exc
            _validate_subject_rules_against_set(
                conn,
                classification_set_id,
                subject_classify_enabled,
                parsed_rules,
            )
            sc_rules_json = _subject_rules_json(parsed_rules)

            if source_id is not None and source_id in existing_inbox_ids:
                db.update_inbox(
                    conn,
                    inbox_id=source_id,
                    mailbox_id=mailbox_id,
                    prompt_template_id=prompt_template_id,
                    classification_set_id=classification_set_id,
                    app_model_id=app_model_id,
                    timezone=timezone,
                    mail_folder=mail_folder,
                    max_messages_per_run=max_messages_per_run,
                    patch_max_workers=patch_max_workers,
                    polling_interval_minutes=polling_interval_minutes,
                    is_active=is_active,
                    graph_write_back_enabled=graph_write_back_enabled,
                    fetch_filter_json=ff_json,
                    subject_classify_enabled=subject_classify_enabled,
                    subject_classify_rules_json=sc_rules_json,
                )
            else:
                db.create_inbox(
                    conn,
                    mailbox_id=mailbox_id,
                    prompt_template_id=prompt_template_id,
                    classification_set_id=classification_set_id,
                    app_model_id=app_model_id,
                    timezone=timezone,
                    mail_folder=mail_folder,
                    max_messages_per_run=max_messages_per_run,
                    patch_max_workers=patch_max_workers,
                    polling_interval_minutes=polling_interval_minutes,
                    is_active=is_active,
                    graph_write_back_enabled=graph_write_back_enabled,
                    fetch_filter_json=ff_json,
                    subject_classify_enabled=subject_classify_enabled,
                    subject_classify_rules_json=sc_rules_json,
                )
            imported["inboxes"] += 1

    return {"imported": imported}


# --- Agentic Workflows ---


class FunctionParameterSchema(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = "string"
    description: str = ""
    required: bool = False


class FunctionDeclarationSchema(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    parameters: List[FunctionParameterSchema] = Field(default_factory=list)


class AgenticWorkflowCreate(BaseModel):
    inbox_id: int = Field(..., ge=1)
    name: str = ""
    extraction_prompt_id: int = Field(..., ge=1)
    response_prompt_id: Optional[int] = None
    workflow_filter: Optional[InboxFetchFilter] = None
    trigger_categories: List[str] = Field(..., min_length=1)
    function_declarations: List[FunctionDeclarationSchema] = Field(default_factory=list)
    agent_api_names: List[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    auto_send: bool = False
    is_active: bool = True


class AgenticWorkflowUpdate(BaseModel):
    inbox_id: int = Field(..., ge=1)
    name: str = ""
    extraction_prompt_id: int = Field(..., ge=1)
    response_prompt_id: Optional[int] = None
    workflow_filter: Optional[InboxFetchFilter] = None
    trigger_categories: List[str] = Field(..., min_length=1)
    function_declarations: List[FunctionDeclarationSchema] = Field(default_factory=list)
    agent_api_names: List[str] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    auto_send: bool = False
    is_active: bool = True


class DryRunRequest(BaseModel):
    """Optional mock email for dry-run; if omitted, uses default test data."""
    subject: str = "Test ETA Update"
    sender: str = "dispatch@example.com"
    body: str = "Order #12345, BOL 67890. ETA is 3pm today. Truck T-100, Trailer TL-200."


@protected.get("/agentic-workflows")
def list_agentic_workflows() -> List[dict[str, Any]]:
    with db.get_connection() as conn:
        return db.list_agentic_workflows(conn)


@protected.get("/agentic-workflows/{workflow_id}")
def get_agentic_workflow(workflow_id: int) -> dict[str, Any]:
    with db.get_connection() as conn:
        row = db.get_agentic_workflow(conn, workflow_id)
    if not row:
        raise HTTPException(status_code=404, detail="Agentic workflow not found.")
    return row


@protected.post("/agentic-workflows", status_code=201)
def create_agentic_workflow(payload: AgenticWorkflowCreate) -> dict[str, int]:
    func_decls = [fd.model_dump() for fd in payload.function_declarations]
    try:
        with db.get_connection() as conn:
            new_id = db.create_agentic_workflow(
                conn,
                inbox_id=payload.inbox_id,
                name=payload.name.strip(),
                extraction_prompt_id=payload.extraction_prompt_id,
                trigger_categories_json=json.dumps(payload.trigger_categories),
                function_declarations_json=json.dumps(func_decls) if func_decls else None,
                agent_api_names_json=json.dumps(payload.agent_api_names),
                webhook_url=(payload.webhook_url or "").strip() or None,
                workflow_filter_json=(payload.workflow_filter.model_dump_json() if payload.workflow_filter is not None else None),
                response_prompt_id=payload.response_prompt_id,
                auto_send=payload.auto_send,
                is_active=payload.is_active,
            )
        return {"id": new_id}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Invalid inbox or prompt reference.") from e
        raise


@protected.put("/agentic-workflows/{workflow_id}")
def update_agentic_workflow(workflow_id: int, payload: AgenticWorkflowUpdate) -> dict[str, str]:
    func_decls = [fd.model_dump() for fd in payload.function_declarations]
    try:
        with db.get_connection() as conn:
            existing = db.get_agentic_workflow(conn, workflow_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Agentic workflow not found.")
            db.update_agentic_workflow(
                conn,
                workflow_id,
                inbox_id=payload.inbox_id,
                name=payload.name.strip(),
                extraction_prompt_id=payload.extraction_prompt_id,
                trigger_categories_json=json.dumps(payload.trigger_categories),
                function_declarations_json=json.dumps(func_decls) if func_decls else None,
                agent_api_names_json=json.dumps(payload.agent_api_names),
                webhook_url=(payload.webhook_url or "").strip() or None,
                workflow_filter_json=(payload.workflow_filter.model_dump_json() if payload.workflow_filter is not None else None),
                response_prompt_id=payload.response_prompt_id,
                auto_send=payload.auto_send,
                is_active=payload.is_active,
            )
        return {"status": "ok"}
    except Exception as e:
        if db.is_integrity_error(e):
            raise _integrity("Invalid inbox or prompt reference.") from e
        raise


@protected.delete("/agentic-workflows/{workflow_id}")
def delete_agentic_workflow(workflow_id: int) -> dict[str, str]:
    with db.get_connection() as conn:
        existing = db.get_agentic_workflow(conn, workflow_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Agentic workflow not found.")
        db.delete_agentic_workflow(conn, workflow_id)
    return {"status": "ok"}


@protected.post("/agentic-workflows/{workflow_id}/dry-run")
def dry_run_agentic_workflow(workflow_id: int, payload: DryRunRequest) -> dict[str, Any]:
    """
    Simulate extraction on a mock email without calling external APIs.
    Returns the extracted data and the API payload that would be sent.
    """
    from ..agent_workflow.orchestrator import extract_with_function_calling

    with db.get_connection() as conn:
        wf = db.get_agentic_workflow(conn, workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail="Agentic workflow not found.")
        # Load extraction prompt body
        prompts = db.list_prompt_templates(conn)
        prompt_row = next(
            (p for p in prompts if int(p["id"]) == int(wf["extraction_prompt_id"])), None
        )
        if not prompt_row:
            raise HTTPException(status_code=404, detail="Extraction prompt not found.")
        # Load inbox for mailbox config
        inbox_row = db.get_inbox_by_id(conn, int(wf["inbox_id"]))
        if not inbox_row:
            raise HTTPException(status_code=404, detail="Linked inbox not found.")

    extraction_prompt_body = prompt_row.get("body", "")
    func_decls = wf.get("function_declarations", [])

    mock_email: dict[str, Any] = {
        "id": "dry-run-00000000-0000-0000-0000-000000000001",
        "subject": payload.subject,
        "sender": {"emailAddress": {"address": payload.sender}},
        "receivedDateTime": None,
        "bodyPreview": payload.body,
    }

    email_summary = {
        "subject": payload.subject,
        "sender": payload.sender,
        "body_preview": payload.body[:500],
    }

    if not func_decls:
        return {
            "email": email_summary,
            "extracted_data": {},
            "api_payload_preview": {},
            "error": "No function declarations configured for this workflow.",
        }

    try:
        # Build a minimal mailbox config for model resolution
        mailbox_config = None
        try:
            from ..config.db_loader import _row_to_config
            mailbox_config = _row_to_config(inbox_row)
        except Exception:
            pass

        extracted = extract_with_function_calling(
            mock_email, extraction_prompt_body, func_decls, mailbox_config
        )
    except ValueError as e:
        msg = str(e)
        if any(x in msg for x in ("VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_API_KEY")):
            raise HTTPException(status_code=503, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e
    except Exception as e:
        return {
            "email": email_summary,
            "extracted_data": {},
            "api_payload_preview": {},
            "error": str(e),
        }

    api_payload = {
        "email_id": mock_email["id"],
        "mailbox_id": inbox_row.get("mailbox_id", ""),
        "category": wf.get("trigger_categories", ["unknown"])[0],
        "extracted_data": extracted,
        "subject": payload.subject,
        "sender": payload.sender,
        "received_date_time": None,
    }

    return {
        "email": email_summary,
        "extracted_data": extracted,
        "api_payload_preview": api_payload,
        "error": None,
    }


@app.on_event("startup")
def startup() -> None:
    db.init_db()


app.include_router(public)
app.include_router(auth_router, prefix="/api")
app.include_router(protected)


def create_app() -> FastAPI:
    return app
