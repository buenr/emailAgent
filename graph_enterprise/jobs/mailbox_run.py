"""
Orchestration sketch: auth → fetch unread-for-day → preprocess → classify → write-back.

Wire Vertex/Gemini calls using the same patterns as inbox_classifier.py; this module
stays dependency-light and documents the control flow for Part 3.
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from ..auth.token import GraphTokenProvider, MsalClientCredentialsConfig
from ..classification.gemini_category_batch import (
    DEFAULT_GEMINI_MODEL,
    body_text_for_classification,
    classify_messages_subject_then_ai,
    effective_gemini_model_from_env,
)
from ..classification.subject_rules import partition_messages_by_subject_rules
from ..classification.schema_from_config import build_classification_json_schema
from ..config.default_categories import DEFAULT_CATEGORIES
from ..config.db_loader import (
    load_mailbox_config_by_inbox_id,
    load_mailbox_config_from_db,
)
from ..agent_workflow import run_agent_workflow
from ..ui import db as db_store
from ..config.models import FetchTimeWindowMode, InboxFetchFilter, MailboxPipelineConfig, RunPolicy
from ..microsoft_graph.fetch import GraphMessageFetcher
from ..microsoft_graph.http_client import GraphHttpClient
from ..microsoft_graph.writeback import outlook_category_label, patch_message_categories
from ..observability.run_log import RunMetrics, RunTimer, emit_run_record, utc_now_iso

logger = logging.getLogger(__name__)

_graph_token_provider_lock = threading.Lock()
_graph_token_provider: Optional[GraphTokenProvider] = None
_graph_token_provider_key: Optional[Tuple[str, str, str]] = None


def _local_day_bounds_utc(timezone_name: str, day: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Interpret 'today' in mailbox TZ; return UTC interval [start, end)."""
    tz = ZoneInfo(timezone_name)
    now = day or datetime.now(tz)
    local_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = local_midnight
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def _effective_fetch_filter_for_run(mailbox: MailboxPipelineConfig) -> InboxFetchFilter:
    """
    When fetching read+unread mail, Graph returns the same messages on every poll unless we
    exclude items already tagged with this inbox's classification labels.
    Names listed in ``category_include_any`` are not auto-excluded so explicit include rules stay satisfiable.
    """
    ff = mailbox.fetch_filter
    if ff.unread_only:
        return ff
    include_norm = {x.strip() for x in ff.category_include_any if x and str(x).strip()}
    names = [
        c.name.strip()
        for c in mailbox.categories
        if c.name and str(c.name).strip() and c.name.strip() not in include_norm
    ]
    if not names:
        return ff
    merged: List[str] = []
    seen: set[str] = set()
    for x in list(ff.category_exclude_any) + names:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        merged.append(k)
    return ff.model_copy(update={"category_exclude_any": merged})


