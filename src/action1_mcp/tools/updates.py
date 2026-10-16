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
"""Missing updates (OS patches and third-party software updates)."""

from typing import Annotated, Literal

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


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def action1_list_missing_updates(
        organization_id: OrganizationId = None,
        limit: Limit = None,
        offset: Offset = None,
        endpoint_id: Annotated[
            str | None, Field(description="Only the updates missing on this endpoint.")
        ] = None,
        security_severity: Annotated[
            Literal["Critical", "-Critical", "Important", "Moderate", "Low", "Unspecified", "Other"] | None,
            Field(description="Severity; '-Critical' means everything except Critical."),
        ] = None,
        approval_status: Annotated[
            Literal["New", "Approved", "Declined", "-Declined"] | None,
            Field(description="Approval state; '-Declined' means not declined."),
        ] = None,
        filter: TextFilter = None,
    ) -> str:
        """List missing OS and third-party updates: name, version, severity, approval status, release date.

        Organization-wide by default (organization_id 'all' covers every
        organization); pass endpoint_id for one device.
        """

        async def action(client: Action1Client) -> dict:
            org = resolve_org(client, organization_id, allow_all=True)
            params = page_params(limit, offset) | {
                "security_severity": security_severity,
                "approval_status": approval_status,
                "filter": filter,
            }
            if endpoint_id:
                path = f"/endpoints/managed/{path_id(org)}/{path_id(endpoint_id)}/missing-updates"
            else:
                path = f"/updates/{path_id(org)}"
            return list_result(await client.get(path, params))

        return await run_tool("action1_list_missing_updates", client_factory, action)
