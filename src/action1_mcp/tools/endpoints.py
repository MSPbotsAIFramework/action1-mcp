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
"""Managed endpoints (devices running the Action1 agent)."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import Action1Client
from ._common import (
    READ_ONLY,
    ClientFactory,
    Limit,
    Offset,
    OrganizationId,
    TextFilter,
    list_result,
    page_params,
    path_id,
    resolve_org,
    run_tool,
)

# Fields kept in the list view; action1_get_endpoint returns everything.
_SUMMARY_FIELDS = (
    "id",
    "name",
    "device_name",
    "address",
    "platform",
    "OS",
    "user",
    "last_seen",
    "online_status",
    "status",
    "update_status",
    "vulnerability_status",
    "missing_updates",
    "reboot_required",
    "agent_version",
    "organization_id",
    "manufacturer",
    "serial",
    "comment",
)


def summarize(endpoint: Any) -> Any:
    if not isinstance(endpoint, dict):
        return endpoint
    return {k: endpoint[k] for k in _SUMMARY_FIELDS if endpoint.get(k) not in (None, "")}


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def action1_list_endpoints(
        organization_id: OrganizationId = None,
        limit: Limit = None,
        offset: Offset = None,
        filter: TextFilter = None,
        status: Annotated[
            Literal["Connected", "Disconnected", "Pending Uninstall"] | None,
            Field(description="Agent connection status."),
        ] = None,
        online_status: Annotated[
            Literal["SUCCESS", "WARNING", "ERROR"] | None,
            Field(description="Last seen: SUCCESS <7 days, WARNING 8-30 days, ERROR >30 days."),
        ] = None,
        update_status: Annotated[
            Literal["SUCCESS", "WARNING", "ERROR"] | None,
            Field(description="SUCCESS no missing updates, WARNING non-critical missing, ERROR critical missing."),
        ] = None,
        reboot_required: Annotated[Literal["Yes", "No"] | None, Field(description="Pending reboot.")] = None,
    ) -> str:
        """List managed endpoints: name, OS, user, last seen, update and vulnerability status.

        organization_id 'all' covers every organization. Use action1_get_endpoint for one device's full record.
        """

        async def action(client: Action1Client) -> dict:
            org = resolve_org(client, organization_id, allow_all=True)
            params = page_params(limit, offset) | {
                "filter": filter,
                "status": status,
                "online_status": online_status,
                "update_status": update_status,
                "reboot_required": reboot_required,
            }
            return list_result(await client.get(f"/endpoints/managed/{path_id(org)}", params), summarize)

        return await run_tool("action1_list_endpoints", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def action1_get_endpoint(
        endpoint_id: Annotated[str, Field(description="Endpoint id from action1_list_endpoints.")],
        organization_id: OrganizationId = None,
    ) -> str:
        """Get one endpoint's full record: hardware, OS, agent, network and missing update counts."""

        async def action(client: Action1Client) -> Any:
            org = resolve_org(client, organization_id, allow_all=True)
            doc = await client.get(f"/endpoints/managed/{path_id(org)}/{path_id(endpoint_id)}")
            return {k: v for k, v in doc.items() if k != "self"} if isinstance(doc, dict) else doc

        return await run_tool("action1_get_endpoint", client_factory, action)