def _fetch_window_utc(
    mailbox: MailboxPipelineConfig,
    reference_day: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    """Compute [start, end) UTC for Graph receivedDateTime from inbox fetch_filter."""
    ff = mailbox.fetch_filter
    if ff.time_window_mode == FetchTimeWindowMode.local_today:
        return _local_day_bounds_utc(mailbox.run_policy.timezone, reference_day)
    end_utc = datetime.now(timezone.utc)
    if ff.time_window_mode == FetchTimeWindowMode.rolling_hours:
        hours = float(ff.rolling_hours or 24)
        start_utc = end_utc - timedelta(hours=hours)
        return start_utc, end_utc
    # since_last_run
    if mailbox.last_run_at is not None:
        start_utc = mailbox.last_run_at.astimezone(timezone.utc)
        if start_utc >= end_utc:
            start_utc = end_utc - timedelta(hours=1)
        return start_utc, end_utc
    start_utc = end_utc - timedelta(hours=24)
    return start_utc, end_utc


def run_fetch_only(
    mailbox: MailboxPipelineConfig,
    token_provider: GraphTokenProvider,
    reference_day: Optional[datetime] = None,
    graph_client: Optional[GraphHttpClient] = None,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch unread messages for the configured local calendar day (no AI).

    Returns ``(messages, first_graph_request_id)`` from the initial list response.
    """
    own_client = graph_client is None
    client = graph_client or GraphHttpClient(token_provider.acquire_token)
    try:
        fetcher = GraphMessageFetcher(client)
        start_utc, end_utc = _fetch_window_utc(mailbox, reference_day)
        cap = mailbox.run_policy.max_messages_per_run
        ff = mailbox.fetch_filter
        fetch_ff = _effective_fetch_filter_for_run(mailbox)
        messages = list(
            fetcher.iter_messages_for_interval(
                mailbox.mailbox_id,
                start_utc,
                end_utc,
                unread_only=ff.unread_only,
                max_messages=cap,
                mail_folder=mailbox.run_policy.mail_folder,
                fetch_filter=fetch_ff,
            )
        )
        return messages, fetcher.first_request_id
    finally:
        if own_client:
            client.close()


def run_fetch_last_hours(
    mailbox: MailboxPipelineConfig,
    token_provider: GraphTokenProvider,
    hours: float,
    *,
    unread_only: bool = False,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch messages received in the last ``hours`` (UTC window ending now).

    Returns ``(messages, first_graph_request_id)`` from the initial list response.
    """
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=hours)
    client = GraphHttpClient(token_provider.acquire_token)
    try:
        fetcher = GraphMessageFetcher(client)
        cap = mailbox.run_policy.max_messages_per_run
        fetch_ff = (
            _effective_fetch_filter_for_run(mailbox)
            if not unread_only
            else mailbox.fetch_filter
        )
        messages = list(
            fetcher.iter_messages_for_interval(
                mailbox.mailbox_id,
                start_utc,
                end_utc,
                unread_only=unread_only,
                max_messages=cap,
                mail_folder=mailbox.run_policy.mail_folder,
                fetch_filter=fetch_ff,
            )
        )
        return messages, fetcher.first_request_id
    finally:
        client.close()


def _persist_run_to_db(inbox_id: int, metrics: RunMetrics) -> None:
    with db_store.get_connection() as conn:
        run_log_id = db_store.insert_run_log(
            conn,
            inbox_id=inbox_id,
            status=metrics.status,
            fetched_count=metrics.fetched_count,
            classified_count=metrics.classified_count,
            tagged_count=metrics.tagged_count,
            failures=metrics.failures,
            latency_ms=metrics.latency_ms,
            total_tokens_used=metrics.total_tokens_used,
            error_message=metrics.error_message,
        )
        if metrics.classifications:
            db_store.insert_message_classifications(
                conn, run_log_id, metrics.classifications
            )
        now = utc_now_iso()
        nxt = db_store.compute_next_run_iso(conn, inbox_id)
        db_store.update_inbox_run_times(conn, inbox_id, last_run_at=now, next_run_at=nxt)


def run_pipeline_stub(
    mailbox: MailboxPipelineConfig,
    token_provider: GraphTokenProvider,
    classify_batch: Optional[Callable[[List[Dict[str, Any]], Dict[str, Any]], List[Dict[str, Any]]]] = None,
    model_id: str = DEFAULT_GEMINI_MODEL,
    prompt_version: str = "0",
    messages: Optional[List[Dict[str, Any]]] = None,
    predictions: Optional[List[Dict[str, Any]]] = None,
    apply_write_back: bool = True,
    run_id: Optional[str] = None,
    *,
    total_tokens_used: Optional[int] = None,
    persist_inbox_id: Optional[int] = None,
) -> RunMetrics:
    """
    Fetch (unless ``messages`` provided), classify, optionally PATCH categories on Graph.

    classify_batch: (messages, json_schema) -> list of dicts with keys
    ``email_id`` and ``category``.

    If ``predictions`` is set, it is used instead of calling ``classify_batch``.

    ``persist_inbox_id``: when set, writes ``run_log`` and updates ``last_run_at`` /
    ``next_run_at`` on the inbox row in SQL Server.
    """
    timer = RunTimer()
    started = utc_now_iso()
    schema = build_classification_json_schema(mailbox)
    messages_work: List[Dict[str, Any]] = []
    final_run_id = run_id or str(uuid.uuid4())
    fetched = 0
    pred_list: List[Dict[str, Any]] = []
    tagged = 0
    failures = 0
    histogram: Dict[str, int] = {}
    record_classifications: List[Dict[str, Any]] = []
    truncated = False
    status = "Success"
    error_message: Optional[str] = None

    client = GraphHttpClient(token_provider.acquire_token)
    try:
        try:
            graph_first_request_id: Optional[str] = None
            if messages is None:
                messages_work, graph_first_request_id = run_fetch_only(
                    mailbox, token_provider, graph_client=client
                )
            else:
                messages_work = list(messages)

            final_run_id = run_id or graph_first_request_id or final_run_id

            fetched = len(messages_work)
            truncated = bool(
                mailbox.run_policy.max_messages_per_run is not None
                and fetched >= mailbox.run_policy.max_messages_per_run
            )

            if predictions is not None:
                pred_list = list(predictions)
            elif classify_batch:
                pred_list = classify_batch(messages_work, schema)
            else:
                pred_list = []

            patch_tasks: List[tuple[str, str, List[str]]] = []

            for pred in pred_list:
                mid = pred.get("email_id")
                cat = pred.get("category")
                if not mid or not cat:
                    failures += 1
                    continue

                msg = next((m for m in messages_work if m.get("id") == mid), None)
                if msg:
                    graph_preview = (
                        msg.get("body_preview")
                        if "body_preview" in msg
                        else msg.get("bodyPreview")
                    )
                    rec: Dict[str, Any] = {
                        "email_id": mid,
                        "category": cat,
                        "subject": msg.get("subject"),
                        "sender": (msg.get("sender") or {})
                        .get("emailAddress", {})
                        .get("address", "Unknown"),
                        "received": msg.get("receivedDateTime"),
                        "graph_body_preview": graph_preview,
                        "model_input_body": body_text_for_classification(msg),
                    }
                    if apply_write_back:
                        rec["outlook_category"] = outlook_category_label(cat)
                    record_classifications.append(rec)

                if apply_write_back:
                    existing = list((msg or {}).get("categories") or [])
                    patch_tasks.append((mid, outlook_category_label(cat), existing))
                else:
                    histogram[cat] = histogram.get(cat, 0) + 1

            if apply_write_back and patch_tasks:

                def _patch_one(task: tuple[str, str, List[str]]) -> tuple[bool, str]:
                    mid, cat, existing_cats = task
                    try:
                        patch_message_categories(
                            client,
                            mailbox.mailbox_id,
                            mid,
                            [cat],
                            merge_with_existing=True,
                            existing_categories=existing_cats,
                        )
                        return True, cat
                    except Exception as exc:
                        logger.warning(
                            "Graph write-back failed for message %s (category=%r): %s",
                            mid,
                            cat,
                            exc,
                        )
                        return False, cat

                workers = min(mailbox.run_policy.patch_max_workers, len(patch_tasks))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(pool.map(_patch_one, patch_tasks))
                for (ok, outlook_lbl), task in zip(results, patch_tasks):
                    if ok:
                        tagged += 1
                        histogram[outlook_lbl] = histogram.get(outlook_lbl, 0) + 1
                    else:
                        failures += 1

        except Exception as exc:
            logger.exception("Mailbox pipeline failed: %s", exc)
            status = "Failed"
            error_message = str(exc)
    finally:
        client.close()

    finished = utc_now_iso()
    metrics = RunMetrics(
        mailbox_id=mailbox.mailbox_id,
        run_id=final_run_id,
        started_at_utc=started,
        finished_at_utc=finished,
        fetched_count=fetched,
        classified_count=len(pred_list),
        tagged_count=tagged,
        failures=failures,
        latency_ms=timer.elapsed_ms(),
        model_id=model_id,
        prompt_version=prompt_version,
        category_histogram=histogram,
        classifications=record_classifications,
        truncated_by_policy=truncated,
        status=status,
        total_tokens_used=total_tokens_used,
        error_message=error_message,
    )
    if os.environ.get("EMIT_RUN_LOG_JSON", "1").strip().lower() not in ("0", "false", "no"):
        emit_run_record(metrics)
    if persist_inbox_id is not None:
        _persist_run_to_db(persist_inbox_id, metrics)
    return metrics


def _build_agentic_trigger_predictions(
    messages: List[Dict[str, Any]],
    trigger_categories: List[str],
) -> List[Dict[str, str]]:
    """Build trigger predictions from existing Outlook categories (independent of classifier output)."""
    preds: List[Dict[str, str]] = []
    clean_triggers = [str(x).strip() for x in trigger_categories if str(x).strip()]
    if not clean_triggers:
        return preds
    for msg in messages:
        mid = str(msg.get("id") or "").strip()
        if not mid:
            continue
        msg_cats = {
            str(c).strip().lower()
            for c in (msg.get("categories") or [])
            if str(c).strip()
        }
        if not msg_cats:
            continue
        matched: Optional[str] = None
        for trig in clean_triggers:
            trig_norm = trig.lower()
            prefixed = outlook_category_label(trig).lower()
            if trig_norm in msg_cats or prefixed in msg_cats:
                matched = trig
                break
        if matched:
            preds.append({"email_id": mid, "category": matched})
    return preds


def run_scheduled_agentic_pipeline(inbox_id: int) -> Dict[str, Any]:
    """
    Independent agentic workflow run:
    fetch messages by inbox filter, then trigger agentic only for messages already
    tagged/categorized for the configured trigger categories.
    """
    mailbox = load_mailbox_config_by_inbox_id(inbox_id)
    if not mailbox.is_active:
        raise ValueError(f"Inbox {inbox_id} is not active")
    if mailbox.inbox_id is None:
        raise ValueError(f"Inbox {inbox_id} has no persisted configuration id")

    with db_store.get_connection() as conn:
        aw_row = db_store.get_agentic_workflow_for_inbox(conn, mailbox.inbox_id)
        all_agent_configs = db_store.get_agent_api_configs(conn)
    if not aw_row or not aw_row.get("is_active"):
        raise ValueError(f"No active agentic workflow configured for inbox {inbox_id}")

    provider = _token_provider_from_env()
    client = GraphHttpClient(provider.acquire_token)
    try:
        messages, _ = run_fetch_only(mailbox, provider, graph_client=client)
        trigger_categories = list(aw_row.get("trigger_categories") or [])
        predictions = _build_agentic_trigger_predictions(messages, trigger_categories)
        aw_row["inbox_mailbox_id"] = mailbox.mailbox_id
        aw_prompt_body = aw_row.get("extraction_prompt_body", "")
        results = run_agent_workflow(
            aw_row,
            aw_prompt_body,
            messages,
            predictions,
            all_agent_configs,
            mailbox_config=mailbox,
            graph_client=client,
        )
    finally:
        client.close()

    success = sum(1 for r in results if r.success)
    failures = len(results) - success
    drafted = sum(1 for r in results if r.draft_id)
    return {
        "fetched_count": len(messages),
        "triggered_count": len(predictions),
        "processed_count": len(results),
        "success_count": success,
        "failure_count": failures,
        "drafted_count": drafted,
    }


def run_scheduled_mailbox_pipeline(
    inbox_id: int,
    *,
    apply_write_back: Optional[bool] = None,
) -> RunMetrics:
    """
    Calendar-day unread fetch → Gemini classify → optional Graph write-back → ``run_log`` / scheduling columns.

    Used by Celery workers; requires the same Vertex / Graph env vars as the CLI ``--classify`` path.

    Fetch and classify run inside a local try/except so Graph or Vertex failures still write ``run_log``
    and advance ``next_run_at`` (same as ``run_pipeline_stub``). Without that, a failing inbox would stay
    "due" and be re-enqueued every scheduler tick.
    """
    mailbox = load_mailbox_config_by_inbox_id(inbox_id)
    if not mailbox.is_active:
        raise ValueError(f"Inbox {inbox_id} is not active")
    do_write_back = (
        apply_write_back
        if apply_write_back is not None
        else mailbox.graph_write_back_enabled
    )
    provider = _token_provider_from_env()
    model_id = (
        mailbox.app_model.name
        if mailbox.app_model and (mailbox.app_model.name or "").strip()
        else None
    ) or effective_gemini_model_from_env()
    timer = RunTimer()
    started = utc_now_iso()
    messages: Optional[List[Dict[str, Any]]] = None
    try:
        messages, _ = run_fetch_only(mailbox, provider)
        if mailbox.subject_classify_enabled and mailbox.subject_classify_rules:
            _, for_ai = partition_messages_by_subject_rules(messages, mailbox)
            needs_ai = bool(for_ai)
        else:
            needs_ai = bool(messages)
        if needs_ai:
            _validate_vertex_env_for_classify()
        predictions, usage = classify_messages_subject_then_ai(messages, mailbox)
    except Exception as exc:
        logger.exception(
            "Scheduled mailbox pipeline failed before write-back (inbox_id=%s): %s",
            inbox_id,
            exc,
        )
        finished = utc_now_iso()
        metrics = RunMetrics(
            mailbox_id=mailbox.mailbox_id,
            run_id=str(uuid.uuid4()),
            started_at_utc=started,
            finished_at_utc=finished,
            fetched_count=len(messages) if messages is not None else 0,
            classified_count=0,
            tagged_count=0,
            failures=1,
            latency_ms=timer.elapsed_ms(),
            model_id=model_id,
            prompt_version="2",
            category_histogram={},
            classifications=[],
            truncated_by_policy=False,
            status="Failed",
            total_tokens_used=None,
            error_message=str(exc),
        )
        if os.environ.get("EMIT_RUN_LOG_JSON", "1").strip().lower() not in ("0", "false", "no"):
            emit_run_record(metrics)
        _persist_run_to_db(inbox_id, metrics)
        raise
    total_tok = int(usage["total_input_tokens"] or 0) + int(
        usage["total_output_tokens"] or 0
    )
    return run_pipeline_stub(
        mailbox,
        provider,
        classify_batch=None,
        model_id=model_id,
        prompt_version="2",
        messages=messages,
        predictions=predictions,
        apply_write_back=do_write_back,
        total_tokens_used=total_tok,
        persist_inbox_id=inbox_id,
    )


def _token_provider_from_env() -> GraphTokenProvider:
    """Return a process-wide ``GraphTokenProvider`` so MSAL keeps its in-memory token cache."""
    global _graph_token_provider, _graph_token_provider_key
    tenant = os.environ.get("AZURE_TENANT_ID", "").strip()
    cid = os.environ.get("AZURE_CLIENT_ID", "").strip()
    secret = os.environ.get("AZURE_CLIENT_SECRET", "").strip()
    missing = [
        name
        for name, val in (
            ("AZURE_TENANT_ID", tenant),
            ("AZURE_CLIENT_ID", cid),
            ("AZURE_CLIENT_SECRET", secret),
        )
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    key = (tenant, cid, secret)
    with _graph_token_provider_lock:
        if _graph_token_provider is not None and _graph_token_provider_key == key:
            return _graph_token_provider
        _graph_token_provider_key = key
        _graph_token_provider = GraphTokenProvider(
            MsalClientCredentialsConfig(tenant_id=tenant, client_id=cid, client_secret=secret)
        )
        return _graph_token_provider


def _validate_vertex_env_for_classify() -> None:
    """Fail fast before Graph fetch when Gemini classification is requested."""
    project = os.environ.get("VERTEX_PROJECT", "").strip()
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    api_key = os.environ.get("GOOGLE_CLOUD_API_KEY", "").strip()
    missing: List[str] = []
    if not project:
        missing.append("VERTEX_PROJECT")
    if not creds and not api_key:
        missing.append("GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CLOUD_API_KEY")
    if missing:
        raise RuntimeError(
            "Classification requires: "
            + ", ".join(missing)
            + ". Set them in the environment."
        )


def _mailbox_from_env() -> MailboxPipelineConfig:
    """
    TARGET_MAILBOX — user or shared mailbox SMTP/UPN for Graph.
    Defaults to Logistics/Trucking after-hours shared mailbox when unset or blank.

    Optional GRAPH_MAIL_FOLDER — well-known folder (default ``inbox``). Avoid ``all`` in
    scheduled runs: it uses ``/users/{{id}}/messages``, which spans Sent Items, Deleted
    Items, Junk, etc., and can waste tokens re-processing those folders.

    If ``MSSQL_ODBC_CONNECTION_STRING`` is set, categories and prompt come from the
    inbox row for ``TARGET_MAILBOX`` in SQL Server.

    Otherwise categories come from DEFAULT_CATEGORIES; run limits from env
    (GRAPH_MAILBOX_TZ, GRAPH_MAX_MESSAGES_PER_RUN). See default_categories.py to change buckets.
    """
    target = os.environ.get("TARGET_MAILBOX", "").strip()
    if os.environ.get("MSSQL_ODBC_CONNECTION_STRING", "").strip():
        if not target:
            raise RuntimeError(
                "TARGET_MAILBOX is required when MSSQL_ODBC_CONNECTION_STRING is set"
            )
        return load_mailbox_config_from_db(target)
    tz = os.environ.get("GRAPH_MAILBOX_TZ", "UTC").strip() or "UTC"
    max_raw = os.environ.get("GRAPH_MAX_MESSAGES_PER_RUN", "").strip()
    max_int: Optional[int] = int(max_raw) if max_raw.isdigit() else 500
    mail_folder = os.environ.get("GRAPH_MAIL_FOLDER", "inbox").strip() or "inbox"
    return MailboxPipelineConfig(
        mailbox_id=target,
        categories=list(DEFAULT_CATEGORIES),
        run_policy=RunPolicy(
            polling_interval_minutes=5,
            max_messages_per_run=max_int,
            timezone=tz,
            mail_folder=mail_folder,
        ),
    )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Microsoft Graph mailbox run: fetch, optional Gemini categories, optional write-back."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging (DEBUG): log each message subject and classification line.",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        metavar="N",
        help="Fetch messages received in the last N hours (UTC). Omit for calendar-day unread window.",
    )
    parser.add_argument(
        "--unread-only",
        action="store_true",
        help="With --hours, restrict to unread messages only.",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Classify with Vertex Gemini into mailbox categories (requires VERTEX_PROJECT, etc.).",
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help="PATCH Outlook categories via Graph (requires --classify).",
    )
    parser.add_argument(
        "--mail-folder",
        default=None,
        metavar="ID",
        help="Graph mail folder: well-known name (inbox, junkemail, …) or folder id. "
        "Default: run_policy.mail_folder / inbox. Use 'all' for entire mailbox.",
    )
    args = parser.parse_args()

    if args.write_back and not args.classify:
        parser.error("--write-back requires --classify")

    if args.classify:
        _validate_vertex_env_for_classify()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    provider = _token_provider_from_env()
    mailbox = _mailbox_from_env()
    if args.mail_folder is not None:
        rp = mailbox.run_policy.model_copy(update={"mail_folder": args.mail_folder.strip()})
        mailbox = mailbox.model_copy(update={"run_policy": rp})

    if str(mailbox.run_policy.mail_folder).strip().lower() == "all":
        logger.warning(
            "GRAPH_MAIL_FOLDER=all uses the entire mailbox (Sent/Deleted/Junk, etc.). "
            "Prefer a well-known folder such as inbox for routine runs."
        )

    if args.hours is not None:
        end_utc = datetime.now(timezone.utc)
        start_utc = end_utc - timedelta(hours=args.hours)
        logger.info("Mailbox: %s", mailbox.mailbox_id)
        logger.info("Graph folder: %s", mailbox.run_policy.mail_folder)
        logger.info(
            "Window (UTC): %s .. %s (%s h, unread_only=%s)",
            start_utc.isoformat(),
            end_utc.isoformat(),
            args.hours,
            args.unread_only,
        )
        messages, _ = run_fetch_last_hours(
            mailbox, provider, args.hours, unread_only=args.unread_only
        )
    else:
        start_utc, end_utc = _local_day_bounds_utc(mailbox.run_policy.timezone)
        logger.info("Mailbox: %s", mailbox.mailbox_id)
        logger.info("Graph folder: %s", mailbox.run_policy.mail_folder)
        logger.info(
            "Day window (UTC): %s .. %s (timezone=%s)",
            start_utc.isoformat(),
            end_utc.isoformat(),
            mailbox.run_policy.timezone,
        )
        messages, _ = run_fetch_only(mailbox, provider)

    logger.info("Fetched %s message(s).", len(messages))
    if args.verbose:
        for msg in messages:
            logger.debug("  - %s", msg.get("subject", ""))

    if not args.classify:
        return

    model_id = (
        mailbox.app_model.name
        if mailbox.app_model and (mailbox.app_model.name or "").strip()
        else None
    ) or effective_gemini_model_from_env()
    if mailbox.subject_classify_enabled and mailbox.subject_classify_rules:
        _, for_ai = partition_messages_by_subject_rules(messages, mailbox)
        needs_ai = bool(for_ai)
    else:
        needs_ai = bool(messages)
    if needs_ai:
        _validate_vertex_env_for_classify()
    predictions, usage = classify_messages_subject_then_ai(messages, mailbox)
    logger.info(
        "Classified %s message(s). Tokens in/out: %s/%s (avg in/out per LLM call with usage: %s/%s)",
        len(predictions),
        usage["total_input_tokens"],
        usage["total_output_tokens"],
        usage["avg_input_tokens_per_email"],
        usage["avg_output_tokens_per_email"],
    )
    if args.verbose:
        for p in predictions:
            eid = p.get("email_id", "") or ""
            short = eid[:16] + ("..." if len(eid) > 16 else "")
            logger.debug("  - %s -> %s", short, p.get("category", ""))

    total_tok = int(usage["total_input_tokens"] or 0) + int(usage["total_output_tokens"] or 0)
    run_pipeline_stub(
        mailbox,
        provider,
        classify_batch=None,
        model_id=model_id,
        prompt_version="2",
        messages=messages,
        predictions=predictions,
        apply_write_back=args.write_back,
        total_tokens_used=total_tok,
        persist_inbox_id=mailbox.inbox_id,
    )


if __name__ == "__main__":
    main()
