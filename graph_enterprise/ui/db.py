"""Config persistence: Microsoft SQL Server (pyodbc) or in-memory demo store.

Demo mode (default when ``MSSQL_ODBC_CONNECTION_STRING`` is unset): set
``GRAPH_ENTERPRISE_DEMO=1`` to force demo even with a connection string, or
``GRAPH_ENTERPRISE_DEMO=0`` to require SQL Server and fail if the string is missing.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config.models import parse_inbox_fetch_filter, parse_subject_classify_rules
from . import demo_db

_ENV_CONN = "MSSQL_ODBC_CONNECTION_STRING"


def _env_bool(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


def is_demo_mode() -> bool:
    """Use in-memory dummy data instead of SQL Server."""
    explicit = _env_bool("GRAPH_ENTERPRISE_DEMO")
    if explicit is True:
        return True
    if explicit is False:
        return False
    return not os.environ.get(_ENV_CONN, "").strip()


def _demo(conn: Any) -> bool:
    return conn is demo_db.DEMO_CONN


def connection_string() -> str:
    raw = os.environ.get(_ENV_CONN, "").strip()
    if not raw:
        raise RuntimeError(
            f"{_ENV_CONN} is required. "
            "Example: Driver={ODBC Driver 18 for SQL Server};Server=host;Database=db;Uid=...;Pwd=...;Encrypt=yes;"
        )
    return raw


def is_integrity_error(exc: BaseException) -> bool:
    """Unique / FK violations from pyodbc or demo store."""
    if isinstance(exc, demo_db.DemoIntegrityError):
        return True
    try:
        import pyodbc

        return isinstance(exc, pyodbc.IntegrityError)
    except ImportError:
        return type(exc).__name__ == "IntegrityError"


def _execute(conn: Any, sql: str, params: tuple = ()) -> Any:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _fetchall_dicts(cur: Any) -> List[Dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    desc = cur.description
    if not desc:
        return []
    cols = [c[0] for c in desc]
    return [dict(zip(cols, row)) for row in rows]


def _fetchone_dict(cur: Any) -> Optional[Dict[str, Any]]:
    row = cur.fetchone()
    if row is None:
        return None
    desc = cur.description
    if not desc:
        return None
    cols = [c[0] for c in desc]
    return dict(zip(cols, row))


@contextmanager
def get_connection() -> Iterator[Any]:
    if is_demo_mode():
        yield demo_db.DEMO_CONN
        return

    import pyodbc

    conn = pyodbc.connect(connection_string())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _api_utc_iso(dt: datetime) -> str:
    """Serialize for JSON/Next.js. Naive datetimes are UTC (DATETIME2 + pyodbc)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    s = dt.isoformat()
    if s.endswith("+00:00"):
        return f"{s[:-6]}Z"
    return s


def _mssql_apply_sql_files(conn: Any) -> None:
    base = Path(__file__).resolve().parents[1] / "migrations" / "mssql"
    for fname in (
        "000_full_schema.sql",
        "001_schema_scheduling.sql",
        "002_inbox_fetch_filter.sql",
        "003_inbox_graph_write_back.sql",
        "004_inbox_subject_classify.sql",
        "005_run_log_category_histogram.sql",
        "006_message_classification.sql",
        "007_agentic_workflow.sql",
    ):
        p = base / fname
        if not p.exists():
            continue
        sql = p.read_text(encoding="utf-8")
        conn.cursor().execute(sql)


def init_db() -> None:
    if is_demo_mode():
        demo_db.init_demo_store()
        return
    with get_connection() as conn:
        _mssql_apply_sql_files(conn)


