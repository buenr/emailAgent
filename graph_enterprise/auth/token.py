"""MSAL app-only token acquisition for Microsoft Graph (service principal)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

try:
    import msal
except ImportError as exc:  # pragma: no cover - optional dependency
    msal = None  # type: ignore
    _MSAL_IMPORT_ERROR = exc
else:
    _MSAL_IMPORT_ERROR = None

GRAPH_SCOPE_DEFAULT = ["https://graph.microsoft.com/.default"]


@dataclass(frozen=True)
class MsalClientCredentialsConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    scopes: Optional[List[str]] = None


class GraphTokenProvider:
    """Wraps MSAL confidential client for client-credentials flow."""

    def __init__(self, config: MsalClientCredentialsConfig) -> None:
        if msal is None:
            raise ImportError(
                "msal is required for GraphTokenProvider. "
                "Install dependencies from requirements.txt (msal)"
            ) from _MSAL_IMPORT_ERROR
        self._config = config
        self._app = msal.ConfidentialClientApplication(
            client_id=config.client_id,
            client_credential=config.client_secret,
            authority=f"https://login.microsoftonline.com/{config.tenant_id}",
        )

    def acquire_token(self) -> str:
        scopes = self._config.scopes or GRAPH_SCOPE_DEFAULT
        result = self._app.acquire_token_for_client(scopes=scopes)
        if "access_token" not in result:
            err = result.get("error_description") or result.get("error") or str(result)
            raise RuntimeError(f"MSAL token acquisition failed: {err}")
        return result["access_token"]
