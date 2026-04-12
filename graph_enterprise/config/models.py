"""Per-mailbox and run policy models (Part 3: per-inbox categories, policy caps)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class FetchTimeWindowMode(str, Enum):
    """How scheduled runs choose the receivedDateTime window."""

    local_today = "local_today"
    rolling_hours = "rolling_hours"
    since_last_run = "since_last_run"


class SubjectKeywordMode(str, Enum):
    """Combine subject keyword predicates in $filter."""

    all = "all"
    any = "any"


class AttachmentFilter(str, Enum):
    """Tri-state attachment filter for Graph hasAttachments."""

    any = "any"
    yes = "yes"
    no = "no"


class InboxFetchFilter(BaseModel):
    """Microsoft Graph message predicates and time window (stored as inbox.fetch_filter_json)."""

    unread_only: bool = Field(
        default=True,
        description="When true, add isRead eq false to $filter.",
    )
    time_window_mode: FetchTimeWindowMode = Field(
        default=FetchTimeWindowMode.local_today,
        description="local_today: mailbox TZ midnight..midnight; rolling_hours: last N hours; "
        "since_last_run: last_run_at..now (fallback if never run).",
    )
    rolling_hours: Optional[int] = Field(
        default=None,
        ge=1,
        le=720,
        description="Required when time_window_mode is rolling_hours.",
    )
    sender_allowlist: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="If non-empty, from address must match one entry (email, @domain, or bare domain).",
    )
    sender_denylist: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Exclude matching senders (deny wins; combined with allowlist as allow AND NOT deny).",
    )
    subject_keywords: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Subject contains predicates (see subject_keyword_mode).",
    )
    subject_keyword_mode: SubjectKeywordMode = Field(
        default=SubjectKeywordMode.any,
        description="all: AND contains(); any: OR contains().",
    )
    body_keywords: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Passed as Microsoft Graph $search (experimental); subject-only filtering uses $filter.",
    )
    importance_levels: List[str] = Field(
        default_factory=list,
        max_length=3,
        description="If non-empty, importance must be one of low, normal, high.",
    )
    has_attachments: AttachmentFilter = Field(
        default=AttachmentFilter.any,
        description="Restrict to messages with or without attachments.",
    )
    category_include_any: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Message must have at least one of these Outlook categories.",
    )
    category_exclude_any: List[str] = Field(
        default_factory=list,
        max_length=50,
        description="Message must not have any of these Outlook categories.",
    )

    @field_validator(
        "sender_allowlist",
        "sender_denylist",
        "subject_keywords",
        "body_keywords",
        "category_include_any",
        "category_exclude_any",
        mode="before",
    )
    @classmethod
    def _coerce_str_lists(cls, v: object) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(x) for x in v]
        raise TypeError("expected list or string")

    @field_validator("sender_allowlist", "sender_denylist", mode="after")
    @classmethod
    def _normalize_senders(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for raw in v:
            s = raw.strip()
            if not s:
                continue
            out.append(s.lower())
        return out

    @field_validator("subject_keywords", "body_keywords", mode="after")
    @classmethod
    def _strip_keywords(cls, v: List[str]) -> List[str]:
        return [x.strip() for x in v if x.strip()]

    @field_validator("category_include_any", "category_exclude_any", mode="after")
    @classmethod
    def _strip_categories(cls, v: List[str]) -> List[str]:
        return [x.strip() for x in v if x.strip()]

    @field_validator("importance_levels", mode="after")
    @classmethod
    def _importance(cls, v: List[str]) -> List[str]:
        allowed = {"low", "normal", "high"}
        out: List[str] = []
        for raw in v:
            s = raw.strip().lower()
            if not s:
                continue
            if s not in allowed:
                raise ValueError(f"importance_levels: invalid value {raw!r} (use low, normal, high)")
            if s not in out:
                out.append(s)
        return out

    @model_validator(mode="after")
    def _rolling_hours_required(self) -> InboxFetchFilter:
        if self.time_window_mode == FetchTimeWindowMode.rolling_hours:
            if self.rolling_hours is None:
                raise ValueError("rolling_hours is required when time_window_mode is rolling_hours")
        return self


def parse_inbox_fetch_filter(raw: Union[str, dict, InboxFetchFilter, None]) -> InboxFetchFilter:
    """Build InboxFetchFilter from DB JSON / dict; invalid or empty → defaults (legacy behavior)."""
    if raw is None:
        return InboxFetchFilter()
    if isinstance(raw, InboxFetchFilter):
        return raw
    if isinstance(raw, dict):
        if not raw:
            return InboxFetchFilter()
        try:
            return InboxFetchFilter.model_validate(raw)
        except Exception:
            return InboxFetchFilter()
    s = str(raw).strip()
    if not s:
        return InboxFetchFilter()
    try:
        return InboxFetchFilter.model_validate_json(s)
    except Exception:
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return InboxFetchFilter.model_validate(obj)
        except Exception:
            pass
    return InboxFetchFilter()


def parse_subject_classify_rules(
    raw: Union[str, dict, list, None],
) -> List[SubjectClassifyRule]:
    """Parse inbox.subject_classify_rules_json into a list; invalid entries dropped."""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            items = json.loads(s)
        except Exception:
            return []
    else:
        return []
    if not isinstance(items, list):
        return []
    out: List[SubjectClassifyRule] = []
    for item in items[:_MAX_SUBJECT_RULES]:
        if not isinstance(item, dict):
            continue
        try:
            out.append(SubjectClassifyRule.model_validate(item))
        except Exception:
            continue
    return out


def parse_last_run_at_utc(value: Any) -> Optional[datetime]:
    """Normalize inbox.last_run_at from SQL or ISO string to aware UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_MAX_SUBJECT_RULES = 20