def list_prompt_templates(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_prompt_templates()
    cur = _execute(
        conn,
        "SELECT id, name, body, created_at, updated_at FROM prompt_template ORDER BY name",
    )
    return _fetchall_dicts(cur)


def create_prompt_template(conn: Any, name: str, body: str) -> int:
    if _demo(conn):
        return demo_db.create_prompt_template(name, body)
    now = _now_iso()
    cur = _execute(
        conn,
        "INSERT INTO prompt_template (name, body, created_at, updated_at) "
        "OUTPUT INSERTED.id AS id VALUES (?, ?, ?, ?)",
        (name, body, now, now),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def update_prompt_template(conn: Any, template_id: int, name: str, body: str) -> None:
    if _demo(conn):
        demo_db.update_prompt_template(template_id, name, body)
        return
    _execute(
        conn,
        "UPDATE prompt_template SET name = ?, body = ?, updated_at = ? WHERE id = ?",
        (name, body, _now_iso(), template_id),
    )


def delete_prompt_template(conn: Any, template_id: int) -> None:
    if _demo(conn):
        demo_db.delete_prompt_template(template_id)
        return
    _execute(conn, "DELETE FROM prompt_template WHERE id = ?", (template_id,))


def list_classification_sets(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_classification_sets()
    cur = _execute(
        conn,
        "SELECT id, name, created_at, updated_at FROM classification_set ORDER BY name",
    )
    return _fetchall_dicts(cur)


def create_classification_set(conn: Any, name: str) -> int:
    if _demo(conn):
        return demo_db.create_classification_set(name)
    now = _now_iso()
    cur = _execute(
        conn,
        "INSERT INTO classification_set (name, created_at, updated_at) OUTPUT INSERTED.id AS id VALUES (?, ?, ?)",
        (name, now, now),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def update_classification_set(conn: Any, set_id: int, name: str) -> None:
    if _demo(conn):
        demo_db.update_classification_set(set_id, name)
        return
    _execute(
        conn,
        "UPDATE classification_set SET name = ?, updated_at = ? WHERE id = ?",
        (name, _now_iso(), set_id),
    )


def delete_classification_set(conn: Any, set_id: int) -> None:
    if _demo(conn):
        demo_db.delete_classification_set(set_id)
        return
    _execute(conn, "DELETE FROM classification_set WHERE id = ?", (set_id,))


def list_categories(conn: Any, set_id: int) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_categories(set_id)
    cur = _execute(
        conn,
        "SELECT id, name, description, sort_order FROM category "
        "WHERE classification_set_id = ? ORDER BY sort_order, id",
        (set_id,),
    )
    return _fetchall_dicts(cur)


def replace_categories(conn: Any, set_id: int, rows: List[Dict[str, Any]]) -> None:
    if _demo(conn):
        demo_db.replace_categories(set_id, rows)
        return
    _execute(conn, "DELETE FROM category WHERE classification_set_id = ?", (set_id,))
    for idx, row in enumerate(rows):
        _execute(
            conn,
            "INSERT INTO category (classification_set_id, name, description, sort_order) "
            "VALUES (?, ?, ?, ?)",
            (set_id, row["name"], row.get("description", ""), idx),
        )
    _execute(
        conn,
        "UPDATE classification_set SET updated_at = ? WHERE id = ?",
        (_now_iso(), set_id),
    )


def _normalize_inbox_row(r: Dict[str, Any]) -> None:
    r["is_active"] = bool(r.get("is_active"))
    r["graph_write_back_enabled"] = bool(r.get("graph_write_back_enabled", True))
    if "subject_classify_enabled" in r:
        r["subject_classify_enabled"] = bool(r.get("subject_classify_enabled"))
    for k in ("last_run_at", "next_run_at"):
        v = r.get(k)
        if isinstance(v, datetime):
            r[k] = _api_utc_iso(v)


def _attach_fetch_filter_api(r: Dict[str, Any]) -> None:
    """Replace fetch_filter_json with fetch_filter dict for REST responses."""
    raw = r.pop("fetch_filter_json", None)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        r["fetch_filter"] = None
    else:
        r["fetch_filter"] = parse_inbox_fetch_filter(raw).model_dump(mode="json")


def _attach_subject_classify_api(r: Dict[str, Any]) -> None:
    raw = r.pop("subject_classify_rules_json", None)
    rules = parse_subject_classify_rules(raw)
    r["subject_classify_rules"] = [x.model_dump(mode="json") for x in rules]


def count_inboxes(
    conn: Any, search: Optional[str] = None, is_active: Optional[bool] = None
) -> int:
    if _demo(conn):
        return demo_db.count_inboxes(search=search, is_active=is_active)
    base = (
        "SELECT COUNT(*) AS n FROM inbox i "
        "JOIN prompt_template pt ON pt.id = i.prompt_template_id "
        "JOIN classification_set cs ON cs.id = i.classification_set_id "
        "LEFT JOIN app_model am ON am.id = i.app_model_id "
    )
    where_clauses: list[str] = []
    params: list[Any] = []
    if search is not None and search.strip():
        like = f"%{search.strip()}%"
        where_clauses.append(
            "(i.mailbox_id LIKE ? OR pt.name LIKE ? OR cs.name LIKE ? OR am.name LIKE ?)"
        )
        params.extend([like, like, like, like])
    if is_active is not None:
        where_clauses.append("i.is_active = ?")
        params.append(1 if is_active else 0)
    if where_clauses:
        base += " WHERE " + " AND ".join(where_clauses)
    cur = _execute(conn, base, tuple(params))
    row = _fetchone_dict(cur)
    return int(row["n"]) if row and row.get("n") is not None else 0


def list_inboxes(
    conn: Any,
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_inboxes(
            offset=offset, limit=limit, search=search, is_active=is_active
        )
    base = (
        "SELECT i.id, i.mailbox_id, i.prompt_template_id, i.classification_set_id, "
        "i.timezone, i.mail_folder, i.max_messages_per_run, i.patch_max_workers, "
        "i.polling_interval_minutes, i.is_active, i.graph_write_back_enabled, i.last_run_at, i.next_run_at, "
        "i.fetch_filter_json, i.subject_classify_enabled, i.subject_classify_rules_json, "
        "pt.name AS prompt_name, cs.name AS classification_set_name, "
        "am.name AS app_model_name, i.app_model_id "
        "FROM inbox i "
        "JOIN prompt_template pt ON pt.id = i.prompt_template_id "
        "JOIN classification_set cs ON cs.id = i.classification_set_id "
        "LEFT JOIN app_model am ON am.id = i.app_model_id "
    )
    where_clauses: list[str] = []
    params: list[Any] = []
    if search is not None and search.strip():
        like = f"%{search.strip()}%"
        where_clauses.append(
            "(i.mailbox_id LIKE ? OR pt.name LIKE ? OR cs.name LIKE ? OR am.name LIKE ?)"
        )
        params.extend([like, like, like, like])
    if is_active is not None:
        where_clauses.append("i.is_active = ?")
        params.append(1 if is_active else 0)
    if where_clauses:
        base += " WHERE " + " AND ".join(where_clauses)
    base += " ORDER BY i.mailbox_id"
    if limit is not None:
        sql = base + " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, limit])
    elif offset > 0:
        sql = base + " OFFSET ? ROWS FETCH NEXT 2147483647 ROWS ONLY"
        params.append(offset)
    else:
        sql = base
    cur = _execute(conn, sql, tuple(params))
    rows = _fetchall_dicts(cur)
    for r in rows:
        _normalize_inbox_row(r)
        _attach_fetch_filter_api(r)
        _attach_subject_classify_api(r)
    return rows


def create_inbox(
    conn: Any,
    mailbox_id: str,
    prompt_template_id: int,
    classification_set_id: int,
    timezone: str,
    mail_folder: str,
    max_messages_per_run: Optional[int],
    patch_max_workers: int,
    *,
    polling_interval_minutes: int = 5,
    is_active: bool = True,
    graph_write_back_enabled: bool = True,
    app_model_id: Optional[int] = None,
    fetch_filter_json: Optional[str] = None,
    subject_classify_enabled: bool = False,
    subject_classify_rules_json: Optional[str] = None,
) -> int:
    if _demo(conn):
        return demo_db.create_inbox(
            mailbox_id,
            prompt_template_id,
            classification_set_id,
            timezone,
            mail_folder,
            max_messages_per_run,
            patch_max_workers,
            polling_interval_minutes=polling_interval_minutes,
            is_active=is_active,
            graph_write_back_enabled=graph_write_back_enabled,
            app_model_id=app_model_id,
            fetch_filter_json=fetch_filter_json,
            subject_classify_enabled=subject_classify_enabled,
            subject_classify_rules_json=subject_classify_rules_json,
        )
    now = _now_iso()
    next_run = now
    cur = _execute(
        conn,
        "INSERT INTO inbox (mailbox_id, prompt_template_id, classification_set_id, app_model_id, timezone, "
        "mail_folder, max_messages_per_run, patch_max_workers, polling_interval_minutes, "
        "is_active, graph_write_back_enabled, next_run_at, fetch_filter_json, "
        "subject_classify_enabled, subject_classify_rules_json, "
        "created_at, updated_at) "
        "OUTPUT INSERTED.id AS id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            mailbox_id,
            prompt_template_id,
            classification_set_id,
            app_model_id,
            timezone,
            mail_folder,
            max_messages_per_run,
            patch_max_workers,
            polling_interval_minutes,
            1 if is_active else 0,
            1 if graph_write_back_enabled else 0,
            next_run,
            fetch_filter_json,
            1 if subject_classify_enabled else 0,
            subject_classify_rules_json,
            now,
            now,
        ),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def update_inbox(
    conn: Any,
    inbox_id: int,
    mailbox_id: str,
    prompt_template_id: int,
    classification_set_id: int,
    timezone: str,
    mail_folder: str,
    max_messages_per_run: Optional[int],
    patch_max_workers: int,
    *,
    polling_interval_minutes: int = 5,
    is_active: bool = True,
    graph_write_back_enabled: bool = True,
    app_model_id: Optional[int] = None,
    fetch_filter_json: Optional[str] = None,
    subject_classify_enabled: bool = False,
    subject_classify_rules_json: Optional[str] = None,
) -> None:
    if _demo(conn):
        demo_db.update_inbox(
            inbox_id,
            mailbox_id,
            prompt_template_id,
            classification_set_id,
            timezone,
            mail_folder,
            max_messages_per_run,
            patch_max_workers,
            polling_interval_minutes=polling_interval_minutes,
            is_active=is_active,
            graph_write_back_enabled=graph_write_back_enabled,
            app_model_id=app_model_id,
            fetch_filter_json=fetch_filter_json,
            subject_classify_enabled=subject_classify_enabled,
            subject_classify_rules_json=subject_classify_rules_json,
        )
        return
    _execute(
        conn,
        "UPDATE inbox SET mailbox_id = ?, prompt_template_id = ?, classification_set_id = ?, app_model_id = ?, "
        "timezone = ?, mail_folder = ?, max_messages_per_run = ?, patch_max_workers = ?, "
        "polling_interval_minutes = ?, is_active = ?, graph_write_back_enabled = ?, fetch_filter_json = ?, "
        "subject_classify_enabled = ?, subject_classify_rules_json = ?, "
        "updated_at = ? WHERE id = ?",
        (
            mailbox_id,
            prompt_template_id,
            classification_set_id,
            app_model_id,
            timezone,
            mail_folder,
            max_messages_per_run,
            patch_max_workers,
            polling_interval_minutes,
            1 if is_active else 0,
            1 if graph_write_back_enabled else 0,
            fetch_filter_json,
            1 if subject_classify_enabled else 0,
            subject_classify_rules_json,
            _now_iso(),
            inbox_id,
        ),
    )


def delete_inbox(conn: Any, inbox_id: int) -> None:
    if _demo(conn):
        demo_db.delete_inbox(inbox_id)
        return
    _execute(conn, "DELETE FROM inbox WHERE id = ?", (inbox_id,))


def bulk_update_inbox_active(conn: Any, inbox_ids: List[int], is_active: bool) -> int:
    """Set is_active on multiple inboxes. Returns count of rows updated."""
    if _demo(conn):
        return demo_db.bulk_update_inbox_active(inbox_ids, is_active)
    if not inbox_ids:
        return 0
    placeholders = ", ".join("?" for _ in inbox_ids)
    cur = _execute(
        conn,
        f"UPDATE inbox SET is_active = ?, updated_at = ? WHERE id IN ({placeholders})",
        (1 if is_active else 0, _now_iso(), *inbox_ids),
    )
    return cur.rowcount


def bulk_delete_inboxes(conn: Any, inbox_ids: List[int]) -> int:
    """Delete multiple inboxes. Returns count of rows deleted."""
    if _demo(conn):
        return demo_db.bulk_delete_inboxes(inbox_ids)
    if not inbox_ids:
        return 0
    placeholders = ", ".join("?" for _ in inbox_ids)
    cur = _execute(
        conn,
        f"DELETE FROM inbox WHERE id IN ({placeholders})",
        tuple(inbox_ids),
    )
    return cur.rowcount


def get_inbox_config(conn: Any, mailbox_id: str) -> Optional[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.get_inbox_config(mailbox_id)
    cur = _execute(
        conn,
        "SELECT i.id, i.mailbox_id, i.timezone, i.mail_folder, i.max_messages_per_run, "
        "i.patch_max_workers, i.polling_interval_minutes, i.is_active, i.graph_write_back_enabled, i.last_run_at, "
        "i.prompt_template_id, i.classification_set_id, i.app_model_id, i.fetch_filter_json, "
        "i.subject_classify_enabled, i.subject_classify_rules_json, "
        "pt.body AS prompt_template, am.name AS app_model_name "
        "FROM inbox i "
        "JOIN prompt_template pt ON pt.id = i.prompt_template_id "
        "LEFT JOIN app_model am ON am.id = i.app_model_id "
        "WHERE i.mailbox_id = ?",
        (mailbox_id,),
    )
    inbox = _fetchone_dict(cur)
    if not inbox:
        return None
    data = dict(inbox)
    data["is_active"] = bool(data.get("is_active"))
    data["graph_write_back_enabled"] = bool(data.get("graph_write_back_enabled", True))
    if "subject_classify_enabled" in data:
        data["subject_classify_enabled"] = bool(data.get("subject_classify_enabled"))
    lr = data.get("last_run_at")
    if isinstance(lr, datetime):
        data["last_run_at"] = _api_utc_iso(lr)
    set_id = int(data["classification_set_id"])
    data["categories"] = list_categories(conn, set_id)
    _attach_subject_classify_api(data)
    return data


def get_inbox_by_id(conn: Any, inbox_id: int) -> Optional[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.get_inbox_by_id(inbox_id)
    cur = _execute(
        conn,
        "SELECT i.id, i.mailbox_id, i.timezone, i.mail_folder, i.max_messages_per_run, "
        "i.patch_max_workers, i.polling_interval_minutes, i.is_active, i.graph_write_back_enabled, "
        "i.last_run_at, i.next_run_at, "
        "i.prompt_template_id, i.classification_set_id, i.app_model_id, i.fetch_filter_json, "
        "i.subject_classify_enabled, i.subject_classify_rules_json, "
        "pt.body AS prompt_template, am.name AS app_model_name "
        "FROM inbox i "
        "JOIN prompt_template pt ON pt.id = i.prompt_template_id "
        "LEFT JOIN app_model am ON am.id = i.app_model_id "
        "WHERE i.id = ?",
        (inbox_id,),
    )
    row = _fetchone_dict(cur)
    if not row:
        return None
    data = dict(row)
    data["is_active"] = bool(data.get("is_active"))
    data["graph_write_back_enabled"] = bool(data.get("graph_write_back_enabled", True))
    for k in ("last_run_at", "next_run_at"):
        v = data.get(k)
        if isinstance(v, datetime):
            data[k] = _api_utc_iso(v)
    set_id = int(data["classification_set_id"])
    data["categories"] = list_categories(conn, set_id)
    _attach_fetch_filter_api(data)
    _attach_subject_classify_api(data)
    return data


def inbox_summary(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.inbox_summary()
    cur = _execute(
        conn,
        "SELECT i.mailbox_id, pt.name AS prompt_name, cs.name AS classification_set_name, "
        "am.name AS app_model_name, "
        "i.timezone, i.mail_folder, i.max_messages_per_run, i.patch_max_workers, "
        "i.polling_interval_minutes, i.is_active, i.last_run_at, i.next_run_at, "
        "(SELECT COUNT(*) FROM category c WHERE c.classification_set_id = cs.id) AS category_count "
        "FROM inbox i "
        "JOIN prompt_template pt ON pt.id = i.prompt_template_id "
        "JOIN classification_set cs ON cs.id = i.classification_set_id "
        "LEFT JOIN app_model am ON am.id = i.app_model_id "
        "ORDER BY i.mailbox_id",
    )
    rows = _fetchall_dicts(cur)
    for r in rows:
        r["is_active"] = bool(r.get("is_active"))
        for k in ("last_run_at", "next_run_at"):
            v = r.get(k)
            if isinstance(v, datetime):
                r[k] = _api_utc_iso(v)
    return rows


def get_global_polling_paused(conn: Any) -> bool:
    if _demo(conn):
        return demo_db.get_global_polling_paused()
    cur = _execute(
        conn,
        "SELECT [value] FROM app_setting WHERE [key] = ?",
        ("global_polling_paused",),
    )
    row = _fetchone_dict(cur)
    if not row:
        return False
    return str(row.get("value", "")).strip().lower() in ("1", "true", "yes")


def set_global_polling_paused(conn: Any, paused: bool) -> None:
    if _demo(conn):
        demo_db.set_global_polling_paused(paused)
        return
    val = "true" if paused else "false"
    cur = conn.cursor()
    cur.execute(
        "UPDATE app_setting SET [value] = ? WHERE [key] = ?",
        (val, "global_polling_paused"),
    )
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO app_setting ([key], [value]) VALUES (?, ?)",
            ("global_polling_paused", val),
        )


def get_agent_api_configs(conn: Any) -> List[Dict[str, str]]:
    if _demo(conn):
        return demo_db.get_agent_api_configs()
    cur = _execute(conn, "SELECT [value] FROM app_setting WHERE [key] = ?", ("agent_api_configs",))
    row = _fetchone_dict(cur)
    if not row:
        return []
    raw = row.get("value")
    if raw is None:
        return []
    try:
        data = json.loads(str(raw))
        if isinstance(data, list):
            return [
                {
                    "name": str(item.get("name", "")),
                    "api_url": str(item.get("api_url", "")),
                    "api_key": str(item.get("api_key", "")),
                }
                for item in data
                if isinstance(item, dict)
            ]
    except Exception:
        pass
    return []


def set_agent_api_configs(conn: Any, configs: List[Dict[str, str]]) -> None:
    if _demo(conn):
        demo_db.set_agent_api_configs(configs)
        return
    payload = json.dumps(configs)
    cur = conn.cursor()
    cur.execute(
        "UPDATE app_setting SET [value] = ? WHERE [key] = ?",
        (payload, "agent_api_configs"),
    )
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO app_setting ([key], [value]) VALUES (?, ?)",
            ("agent_api_configs", payload),
        )


def list_due_inboxes(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_due_inboxes()
    cur = _execute(
        conn,
        "SELECT id, mailbox_id, polling_interval_minutes FROM inbox "
        "WHERE is_active = 1 AND (next_run_at IS NULL OR next_run_at <= SYSUTCDATETIME())",
    )
    return _fetchall_dicts(cur)


def insert_run_log(
    conn: Any,
    *,
    inbox_id: int,
    status: str,
    fetched_count: int,
    classified_count: int,
    tagged_count: int,
    failures: int,
    latency_ms: float,
    total_tokens_used: Optional[int],
    error_message: Optional[str],
    category_histogram: Optional[str] = None,
) -> int:
    """Insert a run_log row and return its id."""
    if _demo(conn):
        return demo_db.insert_run_log(
            inbox_id=inbox_id,
            status=status,
            fetched_count=fetched_count,
            classified_count=classified_count,
            tagged_count=tagged_count,
            failures=failures,
            latency_ms=latency_ms,
            total_tokens_used=total_tokens_used,
            error_message=error_message,
            category_histogram=category_histogram,
        )
    created = _now_iso()
    err = error_message
    if err and len(err) > 8000:
        err = err[:8000] + "…"
    cur = _execute(
        conn,
        "INSERT INTO run_log (inbox_id, status, fetched_count, classified_count, tagged_count, "
        "failures, latency_ms, total_tokens_used, error_message, category_histogram, created_at) "
        "OUTPUT INSERTED.id AS id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            inbox_id,
            status,
            fetched_count,
            classified_count,
            tagged_count,
            failures,
            latency_ms,
            total_tokens_used,
            err,
            category_histogram,
            created,
        ),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def update_inbox_run_times(
    conn: Any,
    inbox_id: int,
    *,
    last_run_at: str,
    next_run_at: str,
) -> None:
    if _demo(conn):
        demo_db.update_inbox_run_times(
            inbox_id, last_run_at=last_run_at, next_run_at=next_run_at
        )
        return
    _execute(
        conn,
        "UPDATE inbox SET last_run_at = ?, next_run_at = ?, updated_at = ? WHERE id = ?",
        (last_run_at, next_run_at, _now_iso(), inbox_id),
    )


def bump_inbox_next_run_after_enqueue(
    conn: Any, inbox_id: int, *, grace_minutes: int = 5
) -> None:
    """Push ``next_run_at`` forward so a slow queue or long run cannot re-enqueue the same inbox every tick.

    The worker still sets the real schedule when it finishes via ``update_inbox_run_times``.
    """
    if _demo(conn):
        demo_db.bump_inbox_next_run_after_enqueue(inbox_id, grace_minutes=grace_minutes)
        return
    nxt = (
        datetime.now(timezone.utc) + timedelta(minutes=max(1, int(grace_minutes)))
    ).isoformat()
    _execute(
        conn,
        "UPDATE inbox SET next_run_at = ?, updated_at = ? WHERE id = ?",
        (nxt, _now_iso(), inbox_id),
    )


def compute_next_run_iso(conn: Any, inbox_id: int) -> str:
    if _demo(conn):
        return demo_db.compute_next_run_iso(inbox_id)
    cur = _execute(
        conn,
        "SELECT polling_interval_minutes FROM inbox WHERE id = ?",
        (inbox_id,),
    )
    row = _fetchone_dict(cur)
    mins = int(row["polling_interval_minutes"] or 5) if row else 5
    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()


def list_run_logs_for_inbox(
    conn: Any, inbox_id: int, limit: int = 50
) -> List[Dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    if _demo(conn):
        return demo_db.list_run_logs_for_inbox(inbox_id, limit=lim)
    cur = _execute(
        conn,
        f"SELECT TOP ({lim}) id, inbox_id, status, fetched_count, classified_count, tagged_count, "
        "failures, latency_ms, total_tokens_used, error_message, created_at "
        "FROM run_log WHERE inbox_id = ? ORDER BY id DESC",
        (inbox_id,),
    )
    rows = _fetchall_dicts(cur)
    for r in rows:
        ca = r.get("created_at")
        if isinstance(ca, datetime):
            r["created_at"] = _api_utc_iso(ca)
    return rows


def list_app_models(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_app_models()
    cur = _execute(
        conn,
        "SELECT id, name, is_active, created_at, updated_at FROM app_model ORDER BY name",
    )
    return _fetchall_dicts(cur)


def create_app_model(conn: Any, name: str) -> int:
    if _demo(conn):
        return demo_db.create_app_model(name)
    now = _now_iso()
    cur = _execute(
        conn,
        "INSERT INTO app_model (name, created_at, updated_at) OUTPUT INSERTED.id AS id VALUES (?, ?, ?)",
        (name, now, now),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def delete_app_model(conn: Any, model_id: int) -> None:
    if _demo(conn):
        demo_db.delete_app_model(model_id)
        return
    _execute(conn, "DELETE FROM app_model WHERE id = ?", (model_id,))


def fleet_summary(
    conn: Any,
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.fleet_summary(
            offset=offset, limit=limit, search=search, is_active=is_active
        )
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    inboxes = list_inboxes(
        conn, offset=offset, limit=limit, search=search, is_active=is_active
    )
    out: List[Dict[str, Any]] = []
    for inv in inboxes:
        iid = int(inv["id"])
        cur = _execute(
            conn,
            "SELECT "
            "COALESCE(SUM(fetched_count), 0) AS emails_24h, "
            "COALESCE(SUM(total_tokens_used), 0) AS tokens_24h, "
            "MAX(created_at) AS last_log_at "
            "FROM run_log WHERE inbox_id = ? AND created_at >= ?",
            (iid, since),
        )
        agg = _fetchone_dict(cur) or {}
        cur2 = _execute(
            conn,
            "SELECT TOP 1 status, error_message FROM run_log WHERE inbox_id = ? ORDER BY id DESC",
            (iid,),
        )
        last = _fetchone_dict(cur2)
        last_status = (last or {}).get("status")
        health_ok = last_status == "Success" if last_status else True
        lr = inv.get("last_run_at")
        if isinstance(lr, datetime):
            lr = _api_utc_iso(lr)
        nr = inv.get("next_run_at")
        if isinstance(nr, datetime):
            nr = _api_utc_iso(nr)
        out.append(
            {
                **inv,
                "last_run_at": lr,
                "next_run_at": nr,
                "emails_processed_24h": int(agg.get("emails_24h") or 0),
                "token_spend_24h": int(agg.get("tokens_24h") or 0),
                "health_ok": health_ok,
                "last_run_status": last_status,
                "last_error_message": (last or {}).get("error_message"),
            }
        )
    return out


def token_trends(conn: Any, days: int = 7) -> List[Dict[str, Any]]:
    """Aggregate total_tokens_used from run_log grouped by date."""
    if days <= 0:
        return []
    if _demo(conn):
        return demo_db.token_trends(days)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = _execute(
        conn,
        "SELECT CONVERT(VARCHAR(10), created_at, 120) AS date, "
        "SUM(COALESCE(total_tokens_used, 0)) AS total_tokens "
        "FROM run_log WHERE created_at >= ? "
        "GROUP BY CONVERT(VARCHAR(10), created_at, 120) "
        "ORDER BY CONVERT(VARCHAR(10), created_at, 120)",
        (since,),
    )
    rows = _fetchall_dicts(cur)
    return [{"date": r["date"], "total_tokens": int(r["total_tokens"])} for r in rows]


def classification_breakdown(
    conn: Any, inbox_id: int, days: int = 7
) -> Dict[str, int]:
    """Aggregate category_histogram JSON from run_log for a given inbox.

    Returns empty dict when no histogram data is available.
    """
    if days <= 0:
        return {}
    if _demo(conn):
        return demo_db.classification_breakdown(inbox_id, days)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        cur = _execute(
            conn,
            "SELECT category_histogram FROM run_log "
            "WHERE inbox_id = ? AND created_at >= ? AND category_histogram IS NOT NULL",
            (inbox_id, since),
        )
        rows = _fetchall_dicts(cur)
    except Exception:
        return {}
    result: Dict[str, int] = {}
    for r in rows:
        raw = r.get("category_histogram")
        if not raw:
            continue
        try:
            hist = json.loads(str(raw))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(hist, dict):
            continue
        for cat, count in hist.items():
            result[cat] = result.get(cat, 0) + int(count)
    return result


def run_volume(conn: Any, days: int = 30) -> List[Dict[str, Any]]:
    """Aggregate run count and message count from run_log grouped by date."""
    if days <= 0:
        return []
    if _demo(conn):
        return demo_db.run_volume(days)
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cur = _execute(
        conn,
        "SELECT CONVERT(VARCHAR(10), created_at, 120) AS date, "
        "COUNT(*) AS run_count, "
        "SUM(COALESCE(fetched_count, 0)) AS message_count "
        "FROM run_log WHERE created_at >= ? "
        "GROUP BY CONVERT(VARCHAR(10), created_at, 120) "
        "ORDER BY CONVERT(VARCHAR(10), created_at, 120)",
        (since,),
    )
    rows = _fetchall_dicts(cur)
    return [
        {
            "date": r["date"],
            "run_count": int(r["run_count"]),
            "message_count": int(r["message_count"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Per-message classification persistence
# ---------------------------------------------------------------------------


def insert_message_classifications(
    conn: Any, run_log_id: int, classifications: List[Dict[str, Any]]
) -> None:
    """Bulk-insert per-message classification rows linked to a run_log entry."""
    if _demo(conn):
        demo_db.insert_message_classifications(run_log_id, classifications)
        return
    for cls in classifications:
        _execute(
            conn,
            "INSERT INTO message_classification "
            "(run_log_id, email_id, subject, sender, category, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_log_id,
                str(cls.get("email_id", "")),
                cls.get("subject"),
                cls.get("sender"),
                str(cls.get("category", "")),
                cls.get("received"),
            ),
        )






def list_distinct_categories_by_inbox(
    conn: Any,
    inbox_id: int,
) -> List[str]:
    """Return sorted list of distinct category values for an inbox."""
    if _demo(conn):
        return demo_db.list_distinct_categories_by_inbox(inbox_id)
    cur = _execute(
        conn,
        "SELECT DISTINCT mc.category FROM message_classification mc "
        "JOIN run_log rl ON rl.id = mc.run_log_id "
        "WHERE rl.inbox_id = ? AND mc.category IS NOT NULL AND mc.category <> '' "
        "ORDER BY mc.category",
        (inbox_id,),
    )
    rows = _fetchall_dicts(cur)
    return [str(r["category"]) for r in rows]


# --- Agentic workflows ---


def _normalize_agentic_row(r: Dict[str, Any]) -> None:
    """Parse JSON columns and normalize booleans for REST responses."""
    r["is_active"] = bool(r.get("is_active"))
    for json_col in ("trigger_categories", "function_declarations", "agent_api_names"):
        raw = r.get(json_col)
        if isinstance(raw, str):
            try:
                r[json_col] = json.loads(raw)
            except Exception:
                r[json_col] = []
        elif raw is None:
            r[json_col] = []
    raw_filter = r.get("workflow_filter")
    if isinstance(raw_filter, str):
        try:
            r["workflow_filter"] = parse_inbox_fetch_filter(raw_filter).model_dump(mode="json")
        except Exception:
            r["workflow_filter"] = None
    elif raw_filter is None:
        r["workflow_filter"] = None
    r["response_prompt_id"] = (
        int(r["response_prompt_id"]) if r.get("response_prompt_id") is not None else None
    )
    r["auto_send"] = bool(r.get("auto_send"))
    for k in ("created_at", "updated_at"):
        v = r.get(k)
        if isinstance(v, datetime):
            r[k] = _api_utc_iso(v)


def list_agentic_workflows(conn: Any) -> List[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.list_agentic_workflows()
    cur = _execute(
        conn,
        "SELECT aw.id, aw.inbox_id, aw.name, aw.extraction_prompt_id, "
        "aw.trigger_categories, aw.function_declarations, aw.agent_api_names, "
        "aw.webhook_url, aw.workflow_filter, aw.response_prompt_id, aw.auto_send, "
        "aw.is_active, aw.created_at, aw.updated_at, "
        "i.mailbox_id AS inbox_mailbox_id, pt.name AS extraction_prompt_name "
        "FROM agentic_workflow aw "
        "JOIN inbox i ON i.id = aw.inbox_id "
        "JOIN prompt_template pt ON pt.id = aw.extraction_prompt_id "
        "ORDER BY aw.name, aw.id",
    )
    rows = _fetchall_dicts(cur)
    for r in rows:
        _normalize_agentic_row(r)
    return rows


def get_agentic_workflow(conn: Any, workflow_id: int) -> Optional[Dict[str, Any]]:
    if _demo(conn):
        return demo_db.get_agentic_workflow(workflow_id)
    cur = _execute(
        conn,
        "SELECT aw.id, aw.inbox_id, aw.name, aw.extraction_prompt_id, "
        "aw.trigger_categories, aw.function_declarations, aw.agent_api_names, "
        "aw.webhook_url, aw.workflow_filter, aw.response_prompt_id, aw.auto_send, "
        "aw.is_active, aw.created_at, aw.updated_at, "
        "i.mailbox_id AS inbox_mailbox_id, pt.name AS extraction_prompt_name "
        "FROM agentic_workflow aw "
        "JOIN inbox i ON i.id = aw.inbox_id "
        "JOIN prompt_template pt ON pt.id = aw.extraction_prompt_id "
        "WHERE aw.id = ?",
        (workflow_id,),
    )
    row = _fetchone_dict(cur)
    if row:
        _normalize_agentic_row(row)
    return row


def get_agentic_workflow_for_inbox(conn: Any, inbox_id: int) -> Optional[Dict[str, Any]]:
    """Return the first active agentic workflow for an inbox (used during pipeline execution)."""
    if _demo(conn):
        return demo_db.get_agentic_workflow_for_inbox(inbox_id)
    cur = _execute(
        conn,
        "SELECT aw.id, aw.inbox_id, aw.name, aw.extraction_prompt_id, "
        "aw.trigger_categories, aw.function_declarations, aw.agent_api_names, "
        "aw.webhook_url, aw.workflow_filter, aw.response_prompt_id, aw.auto_send, "
        "aw.is_active, "
        "pt.body AS extraction_prompt_body, rpt.body AS response_prompt_body "
        "FROM agentic_workflow aw "
        "JOIN prompt_template pt ON pt.id = aw.extraction_prompt_id "
        "LEFT JOIN prompt_template rpt ON rpt.id = aw.response_prompt_id "
        "WHERE aw.inbox_id = ? AND aw.is_active = 1",
        (inbox_id,),
    )
    row = _fetchone_dict(cur)
    if row:
        _normalize_agentic_row(row)
    return row


def create_agentic_workflow(
    conn: Any,
    *,
    inbox_id: int,
    name: str,
    extraction_prompt_id: int,
    trigger_categories_json: str,
    function_declarations_json: Optional[str],
    agent_api_names_json: str,
    webhook_url: Optional[str],
    workflow_filter_json: Optional[str],
    response_prompt_id: Optional[int],
    auto_send: bool = False,
    is_active: bool = True,
) -> int:
    if _demo(conn):
        return demo_db.create_agentic_workflow(
            inbox_id=inbox_id,
            name=name,
            extraction_prompt_id=extraction_prompt_id,
            trigger_categories_json=trigger_categories_json,
            function_declarations_json=function_declarations_json,
            agent_api_names_json=agent_api_names_json,
            webhook_url=webhook_url,
            workflow_filter_json=workflow_filter_json,
            response_prompt_id=response_prompt_id,
            auto_send=auto_send,
            is_active=is_active,
        )
    now = _now_iso()
    cur = _execute(
        conn,
        "INSERT INTO agentic_workflow "
        "(inbox_id, name, extraction_prompt_id, trigger_categories, "
        "function_declarations, agent_api_names, webhook_url, workflow_filter, "
        "response_prompt_id, auto_send, is_active, created_at, updated_at) "
        "OUTPUT INSERTED.id AS id "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            inbox_id,
            name,
            extraction_prompt_id,
            trigger_categories_json,
            function_declarations_json,
            agent_api_names_json,
            webhook_url,
            workflow_filter_json,
            response_prompt_id,
            1 if auto_send else 0,
            1 if is_active else 0,
            now,
            now,
        ),
    )
    row = _fetchone_dict(cur)
    return int(row["id"]) if row else 0


def update_agentic_workflow(
    conn: Any,
    workflow_id: int,
    *,
    inbox_id: int,
    name: str,
    extraction_prompt_id: int,
    trigger_categories_json: str,
    function_declarations_json: Optional[str],
    agent_api_names_json: str,
    webhook_url: Optional[str],
    workflow_filter_json: Optional[str],
    response_prompt_id: Optional[int],
    auto_send: bool = False,
    is_active: bool = True,
) -> None:
    if _demo(conn):
        demo_db.update_agentic_workflow(
            workflow_id,
            inbox_id=inbox_id,
            name=name,
            extraction_prompt_id=extraction_prompt_id,
            trigger_categories_json=trigger_categories_json,
            function_declarations_json=function_declarations_json,
            agent_api_names_json=agent_api_names_json,
            webhook_url=webhook_url,
            workflow_filter_json=workflow_filter_json,
            response_prompt_id=response_prompt_id,
            auto_send=auto_send,
            is_active=is_active,
        )
        return
    _execute(
        conn,
        "UPDATE agentic_workflow SET inbox_id = ?, name = ?, extraction_prompt_id = ?, "
        "trigger_categories = ?, function_declarations = ?, agent_api_names = ?, "
        "webhook_url = ?, workflow_filter = ?, response_prompt_id = ?, auto_send = ?, "
        "is_active = ?, updated_at = ? WHERE id = ?",
        (
            inbox_id,
            name,
            extraction_prompt_id,
            trigger_categories_json,
            function_declarations_json,
            agent_api_names_json,
            webhook_url,
            workflow_filter_json,
            response_prompt_id,
            1 if auto_send else 0,
            1 if is_active else 0,
            _now_iso(),
            workflow_id,
        ),
    )


def delete_agentic_workflow(conn: Any, workflow_id: int) -> None:
    if _demo(conn):
        demo_db.delete_agentic_workflow(workflow_id)
        return
    _execute(conn, "DELETE FROM agentic_workflow WHERE id = ?", (workflow_id,))
