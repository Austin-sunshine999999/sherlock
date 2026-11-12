"""Authenticated MCP adapter for Sherlock's public username search."""
from __future__ import annotations

import asyncio
import hmac
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from sherlock_project import __file__ as sherlock_package_file
from sherlock_project.notify import QueryNotify
from sherlock_project.result import QueryStatus
from sherlock_project.sherlock import sherlock as run_sherlock
from sherlock_project.sites import SitesInformation

REQUIRED_SCOPE = "sherlock:search"
BEARER_TOKEN = os.environ.get("MCP_BEARER_TOKEN", "")
PUBLIC_BASE_URL = os.environ.get("MCP_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
RESOURCE_URL = f"{PUBLIC_BASE_URL}/mcp"
ISSUER_URL = os.environ.get("MCP_ISSUER_URL", PUBLIC_BASE_URL)
ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get(
        "MCP_ALLOWED_HOSTS", "127.0.0.1:8000,localhost:8000"
    ).split(",")
    if value.strip()
]

if not BEARER_TOKEN:
    raise RuntimeError("Set MCP_BEARER_TOKEN before starting the Sherlock MCP server.")

DATA_FILE = Path(sherlock_package_file).resolve().parent / "resources" / "data.json"
if not DATA_FILE.is_file():
    raise RuntimeError(f"Sherlock site data file not found: {DATA_FILE}")


class EnvironmentTokenVerifier(TokenVerifier):
    """Verify a deployment-managed bearer token without storing it in source."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, BEARER_TOKEN):
            return None
        return AccessToken(
            token=token,
            client_id="sherlock-mcp-client",
            scopes=[REQUIRED_SCOPE],
            expires_at=int(time.time()) + 3600,
            resource=RESOURCE_URL,
            subject="authenticated-user",
        )


mcp = MCPServer(
    "sherlock-username-search",
    token_verifier=EnvironmentTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(ISSUER_URL),
        resource_server_url=AnyHttpUrl(RESOURCE_URL),
        required_scopes=[REQUIRED_SCOPE],
        validate_token_resource=True,
    ),
)


def _search_username(
    username: str, site_names: list[str] | None, timeout_seconds: int
) -> dict[str, object]:
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", username):
        raise ValueError(
            "Username must be 1–64 characters and contain only letters, numbers, dots, underscores, or hyphens."
        )
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout_seconds must be between 1 and 30.")
    if site_names is not None and (not site_names or len(site_names) > 50):
        raise ValueError("site_names must contain between 1 and 50 site names.")

    sites = SitesInformation(str(DATA_FILE), honor_exclusions=True)
    sites.remove_nsfw_sites()
    all_site_data = {site.name: site.information for site in sites}

    if site_names is None:
        selected_site_data = all_site_data
    else:
        requested = {name.casefold() for name in site_names}
        selected_site_data = {
            name: data for name, data in all_site_data.items()
            if name.casefold() in requested
        }
        found_names = {name.casefold() for name in selected_site_data}
        unknown = sorted(name for name in site_names if name.casefold() not in found_names)
        if unknown:
            raise ValueError(f"Unknown Sherlock site name(s): {', '.join(unknown)}")

    results = run_sherlock(
        username,
        selected_site_data,
        QueryNotify(),
        timeout=timeout_seconds,
    )

    matches: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for site_name, result in results.items():
        status = result["status"].status
        status_name = str(status)
        counts[status_name] = counts.get(status_name, 0) + 1
        if status is QueryStatus.CLAIMED:
            matches.append({
                "site": site_name,
                "profile_url": result.get("url_user") or "",
                "site_url": result.get("url_main") or "",
            })

    return {
        "username": username,
        "checked_sites": len(results),
        "found_count": len(matches),
        "status_counts": counts,
        "matches": matches,
        "caveat": "Sherlock checks public profile URLs and can return false positives; verify each result manually.",
    }


@mcp.tool(
    description=(
        "Search a public username across Sherlock-supported sites. "
        "Use for authorized research; results are heuristic and must be verified."
    )
)
async def search_public_username(
    username: str,
    site_names: list[str] | None = None,
    timeout_seconds: int = 15,
) -> dict[str, object]:
    """Return matching public profile URLs for one username."""
    return await asyncio.to_thread(
        _search_username, username, site_names, timeout_seconds
    )


host_allowlist = ALLOWED_HOSTS or [urlsplit(PUBLIC_BASE_URL).netloc]
app = mcp.streamable_http_app(
    transport_security=TransportSecuritySettings(allowed_hosts=host_allowlist)
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
