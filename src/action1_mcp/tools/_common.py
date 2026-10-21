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
"""Shared argument types, result shaping and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from urllib.parse import parse_qs, quote, urlsplit

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import Action1Client, Action1Error

logger = logging.getLogger("action1_mcp.tools")

ClientFactory = Callable[[], Action1Client | None]

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured",
    "Action1 credentials are missing for this request (X-Action1-API-Key / X-Action1-Secret).",
    False,
)

OrganizationId = Annotated[
    str | None,
    Field(description="Organization id from action1_list_organizations. Defaults to the connection's default."),
]
Limit = Annotated[int | None, Field(description=f"Max items (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).")]
Offset = Annotated[int | None, Field(description="Index of the first item; use next_offset from a previous call.")]
TextFilter = Annotated[
    str | None, Field(description="Case-insensitive text; items with any field containing it are returned.")
]


def resolve_org(client: Action1Client, organization_id: str | None, allow_all: bool) -> str:
    org = (organization_id or "").strip() or (client.default_org_id or "")
    if org:
        return org
    if allow_all:
        return "all"
    raise ValueError(
        "organization_id is required (no default organization is configured); "
        "get one from action1_list_organizations."
    )


def page_params(limit: int | None, offset: int | None) -> dict[str, Any]:
    size = DEFAULT_LIMIT if limit is None else max(1, min(int(limit), MAX_LIMIT))
    params: dict[str, Any] = {"limit": size}
    if offset:
        params["from"] = max(0, int(offset))
    return params


def _next_offset(document: dict) -> int | None:
    nxt = document.get("next_page")
    if not isinstance(nxt, str) or not nxt:
        return None
    values = parse_qs(urlsplit(nxt).query).get("from")
    try:
        return int(values[0]) if values else None
    except ValueError:
        return None


def strip_links(item: Any) -> Any:
    if isinstance(item, dict):
        return {k: v for k, v in item.items() if k != "self"}
    return item


def list_result(document: Any, shape: Callable[[Any], Any] = strip_links) -> dict[str, Any]:
    """Shape an Action1 ResultPage as ``{items, count, total_items, has_more, next_offset}``."""
    doc = document if isinstance(document, dict) else {}
    items = [shape(i) for i in doc.get("items") or []]
    next_offset = _next_offset(doc)
    total = doc.get("total_items")
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        pass
    return {
        "items": items,
        "count": len(items),
        "total_items": total,
        "has_more": next_offset is not None,
        "next_offset": next_offset,
    }


def path_id(value: Any) -> str:
    """Percent-encode an ID for use as a single URL path segment."""
    return quote(str(value).strip(), safe="")


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[Action1Client], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    if client.header_error:
        return error_envelope("invalid_argument", client.header_error, False)
    started = time.monotonic()
    try:
        result = await action(client)
    except Action1Error as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
