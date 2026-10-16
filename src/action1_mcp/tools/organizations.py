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
"""Organizations (one per client in an MSP enterprise)."""

from mcp.server.fastmcp import FastMCP

from ..api_client import Action1Client
from ._common import READ_ONLY, ClientFactory, list_result, run_tool


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def action1_list_organizations() -> str:
        """List the organizations (clients) in the Action1 enterprise with their id and name.

        Use an id as organization_id in the other tools.
        """

        async def action(client: Action1Client) -> dict:
            return list_result(await client.get("/organizations"))

        return await run_tool("action1_list_organizations", client_factory, action)
