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
    patch_max_workers: int = Field(default=4, ge=1, le=10)
    polling_interval_minutes: int = Field(default=5, ge=1, le=1440)
    is_active: bool = True
    graph_write_back_enabled: bool = True
    fetch_filter: Optional[InboxFetchFilter] = None
    subject_classify_enabled: bool = False
    subject_classify_rules: List[SubjectClassifyRule] = Field(default_factory=list)
    eta_lookup_enabled: bool = False
    eta_lookup_api_url: Optional[str] = None
    eta_lookup_api_key: Optional[str] = None
    eta_draft_enabled: bool = True


class InboxUpdate(BaseModel):
    mailbox_id: str = Field(..., min_length=1)
    prompt_template_id: int
    classification_set_id: int
    app_model_id: Optional[int] = None
    timezone: str = "UTC"
    mail_folder: str = "inbox"
    max_messages_per_run: Optional[int] = 500
    patch_max_workers: int = Field(default=4, ge=1, le=10)
    polling_interval_minutes: int = Field(default=5, ge=1, le=1440)
    is_active: bool = True
    graph_write_back_enabled: bool = True
    fetch_filter: InboxFetchFilter = Field(default_factory=InboxFetchFilter)
    subject_classify_enabled: bool = False
    subject_classify_rules: List[SubjectClassifyRule] = Field(default_factory=list)
    eta_lookup_enabled: bool = False
    eta_lookup_api_url: Optional[str] = None
    eta_lookup_api_key: Optional[str] = None
    eta_draft_enabled: bool = True


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
                eta_lookup_enabled=payload.eta_lookup_enabled,
                eta_lookup_api_url=payload.eta_lookup_api_url,
                eta_lookup_api_key=payload.eta_lookup_api_key,
                eta_draft_enabled=payload.eta_draft_enabled,
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
                eta_lookup_enabled=payload.eta_lookup_enabled,
                eta_lookup_api_url=payload.eta_lookup_api_url,
                eta_lookup_api_key=payload.eta_lookup_api_key,
                eta_draft_enabled=payload.eta_draft_enabled,
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
    from ..jobs.run_lock import try_acquire_run_lock, is_run_lock_held

    with db.get_connection() as conn:
        inbox = db.get_inbox_by_id(conn, inbox_id)
    if not inbox:
        raise HTTPException(status_code=404, detail="Inbox not found.")
    if not inbox.get("is_active"):
        raise HTTPException(status_code=400, detail="Inbox is not active")

    # Check for an existing run lock (conflict detection)
    if not db.is_demo_mode() and is_run_lock_held(inbox_id):
        raise HTTPException(status_code=409, detail="A run is already in progress for this inbox")

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

    result: dict[str, Any] = {"status": metrics.status.lower()}
    if metrics.status == "Success":
        result["run_id"] = metrics.run_id
        result["status"] = "completed"
    return result


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
    """Upsert configuration data from JSON. For each entity, check if ID exists → update, else create."""
    imported = {"prompt_templates": 0, "classification_sets": 0, "inboxes": 0, "app_models": 0}
    with db.get_connection() as conn:
        # --- Prompt templates ---
        for pt in payload.prompt_templates:
            pt_id = pt.get("id")
            existing = None
            if pt_id is not None:
                for existing_pt in db.list_prompt_templates(conn):
                    if int(existing_pt["id"]) == int(pt_id):
                        existing = existing_pt
                        break
            try:
                if existing:
                    db.update_prompt_template(conn, int(pt_id), str(pt.get("name", "")), str(pt.get("body", "")))
                else:
                    db.create_prompt_template(conn, str(pt.get("name", "")), str(pt.get("body", "")))
                imported["prompt_templates"] += 1
            except Exception:
                pass

        # --- Classification sets (with categories) ---
        for cs in payload.classification_sets:
            cs_id = cs.get("id")
            existing = None
            if cs_id is not None:
                for existing_cs in db.list_classification_sets(conn):
                    if int(existing_cs["id"]) == int(cs_id):
                        existing = existing_cs
                        break
            try:
                if existing:
                    db.update_classification_set(conn, int(cs_id), str(cs.get("name", "")))
                else:
                    cs_id = db.create_classification_set(conn, str(cs.get("name", "")))
                # Upsert categories
                cats = cs.get("categories", [])
                if cats:
                    clean_cats = [{"name": c.get("name", ""), "description": c.get("description", "")} for c in cats if c.get("name")]
                    if clean_cats:
                        db.replace_categories(conn, int(cs_id), clean_cats)
                imported["classification_sets"] += 1
            except Exception:
                pass

        # --- App models ---
        for am in payload.app_models:
            am_id = am.get("id")
            existing = None
            if am_id is not None:
                for existing_am in db.list_app_models(conn):
                    if int(existing_am["id"]) == int(am_id):
                        existing = existing_am
                        break
            try:
                if existing:
                    # App model has no update function, skip if exists
                    pass
                else:
                    db.create_app_model(conn, str(am.get("name", "")))
                imported["app_models"] += 1
            except Exception:
                pass

        # --- Inboxes ---
        for inv in payload.inboxes:
            inv_id = inv.get("id")
            existing = None
            if inv_id is not None:
                row = db.get_inbox_by_id(conn, int(inv_id))
                if row:
                    existing = row
            try:
                ff_json = None
                ff = inv.get("fetch_filter")
                if ff is not None:
                    if isinstance(ff, str):
                        ff_json = ff
                    elif isinstance(ff, dict):
                        ff_json = json.dumps(ff)
                sc_rules = inv.get("subject_classify_rules", [])
                sc_rules_json = json.dumps(sc_rules) if sc_rules else None

                if existing:
                    db.update_inbox(
                        conn,
                        inbox_id=int(inv_id),
                        mailbox_id=str(inv.get("mailbox_id", "")),
                        prompt_template_id=int(inv.get("prompt_template_id", 0)),
                        classification_set_id=int(inv.get("classification_set_id", 0)),
                        app_model_id=inv.get("app_model_id"),
                        timezone=str(inv.get("timezone", "UTC")),
                        mail_folder=str(inv.get("mail_folder", "inbox")),
                        max_messages_per_run=inv.get("max_messages_per_run"),
                        patch_max_workers=int(inv.get("patch_max_workers", 4)),
                        polling_interval_minutes=int(inv.get("polling_interval_minutes", 5)),
                        is_active=bool(inv.get("is_active", True)),
                        graph_write_back_enabled=bool(inv.get("graph_write_back_enabled", True)),
                        fetch_filter_json=ff_json,
                        subject_classify_enabled=bool(inv.get("subject_classify_enabled", False)),
                        subject_classify_rules_json=sc_rules_json,
                        eta_lookup_enabled=bool(inv.get("eta_lookup_enabled", False)),
                        eta_lookup_api_url=inv.get("eta_lookup_api_url"),
                        eta_lookup_api_key=inv.get("eta_lookup_api_key"),
                        eta_draft_enabled=bool(inv.get("eta_draft_enabled", True)),
                    )
                else:
                    db.create_inbox(
                        conn,
                        mailbox_id=str(inv.get("mailbox_id", "")),
                        prompt_template_id=int(inv.get("prompt_template_id", 0)),
                        classification_set_id=int(inv.get("classification_set_id", 0)),
                        app_model_id=inv.get("app_model_id"),
                        timezone=str(inv.get("timezone", "UTC")),
                        mail_folder=str(inv.get("mail_folder", "inbox")),
                        max_messages_per_run=inv.get("max_messages_per_run"),
                        patch_max_workers=int(inv.get("patch_max_workers", 4)),
                        polling_interval_minutes=int(inv.get("polling_interval_minutes", 5)),
                        is_active=bool(inv.get("is_active", True)),
                        graph_write_back_enabled=bool(inv.get("graph_write_back_enabled", True)),
                        fetch_filter_json=ff_json,
                        subject_classify_enabled=bool(inv.get("subject_classify_enabled", False)),
                        subject_classify_rules_json=sc_rules_json,
                        eta_lookup_enabled=bool(inv.get("eta_lookup_enabled", False)),
                        eta_lookup_api_url=inv.get("eta_lookup_api_url"),
                        eta_lookup_api_key=inv.get("eta_lookup_api_key"),
                        eta_draft_enabled=bool(inv.get("eta_draft_enabled", True)),
                    )
                imported["inboxes"] += 1
            except Exception:
                pass

    return {"imported": imported}


@app.on_event("startup")
def startup() -> None:
    db.init_db()


app.include_router(public)
app.include_router(auth_router, prefix="/api")
app.include_router(protected)


def create_app() -> FastAPI:
    return app
