# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import Action1Client, Action1Credentials
from .config import DEFAULT_REGION, REGION_BASE_URLS, Settings, resolve_region

HEADER_API_KEY = "X-Action1-API-Key"
HEADER_SECRET = "X-Action1-Secret"
HEADER_REGION = "X-Action1-Region"
HEADER_DEFAULT_ORG = "X-Action1-Default-Org-Id"
REQUIRED_HEADERS = [HEADER_API_KEY, HEADER_SECRET]
OPTIONAL_HEADERS = [HEADER_REGION, HEADER_DEFAULT_ORG]

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[Action1Credentials | None] = contextvars.ContextVar(
    "action1_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "action1_request_id", default="-"
)

INSTRUCTIONS = (
    "Action1 is a cloud patch management and endpoint management platform. MSPs "
    "use it to inventory Windows/Mac/Linux endpoints, find missing OS and "
    "third-party updates and vulnerabilities, and run automations (scheduled "
    "patch deployments, scripts). Data is split into organizations (one per "
    "client); an enterprise holds many organizations.\n"
    "Typical flows:\n"
    "- Find a client: action1_list_organizations, then pass its id as "
    "organization_id.\n"
    "- Device questions: action1_list_endpoints (filter by status, update "
    "status, text) -> action1_get_endpoint for full detail.\n"
    "- Patch exposure: action1_list_missing_updates (optionally for one "
    "endpoint_id, or by security_severity).\n"
    "- Automation setup: action1_list_policies lists scheduled automations.\n"
    "organization_id defaults to the connection's default organization; for "
    "endpoints and updates 'all' covers every organization. Lists return "
    "{items, total_items, has_more, next_offset}; pass next_offset as offset to "
    "continue. All tools are read-only."
)


def get_client_from_context() -> Action1Client | None:
    """The Action1 client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return Action1Client(credentials)


class GatewayCredentialsMiddleware:
    """Reads X-Action1-* headers on /mcp requests into the request context.

    Missing required headers -> 401 listing them. A malformed region does not block
    the request (tools/list must work with any values); tools report it instead.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        api_key = (request.headers.get(HEADER_API_KEY) or "").strip()
        secret = (request.headers.get(HEADER_SECRET) or "").strip()
        default_org = (request.headers.get(HEADER_DEFAULT_ORG) or "").strip() or None
        region = resolve_region(request.headers.get(HEADER_REGION))

        missing = [h for h, v in ((HEADER_API_KEY, api_key), (HEADER_SECRET, secret)) if not v]
        if missing:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": "Required header(s) missing: " + ", ".join(missing),
                    "required_headers": REQUIRED_HEADERS,
                    "optional_headers": OPTIONAL_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        header_error = None
        if region is None:
            header_error = f"{HEADER_REGION} must be one of: {', '.join(REGION_BASE_URLS)}"
            region = DEFAULT_REGION

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(Action1Credentials(api_key, secret, region, default_org, header_error))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every Action1 tool."""
    mcp = EnvelopeFastMCP(
        name="action1-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], Action1Client | None] = get_client_from_context

    from .tools import endpoints, navigation, organizations, policies, updates

    for module in (navigation, organizations, endpoints, policies, updates):
        module.register(mcp, client_factory)

    return mcp