_SUBJECT_PATTERN_MAX_LEN = 512
_CATEGORY_NAME_MAX_LEN = 512


class SubjectClassifyRule(BaseModel):
    """Match message subject with SQL LIKE-style pattern (% and _); first rule wins."""

    pattern: str = Field(
        ...,
        min_length=1,
        max_length=_SUBJECT_PATTERN_MAX_LEN,
        description="Case-insensitive LIKE pattern (e.g. %Automated%).",
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=_CATEGORY_NAME_MAX_LEN,
        description="Taxonomy label; must exist in the inbox classification set.",
    )


class CategoryDefinition(BaseModel):
    """Single allowed label with prompt context for Gemini."""

    name: str = Field(..., description="Outlook/Graph category string")
    description: str = Field(
        default="",
        description="Short definition or examples for the model prompt",
    )


class RunPolicy(BaseModel):
    """Safety and volume controls for a scheduled run."""

    polling_interval_minutes: int = Field(
        default=5,
        ge=1,
        le=1440,
        description="Minutes until the scheduler should run this inbox again after a completed run.",
    )
    max_messages_per_run: Optional[int] = Field(
        default=None,
        description="Optional cap; log/alert if pagination truncates due to cap",
    )
    timezone: str = Field(
        default="UTC",
        description="IANA timezone for 'that day' window (e.g. America/Phoenix)",
    )
    mail_folder: str = Field(
        default="inbox",
        description=(
            "Graph folder: well-known id (inbox, sentitems, deleteditems, junkemail) "
            "or a mailFolder id. Use 'all' for /users/.../messages (entire mailbox)."
        ),
    )
    patch_max_workers: int = Field(
        default=4,
        ge=1,
        le=4,
        description=(
            "Max concurrent Microsoft Graph PATCH threads for category write-back; "
            "limited to 4 by Microsoft Graph API rate limits."
        ),
    )


class AppModelDefinition(BaseModel):
    """Available Gemini model name."""

    id: Optional[int] = None
    name: str = Field(..., description="Gemini model name (e.g. gemini-2.5-flash-lite)")
    is_active: bool = True


class MailboxPipelineConfig(BaseModel):
    """One mailbox entry from allowlisted config (UPN or shared mailbox SMTP)."""

    inbox_id: Optional[int] = Field(
        default=None,
        description="Primary key in SQL Server config DB; used for run_log FK.",
    )
    is_active: bool = Field(
        default=True,
        description="When false, scheduler skips this inbox without deleting its config.",
    )
    graph_write_back_enabled: bool = Field(
        default=True,
        description="When false, pipeline classifies but skips Graph category PATCH (dry-run).",
    )
    mailbox_id: str = Field(
        ...,
        description="User principal name or shared mailbox address Graph resolves",
    )
    categories: List[CategoryDefinition] = Field(
        ...,
        min_length=1,
        description="Allowed category literals and definitions for this inbox",
    )
    run_policy: RunPolicy = Field(default_factory=RunPolicy)
    prompt_template: Optional[str] = Field(
        default=None,
        description="Optional full prompt template loaded from external config storage.",
    )
    app_model: Optional[AppModelDefinition] = Field(
        default=None,
        description="Selected Gemini model for this inbox.",
    )
    fetch_filter: InboxFetchFilter = Field(
        default_factory=InboxFetchFilter,
        description="Graph list query filters ($filter / $search).",
    )
    last_run_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of last completed run; used for since_last_run window.",
    )
    subject_classify_enabled: bool = Field(
        default=False,
        description="When true, apply subject LIKE rules before Gemini for non-matches.",
    )
    subject_classify_rules: List[SubjectClassifyRule] = Field(
        default_factory=list,
        max_length=_MAX_SUBJECT_RULES,
        description="Ordered rules; first pattern match assigns category.",
    )
