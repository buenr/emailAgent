"""In-memory store for GRAPH_ENTERPRISE demo mode (no SQL Server)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..config.default_categories import DEFAULT_CATEGORIES
from ..config.models import parse_inbox_fetch_filter, parse_subject_classify_rules

DEMO_CONN = object()


class DemoIntegrityError(Exception):
    """Raised for unique/FK violations in demo mode (API maps to 409)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_lock = threading.RLock()
_state: Dict[str, Any] = {
    "prompts": [],
    "sets": [],
    "categories": {},
    "inboxes": [],
    "run_logs": [],
    "message_classifications": [],
    "models": [],
    "next_id": {"prompt": 1, "set": 1, "cat": 1, "inbox": 1, "runlog": 1, "msgcls": 1, "model": 1, "agentic": 1},
    "settings": {"global_polling_paused": "false", "agent_api_configs": "[]"},
    "agentic_workflows": [],
    "initialized": False,
}

DEFAULT_TEMPLATE_NAME = "Logistics/Trucking Default Prompt"
DEFAULT_SET_NAME = "Logistics/Trucking Default Classification Set"
DEFAULT_INBOX_MAILBOX = "demo-afterhours@example.com"

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
Return JSON matching the required schema with category.
"""


def _prompt_by_id(pid: int) -> Optional[Dict[str, Any]]:
    for p in _state["prompts"]:
        if int(p["id"]) == pid:
            return p
    return None


def _set_by_id(sid: int) -> Optional[Dict[str, Any]]:
    for s in _state["sets"]:
        if int(s["id"]) == sid:
            return s
    return None


def _inbox_by_id(iid: int) -> Optional[Dict[str, Any]]:
    for i in _state["inboxes"]:
        if int(i["id"]) == iid:
            return i
    return None


def init_demo_store() -> None:
    with _lock:
        if _state["initialized"]:
            return
        now = _now_iso()
        pid = _state["next_id"]["prompt"]
        _state["next_id"]["prompt"] += 1
        _state["prompts"].append(
            {
                "id": pid,
                "name": DEFAULT_TEMPLATE_NAME,
                "body": DEFAULT_PROMPT_TEMPLATE,
                "created_at": now,
                "updated_at": now,
            }
        )
        sid = _state["next_id"]["set"]
        _state["next_id"]["set"] += 1
        _state["sets"].append(
            {"id": sid, "name": DEFAULT_SET_NAME, "created_at": now, "updated_at": now}
        )
        mid = _state["next_id"]["model"]
        _state["next_id"]["model"] += 1
        _state["models"].append(
            {
                "id": mid,
                "name": "gemini-2.5-flash-lite",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        mid_pro = _state["next_id"]["model"]
        _state["next_id"]["model"] += 1
        _state["models"].append(
            {
                "id": mid_pro,
                "name": "gemini-3.1-pro",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        mid2 = _state["next_id"]["model"]
        _state["next_id"]["model"] += 1
        _state["models"].append(
            {
                "id": mid2,
                "name": "gemini-3.1-flash-lite",
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        cats: List[Dict[str, Any]] = []
        for idx, c in enumerate(DEFAULT_CATEGORIES):
            cid = _state["next_id"]["cat"]
            _state["next_id"]["cat"] += 1
            cats.append(
                {
                    "id": cid,
                    "name": c.name,
                    "description": c.description,
                    "sort_order": idx,
                }
            )
        _state["categories"][sid] = cats
        iid = _state["next_id"]["inbox"]
        _state["next_id"]["inbox"] += 1
        _state["inboxes"].append(
            {
                "id": iid,
                "mailbox_id": DEFAULT_INBOX_MAILBOX,
                "prompt_template_id": pid,
                "classification_set_id": sid,
                "app_model_id": mid,
                "timezone": "UTC",
                "mail_folder": "inbox",
                "max_messages_per_run": 500,
                "patch_max_workers": 4,
                "polling_interval_minutes": 5,
                "is_active": True,
                "graph_write_back_enabled": True,
                "last_run_at": None,
                "next_run_at": now,
                "prompt_name": DEFAULT_TEMPLATE_NAME,
                "classification_set_name": DEFAULT_SET_NAME,
                "app_model_name": "gemini-2.5-flash-lite",
                "fetch_filter_json": None,
                "subject_classify_enabled": False,
                "subject_classify_rules_json": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        _state["initialized"] = True


def _attach_inbox_joins(row: Dict[str, Any]) -> Dict[str, Any]:
    pt = _prompt_by_id(int(row["prompt_template_id"]))
    cs = _set_by_id(int(row["classification_set_id"]))
    am_id = row.get("app_model_id")
    am = None
    if am_id is not None:
        for m in _state["models"]:
            if int(m["id"]) == int(am_id):
                am = m
                break
    out = dict(row)
    out["prompt_name"] = pt["name"] if pt else ""
    out["classification_set_name"] = cs["name"] if cs else ""
    out["app_model_name"] = am["name"] if am else ""
    return out


def list_prompt_templates() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(p) for p in sorted(_state["prompts"], key=lambda x: str(x["name"]))]


def create_prompt_template(name: str, body: str) -> int:
    with _lock:
        if any(str(p["name"]).lower() == name.lower() for p in _state["prompts"]):
            raise DemoIntegrityError("duplicate prompt name")
        now = _now_iso()
        pid = _state["next_id"]["prompt"]
        _state["next_id"]["prompt"] += 1
        _state["prompts"].append(
            {"id": pid, "name": name, "body": body, "created_at": now, "updated_at": now}
        )
        return pid


def update_prompt_template(template_id: int, name: str, body: str) -> None:
    with _lock:
        for p in _state["prompts"]:
            if int(p["id"]) != template_id and str(p["name"]).lower() == name.lower():
                raise DemoIntegrityError("duplicate prompt name")
        for p in _state["prompts"]:
            if int(p["id"]) == template_id:
                p["name"] = name
                p["body"] = body
                p["updated_at"] = _now_iso()
                for inv in _state["inboxes"]:
                    if int(inv["prompt_template_id"]) == template_id:
                        inv["prompt_name"] = name
                        inv["updated_at"] = _now_iso()
                return
        raise KeyError(template_id)


def delete_prompt_template(template_id: int) -> None:
    with _lock:
        if any(int(i["prompt_template_id"]) == template_id for i in _state["inboxes"]):
            raise DemoIntegrityError("prompt in use")
        _state["prompts"] = [p for p in _state["prompts"] if int(p["id"]) != template_id]


def list_classification_sets() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(s) for s in sorted(_state["sets"], key=lambda x: str(x["name"]))]


def create_classification_set(name: str) -> int:
    with _lock:
        if any(str(s["name"]).lower() == name.lower() for s in _state["sets"]):
            raise DemoIntegrityError("duplicate set name")
        now = _now_iso()
        sid = _state["next_id"]["set"]
        _state["next_id"]["set"] += 1
        _state["sets"].append(
            {"id": sid, "name": name, "created_at": now, "updated_at": now}
        )
        _state["categories"][sid] = []
        return sid


def update_classification_set(set_id: int, name: str) -> None:
    with _lock:
        for s in _state["sets"]:
            if int(s["id"]) != set_id and str(s["name"]).lower() == name.lower():
                raise DemoIntegrityError("duplicate set name")
        for s in _state["sets"]:
            if int(s["id"]) == set_id:
                s["name"] = name
                s["updated_at"] = _now_iso()
                for inv in _state["inboxes"]:
                    if int(inv["classification_set_id"]) == set_id:
                        inv["classification_set_name"] = name
                        inv["updated_at"] = _now_iso()
                return
        raise KeyError(set_id)


def delete_classification_set(set_id: int) -> None:
    with _lock:
        if any(int(i["classification_set_id"]) == set_id for i in _state["inboxes"]):
            raise DemoIntegrityError("set in use")
        _state["sets"] = [s for s in _state["sets"] if int(s["id"]) != set_id]
        _state["categories"].pop(set_id, None)


def list_categories(set_id: int) -> List[Dict[str, Any]]:
    with _lock:
        rows = _state["categories"].get(set_id, [])
        return [dict(r) for r in sorted(rows, key=lambda x: (x["sort_order"], x["id"]))]


def replace_categories(set_id: int, rows: List[Dict[str, Any]]) -> None:
    with _lock:
        if not _set_by_id(set_id):
            raise KeyError(set_id)
        new_rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            cid = _state["next_id"]["cat"]
            _state["next_id"]["cat"] += 1
            new_rows.append(
                {
                    "id": cid,
                    "name": row["name"],
                    "description": row.get("description", ""),
                    "sort_order": idx,
                }
            )
        _state["categories"][set_id] = new_rows
        for s in _state["sets"]:
            if int(s["id"]) == set_id:
                s["updated_at"] = _now_iso()
                break


def _demo_list_row_shape(r: Dict[str, Any]) -> None:
    r["is_active"] = bool(r.get("is_active"))
    r["graph_write_back_enabled"] = bool(r.get("graph_write_back_enabled", True))
    for k in ("last_run_at", "next_run_at"):
        v = r.get(k)
        if v is not None and hasattr(v, "isoformat"):
            r[k] = v.isoformat()
    raw = r.pop("fetch_filter_json", None)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        r["fetch_filter"] = None
    else:
        r["fetch_filter"] = parse_inbox_fetch_filter(raw).model_dump(mode="json")
    r["subject_classify_enabled"] = bool(r.get("subject_classify_enabled", False))
    raw_sj = r.pop("subject_classify_rules_json", None)
    rules = parse_subject_classify_rules(raw_sj)
    r["subject_classify_rules"] = [x.model_dump(mode="json") for x in rules]


def count_inboxes(
    search: Optional[str] = None, is_active: Optional[bool] = None
) -> int:
    with _lock:
        inboxes = _state["inboxes"]
        if search is not None and search.strip():
            s = search.strip().lower()
            inboxes = [
                inv
                for inv in inboxes
                if s in str(inv.get("mailbox_id", "")).lower()
                or s in str(inv.get("prompt_name", "")).lower()
                or s in str(inv.get("classification_set_name", "")).lower()
                or s in str(inv.get("app_model_name", "")).lower()
            ]
        if is_active is not None:
            inboxes = [
                inv for inv in inboxes if bool(inv.get("is_active")) == is_active
            ]
        return len(inboxes)


def list_inboxes(
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    with _lock:
        sorted_list = sorted(_state["inboxes"], key=lambda x: str(x["mailbox_id"]))
        if search is not None and search.strip():
            s = search.strip().lower()
            sorted_list = [
                inv
                for inv in sorted_list
                if s in str(inv.get("mailbox_id", "")).lower()
                or s in str(inv.get("prompt_name", "")).lower()
                or s in str(inv.get("classification_set_name", "")).lower()
                or s in str(inv.get("app_model_name", "")).lower()
            ]
        if is_active is not None:
            sorted_list = [
                inv for inv in sorted_list if bool(inv.get("is_active")) == is_active
            ]
        if limit is not None:
            slice_list = sorted_list[offset : offset + limit]
        else:
            slice_list = sorted_list[offset:]
        out = []
        for inv in slice_list:
            row = _attach_inbox_joins(inv)
            r = {k: v for k, v in row.items() if k not in ("created_at",)}
            r["fetch_filter_json"] = inv.get("fetch_filter_json")
            _demo_list_row_shape(r)
            out.append(r)
        return out


def create_inbox(
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
    with _lock:
        if any(str(i["mailbox_id"]).lower() == mailbox_id.lower() for i in _state["inboxes"]):
            raise DemoIntegrityError("duplicate mailbox")
        if not _prompt_by_id(prompt_template_id) or not _set_by_id(classification_set_id):
            raise DemoIntegrityError("fk")
        now = _now_iso()
        iid = _state["next_id"]["inbox"]
        _state["next_id"]["inbox"] += 1
        pt = _prompt_by_id(prompt_template_id)
        cs = _set_by_id(classification_set_id)
        am_name = ""
        if app_model_id is not None:
            for m in _state["models"]:
                if int(m["id"]) == int(app_model_id):
                    am_name = m["name"]
                    break
        _state["inboxes"].append(
            {
                "id": iid,
                "mailbox_id": mailbox_id,
                "prompt_template_id": prompt_template_id,
                "classification_set_id": classification_set_id,
                "app_model_id": app_model_id,
                "timezone": timezone,
                "mail_folder": mail_folder,
                "max_messages_per_run": max_messages_per_run,
                "patch_max_workers": patch_max_workers,
                "polling_interval_minutes": polling_interval_minutes,
                "is_active": is_active,
                "graph_write_back_enabled": graph_write_back_enabled,
                "last_run_at": None,
                "next_run_at": now,
                "prompt_name": pt["name"] if pt else "",
                "classification_set_name": cs["name"] if cs else "",
                "app_model_name": am_name,
                "fetch_filter_json": fetch_filter_json,
                "subject_classify_enabled": subject_classify_enabled,
                "subject_classify_rules_json": subject_classify_rules_json,
                "created_at": now,
                "updated_at": now,
            }
        )
        return iid


def update_inbox(
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
    with _lock:
        for i in _state["inboxes"]:
            if int(i["id"]) != inbox_id and str(i["mailbox_id"]).lower() == mailbox_id.lower():
                raise DemoIntegrityError("duplicate mailbox")
        if not _prompt_by_id(prompt_template_id) or not _set_by_id(classification_set_id):
            raise DemoIntegrityError("fk")
        pt = _prompt_by_id(prompt_template_id)
        cs = _set_by_id(classification_set_id)
        am_name = ""
        if app_model_id is not None:
            for m in _state["models"]:
                if int(m["id"]) == int(app_model_id):
                    am_name = m["name"]
                    break
        for i in _state["inboxes"]:
            if int(i["id"]) == inbox_id:
                i.update(
                    {
                        "mailbox_id": mailbox_id,
                        "prompt_template_id": prompt_template_id,
                        "classification_set_id": classification_set_id,
                        "app_model_id": app_model_id,
                        "timezone": timezone,
                        "mail_folder": mail_folder,
                        "max_messages_per_run": max_messages_per_run,
                        "patch_max_workers": patch_max_workers,
                        "polling_interval_minutes": polling_interval_minutes,
                        "is_active": is_active,
                        "graph_write_back_enabled": graph_write_back_enabled,
                        "prompt_name": pt["name"] if pt else "",
                        "classification_set_name": cs["name"] if cs else "",
                        "app_model_name": am_name,
                        "fetch_filter_json": fetch_filter_json,
                        "subject_classify_enabled": subject_classify_enabled,
                        "subject_classify_rules_json": subject_classify_rules_json,
                        "updated_at": _now_iso(),
                    }
                )
                return
        raise KeyError(inbox_id)


def delete_inbox(inbox_id: int) -> None:
    with _lock:
        _state["inboxes"] = [i for i in _state["inboxes"] if int(i["id"]) != inbox_id]


def bulk_update_inbox_active(inbox_ids: List[int], is_active: bool) -> int:
    """Set is_active on multiple inboxes. Returns count of inboxes updated."""
    with _lock:
        id_set = set(inbox_ids)
        count = 0
        for i in _state["inboxes"]:
            if int(i["id"]) in id_set:
                i["is_active"] = is_active
                i["updated_at"] = _now_iso()
                count += 1
        return count


def bulk_delete_inboxes(inbox_ids: List[int]) -> int:
    """Delete multiple inboxes. Returns count of inboxes deleted."""
    with _lock:
        id_set = set(inbox_ids)
        before = len(_state["inboxes"])
        _state["inboxes"] = [i for i in _state["inboxes"] if int(i["id"]) not in id_set]
        return before - len(_state["inboxes"])


def get_inbox_config(mailbox_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for i in _state["inboxes"]:
            if str(i["mailbox_id"]) == mailbox_id:
                return _inbox_detail_dict(i)
        return None


def get_inbox_by_id(inbox_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        i = _inbox_by_id(inbox_id)
        if not i:
            return None
        d = _inbox_detail_dict(i)
    raw = d.pop("fetch_filter_json", None)
    if raw is None or (isinstance(raw, str) and not str(raw).strip()):
        d["fetch_filter"] = None
    else:
        d["fetch_filter"] = parse_inbox_fetch_filter(raw).model_dump(mode="json")
    d["subject_classify_enabled"] = bool(d.get("subject_classify_enabled", False))
    raw_sj = d.pop("subject_classify_rules_json", None)
    d["subject_classify_rules"] = [
        x.model_dump(mode="json") for x in parse_subject_classify_rules(raw_sj)
    ]
    return d


def _inbox_detail_dict(inv: Dict[str, Any]) -> Dict[str, Any]:
    sid = int(inv["classification_set_id"])
    pt = _prompt_by_id(int(inv["prompt_template_id"]))
    data = dict(inv)
    data["is_active"] = bool(data.get("is_active"))
    data["graph_write_back_enabled"] = bool(data.get("graph_write_back_enabled", True))
    data.setdefault("subject_classify_enabled", False)
    data.setdefault("subject_classify_rules_json", inv.get("subject_classify_rules_json"))
    data["prompt_template"] = pt["body"] if pt else ""
    data["categories"] = list_categories(sid)
    return data


def inbox_summary() -> List[Dict[str, Any]]:
    with _lock:
        out = []
        for inv in sorted(_state["inboxes"], key=lambda x: str(x["mailbox_id"])):
            sid = int(inv["classification_set_id"])
            cats = _state["categories"].get(sid, [])
            row = _attach_inbox_joins(inv)
            out.append(
                {
                    "mailbox_id": row["mailbox_id"],
                    "prompt_name": row["prompt_name"],
                    "classification_set_name": row["classification_set_name"],
                    "app_model_name": row["app_model_name"],
                    "timezone": row["timezone"],
                    "mail_folder": row["mail_folder"],
                    "max_messages_per_run": row["max_messages_per_run"],
                    "patch_max_workers": row["patch_max_workers"],
                    "polling_interval_minutes": row["polling_interval_minutes"],
                    "is_active": bool(row.get("is_active")),
                    "last_run_at": row.get("last_run_at"),
                    "next_run_at": row.get("next_run_at"),
                    "category_count": len(cats),
                }
            )
        return out


def list_app_models() -> List[Dict[str, Any]]:
    with _lock:
        return [dict(m) for m in sorted(_state["models"], key=lambda x: str(x["name"]))]


def create_app_model(name: str) -> int:
    with _lock:
        if any(str(m["name"]).lower() == name.lower() for m in _state["models"]):
            raise DemoIntegrityError("duplicate model name")
        now = _now_iso()
        mid = _state["next_id"]["model"]
        _state["next_id"]["model"] += 1
        _state["models"].append(
            {
                "id": mid,
                "name": name,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        )
        return mid


def delete_app_model(model_id: int) -> None:
    with _lock:
        if any(int(i.get("app_model_id") or 0) == model_id for i in _state["inboxes"]):
            raise DemoIntegrityError("model in use")
        _state["models"] = [m for m in _state["models"] if int(m["id"]) != model_id]


def get_global_polling_paused() -> bool:
    with _lock:
        v = str(_state["settings"].get("global_polling_paused", "")).strip().lower()
        return v in ("1", "true", "yes")


def set_global_polling_paused(paused: bool) -> None:
    with _lock:
        _state["settings"]["global_polling_paused"] = "true" if paused else "false"


def get_agent_api_configs() -> List[Dict[str, str]]:
    with _lock:
        raw = str(_state["settings"].get("agent_api_configs", "[]"))
        try:
            data = json.loads(raw)
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


def set_agent_api_configs(configs: List[Dict[str, str]]) -> None:
    with _lock:
        _state["settings"]["agent_api_configs"] = json.dumps(configs)


def _parse_utc(ts: Optional[Any]) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    s = str(ts).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def list_due_inboxes() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    with _lock:
        due = []
        for i in _state["inboxes"]:
            if not i.get("is_active"):
                continue
            nr = _parse_utc(i.get("next_run_at"))
            if nr is None or nr <= now:
                due.append(
                    {
                        "id": i["id"],
                        "mailbox_id": i["mailbox_id"],
                        "polling_interval_minutes": i["polling_interval_minutes"],
                    }
                )
        return due


def insert_run_log(
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
    with _lock:
        rid = _state["next_id"]["runlog"]
        _state["next_id"]["runlog"] += 1
        err = error_message
        if err and len(err) > 8000:
            err = err[:8000] + "…"
        _state["run_logs"].append(
            {
                "id": rid,
                "inbox_id": inbox_id,
                "status": status,
                "fetched_count": fetched_count,
                "classified_count": classified_count,
                "tagged_count": tagged_count,
                "failures": failures,
                "latency_ms": latency_ms,
                "total_tokens_used": total_tokens_used,
                "error_message": err,
                "category_histogram": category_histogram,
                "created_at": _now_iso(),
            }
        )
        return rid


def update_inbox_run_times(
    inbox_id: int,
    *,
    last_run_at: str,
    next_run_at: str,
) -> None:
    with _lock:
        for i in _state["inboxes"]:
            if int(i["id"]) == inbox_id:
                i["last_run_at"] = last_run_at
                i["next_run_at"] = next_run_at
                i["updated_at"] = _now_iso()
                return


def bump_inbox_next_run_after_enqueue(inbox_id: int, *, grace_minutes: int = 5) -> None:
    nxt = (
        datetime.now(timezone.utc) + timedelta(minutes=max(1, int(grace_minutes)))
    ).isoformat()
    with _lock:
        for i in _state["inboxes"]:
            if int(i["id"]) == inbox_id:
                i["next_run_at"] = nxt
                i["updated_at"] = _now_iso()
                return


def compute_next_run_iso(inbox_id: int) -> str:
    with _lock:
        i = _inbox_by_id(inbox_id)
        mins = int(i["polling_interval_minutes"] or 5) if i else 5
    return (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat()


def list_run_logs_for_inbox(inbox_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    with _lock:
        logs = [lg for lg in _state["run_logs"] if int(lg["inbox_id"]) == inbox_id]
        logs.sort(key=lambda x: int(x["id"]), reverse=True)
        out = []
        for lg in logs[:lim]:
            r = dict(lg)
            out.append(r)
        return out


def fleet_summary(
    *,
    offset: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with _lock:
        inboxes = list_inboxes(
            offset=offset, limit=limit, search=search, is_active=is_active
        )
        out: List[Dict[str, Any]] = []
        for inv in inboxes:
            iid = int(inv["id"])
            emails_24h = 0
            tokens_24h = 0
            for lg in _state["run_logs"]:
                if int(lg["inbox_id"]) != iid:
                    continue
                ca = _parse_utc(lg.get("created_at"))
                if ca and ca >= since:
                    emails_24h += int(lg.get("fetched_count") or 0)
                    tu = lg.get("total_tokens_used")
                    if tu is not None:
                        tokens_24h += int(tu)
            logs_for = [lg for lg in _state["run_logs"] if int(lg["inbox_id"]) == iid]
            logs_for.sort(key=lambda x: int(x["id"]), reverse=True)
            last = logs_for[0] if logs_for else None
            last_status = last.get("status") if last else None
            health_ok = last_status == "Success" if last_status else True
            lr = inv.get("last_run_at")
            nr = inv.get("next_run_at")
            out.append(
                {
                    **inv,
                    "last_run_at": lr,
                    "next_run_at": nr,
                    "emails_processed_24h": emails_24h,
                    "token_spend_24h": tokens_24h,
                    "health_ok": health_ok,
                    "last_run_status": last_status,
                    "last_error_message": (last or {}).get("error_message"),
                }
            )
        return out


def token_trends(days: int = 7) -> List[Dict[str, Any]]:
    """Aggregate total_tokens_used from demo run_logs grouped by date."""
    if days <= 0:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with _lock:
        buckets: Dict[str, int] = {}
        for lg in _state["run_logs"]:
            ca = _parse_utc(lg.get("created_at"))
            if ca is None or ca < since:
                continue
            date_key = ca.strftime("%Y-%m-%d")
            buckets[date_key] = buckets.get(date_key, 0) + int(
                lg.get("total_tokens_used") or 0
            )
        return [{"date": d, "total_tokens": t} for d, t in sorted(buckets.items())]


def classification_breakdown(
    inbox_id: int, days: int = 7
) -> Dict[str, int]:
    """Aggregate category_histogram from demo run_logs for a given inbox.

    Returns empty dict when no histogram data is available.
    """
    if days <= 0:
        return {}
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with _lock:
        result: Dict[str, int] = {}
        for lg in _state["run_logs"]:
            if int(lg["inbox_id"]) != inbox_id:
                continue
            ca = _parse_utc(lg.get("created_at"))
            if ca is None or ca < since:
                continue
            raw = lg.get("category_histogram")
            if not raw:
                continue
            try:
                hist = json.loads(str(raw)) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(hist, dict):
                continue
            for cat, count in hist.items():
                result[cat] = result.get(cat, 0) + int(count)
        return result


def run_volume(days: int = 30) -> List[Dict[str, Any]]:
    """Aggregate run count and message count from demo run_logs grouped by date."""
    if days <= 0:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with _lock:
        buckets: Dict[str, Dict[str, int]] = {}
        for lg in _state["run_logs"]:
            ca = _parse_utc(lg.get("created_at"))
            if ca is None or ca < since:
                continue
            date_key = ca.strftime("%Y-%m-%d")
            if date_key not in buckets:
                buckets[date_key] = {"run_count": 0, "message_count": 0}
            buckets[date_key]["run_count"] += 1
            buckets[date_key]["message_count"] += int(lg.get("fetched_count") or 0)
        return [
            {
                "date": d,
                "run_count": b["run_count"],
                "message_count": b["message_count"],
            }
            for d, b in sorted(buckets.items())
        ]


# ---------------------------------------------------------------------------
# Per-message classification persistence (demo)
# ---------------------------------------------------------------------------


def insert_message_classifications(
    run_log_id: int, classifications: List[Dict[str, Any]]
) -> None:
    """Bulk-insert per-message classification rows linked to a run_log entry."""
    with _lock:
        for cls in classifications:
            cid = _state["next_id"]["msgcls"]
            _state["next_id"]["msgcls"] += 1
            _state["message_classifications"].append(
                {
                    "id": cid,
                    "run_log_id": run_log_id,
                    "email_id": str(cls.get("email_id", "")),
                    "subject": cls.get("subject"),
                    "sender": cls.get("sender"),
                    "category": str(cls.get("category", "")),
                    "received_at": cls.get("received"),
                    "created_at": _now_iso(),
                }
            )






def list_distinct_categories_by_inbox(inbox_id: int) -> List[str]:
    """Return sorted list of distinct category values for an inbox."""
    with _lock:
        run_log_ids: set[int] = set()
        for lg in _state["run_logs"]:
            if int(lg["inbox_id"]) == inbox_id:
                run_log_ids.add(int(lg["id"]))
        cats: set[str] = set()
        for mc in _state["message_classifications"]:
            if int(mc["run_log_id"]) in run_log_ids:
                c = str(mc.get("category", "")).strip()
                if c:
                    cats.add(c)
        return sorted(cats)


# --- Agentic workflows (in-memory) ---


def _agentic_by_id(wid: int) -> Optional[Dict[str, Any]]:
    for w in _state["agentic_workflows"]:
        if int(w["id"]) == wid:
            return w
    return None


def _normalize_agentic_json(r: Dict[str, Any]) -> None:
    r["is_active"] = bool(r.get("is_active"))
    for col in ("trigger_categories", "function_declarations", "agent_api_names"):
        raw = r.get(col)
        if isinstance(raw, str):
            try:
                r[col] = json.loads(raw)
            except Exception:
                r[col] = []
        elif raw is None:
            r[col] = []
    raw_filter = r.get("workflow_filter")
    if isinstance(raw_filter, str):
        try:
            r["workflow_filter"] = json.loads(raw_filter)
        except Exception:
            r["workflow_filter"] = None
    elif raw_filter is None:
        r["workflow_filter"] = None
    r["response_prompt_id"] = (
        int(r["response_prompt_id"]) if r.get("response_prompt_id") is not None else None
    )
    r["auto_send"] = bool(r.get("auto_send"))


def list_agentic_workflows() -> List[Dict[str, Any]]:
    with _lock:
        out = []
        for w in sorted(_state["agentic_workflows"], key=lambda x: (str(x.get("name", "")), x["id"])):
            r = dict(w)
            # join inbox and prompt names
            inv = _inbox_by_id(int(r["inbox_id"]))
            pt = _prompt_by_id(int(r["extraction_prompt_id"]))
            r["inbox_mailbox_id"] = inv["mailbox_id"] if inv else ""
            r["extraction_prompt_name"] = pt["name"] if pt else ""
            _normalize_agentic_json(r)
            out.append(r)
        return out


def get_agentic_workflow(workflow_id: int) -> Optional[Dict[str, Any]]:
    with _lock:
        w = _agentic_by_id(workflow_id)
        if not w:
            return None
        r = dict(w)
        inv = _inbox_by_id(int(r["inbox_id"]))
        pt = _prompt_by_id(int(r["extraction_prompt_id"]))
        r["inbox_mailbox_id"] = inv["mailbox_id"] if inv else ""
        r["extraction_prompt_name"] = pt["name"] if pt else ""
        _normalize_agentic_json(r)
        return r


def get_agentic_workflow_for_inbox(inbox_id: int) -> Optional[Dict[str, Any]]:
    """Return the first active agentic workflow for an inbox."""
    with _lock:
        for w in _state["agentic_workflows"]:
            if int(w["inbox_id"]) == inbox_id and w.get("is_active"):
                r = dict(w)
                pt = _prompt_by_id(int(r["extraction_prompt_id"]))
                r["extraction_prompt_body"] = pt["body"] if pt else ""
                if r.get("response_prompt_id") is not None:
                    rpt = _prompt_by_id(int(r["response_prompt_id"]))
                    r["response_prompt_body"] = rpt["body"] if rpt else ""
                _normalize_agentic_json(r)
                return r
    return None


def create_agentic_workflow(
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
    with _lock:
        if not _inbox_by_id(inbox_id):
            raise DemoIntegrityError("inbox fk")
        if not _prompt_by_id(extraction_prompt_id):
            raise DemoIntegrityError("prompt fk")
        if response_prompt_id is not None and not _prompt_by_id(response_prompt_id):
            raise DemoIntegrityError("response prompt fk")
        now = _now_iso()
        wid = _state["next_id"]["agentic"]
        _state["next_id"]["agentic"] += 1
        _state["agentic_workflows"].append({
            "id": wid,
            "inbox_id": inbox_id,
            "name": name,
            "extraction_prompt_id": extraction_prompt_id,
            "trigger_categories": trigger_categories_json,
            "function_declarations": function_declarations_json,
            "agent_api_names": agent_api_names_json,
            "webhook_url": webhook_url,
            "workflow_filter": workflow_filter_json,
            "response_prompt_id": response_prompt_id,
            "auto_send": auto_send,
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
        })
        return wid


def update_agentic_workflow(
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
    with _lock:
        w = _agentic_by_id(workflow_id)
        if not w:
            raise KeyError(workflow_id)
        if response_prompt_id is not None and not _prompt_by_id(response_prompt_id):
            raise DemoIntegrityError("response prompt fk")
        w.update({
            "inbox_id": inbox_id,
            "name": name,
            "extraction_prompt_id": extraction_prompt_id,
            "trigger_categories": trigger_categories_json,
            "function_declarations": function_declarations_json,
            "agent_api_names": agent_api_names_json,
            "webhook_url": webhook_url,
            "workflow_filter": workflow_filter_json,
            "response_prompt_id": response_prompt_id,
            "auto_send": auto_send,
            "is_active": is_active,
            "updated_at": _now_iso(),
        })


def delete_agentic_workflow(workflow_id: int) -> None:
    with _lock:
        _state["agentic_workflows"] = [
            w for w in _state["agentic_workflows"] if int(w["id"]) != workflow_id
        ]
