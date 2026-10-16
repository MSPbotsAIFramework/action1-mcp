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
"""Automations (formerly called policies): scheduled patch deployments and scripts."""

from mcp.server.fastmcp import FastMCP

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
    async def action1_list_policies(
        organization_id: OrganizationId = None,
        limit: Limit = None,
        offset: Offset = None,
        filter: TextFilter = None,
    ) -> str:
        """List scheduled automations (policies) in one organization: actions, targets, last/next run.

        Needs a specific organization_id ('all' is not supported here).
        """

        async def action(client: Action1Client) -> dict:
            org = resolve_org(client, organization_id, allow_all=False)
            params = page_params(limit, offset) | {"filter": filter}
            return list_result(await client.get(f"/automations/schedules/{path_id(org)}", params))

        return await run_tool("action1_list_policies", client_factory, action)
