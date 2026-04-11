"""List messages for a mailbox within a UTC time window (paginated)."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from ..config.models import InboxFetchFilter
from .http_client import GRAPH_ROOT, GraphHttpClient
from .message_filter import (
    build_search_from_body_keywords,
    extra_filter_clauses_from_fetch_filter,
)


def _odata_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def messages_collection_url(mailbox_id: str, mail_folder: str) -> str:
    """
    Inbox-only: ``mail_folder='inbox'`` → .../mailFolders/inbox/messages.

    ``/users/{id}/messages`` includes Deleted Items, Junk, and other folders;
    folder-scoped URLs do not.
    """
    encoded_mailbox = urllib.parse.quote(mailbox_id, safe="")
    root = f"{GRAPH_ROOT}/users/{encoded_mailbox}"
    if mail_folder.lower() == "all":
        return f"{root}/messages"
    enc_folder = urllib.parse.quote(mail_folder, safe="")
    return f"{root}/mailFolders/{enc_folder}/messages"


@dataclass
class GraphMessageFetcher:
    """Fetches messages using $filter, $select, $top, and @odata.nextLink."""

    client: GraphHttpClient
    page_size: int = 100
    first_request_id: Optional[str] = None

    def iter_unread_for_interval(
        self,
        mailbox_id: str,
        start_utc: datetime,
        end_utc: datetime,
        select_fields: Optional[List[str]] = None,
        max_messages: Optional[int] = None,
        mail_folder: str = "inbox",
        fetch_filter: Optional[InboxFetchFilter] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Unread-only messages in [start_utc, end_utc)."""
        yield from self.iter_messages_for_interval(
            mailbox_id,
            start_utc,
            end_utc,
            unread_only=True,
            select_fields=select_fields,
            max_messages=max_messages,
            mail_folder=mail_folder,
            fetch_filter=fetch_filter,
        )

    def iter_messages_for_interval(
        self,
        mailbox_id: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        unread_only: bool = False,
        select_fields: Optional[List[str]] = None,
        max_messages: Optional[int] = None,
        mail_folder: str = "inbox",
        fetch_filter: Optional[InboxFetchFilter] = None,
    ) -> Iterator[Dict[str, Any]]:
        conditions = [
            f"receivedDateTime ge {_odata_datetime(start_utc)}",
            f"receivedDateTime lt {_odata_datetime(end_utc)}",
        ]
        if unread_only:
            conditions.insert(0, "isRead eq false")
        if fetch_filter is not None:
            conditions.extend(extra_filter_clauses_from_fetch_filter(fetch_filter))
        filt = " and ".join(conditions)
        default_select = [
            "id",
            "subject",
            "bodyPreview",
            "body",
            "sender",
            "receivedDateTime",
            "importance",
            "isRead",
            "categories",
            "hasAttachments",
        ]
        if select_fields:
            merged = list(dict.fromkeys(list(select_fields) + ["id", "hasAttachments"]))
            if unread_only and "isRead" not in merged:
                merged.append("isRead")
            select = merged
        else:
            select = default_select
        base = messages_collection_url(mailbox_id, mail_folder)
        params: Dict[str, Any] = {
            "$filter": filt,
            "$select": ",".join(select),
            "$expand": "attachments($select=name,contentType,size)",
            "$top": self.page_size,
            "$orderby": "receivedDateTime asc",
        }
        if fetch_filter is not None:
            search_q = build_search_from_body_keywords(fetch_filter.body_keywords)
            if search_q:
                params["$search"] = search_q
        next_url: Optional[str] = None
        yielded = 0

        while True:
            if next_url:
                resp = self.client.get(next_url)
            else:
                resp = self.client.get(base, params=params)
            resp.raise_for_status()
            if self.first_request_id is None:
                self.first_request_id = resp.headers.get("request-id")
            payload = resp.json()
            for item in payload.get("value", []):
                yield item
                yielded += 1
                if max_messages is not None and yielded >= max_messages:
                    return
            next_url = payload.get("@odata.nextLink")
            if not next_url:
                break
