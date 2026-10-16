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
"""Per-area tool guide."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import Action1Client
from ._common import READ_ONLY, ClientFactory, run_tool

DOMAIN_TOOLS: dict[str, dict[str, str]] = {
    "endpoints": {
        "action1_list_endpoints": "List managed endpoints with status filters.",
        "action1_get_endpoint": "Full record of one endpoint.",
    },
    "organizations": {
        "action1_list_organizations": "Organizations (clients) in the enterprise.",
    },
    "policies": {
        "action1_list_policies": "Scheduled automations in one organization.",
    },
    "updates": {
        "action1_list_missing_updates": "Missing OS and third-party updates, per organization or endpoint.",
    },
}


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def action1_navigate(
        domain: Annotated[
            Literal["endpoints", "organizations", "policies", "updates"],
            Field(description="Area to show tools for."),
        ],
    ) -> str:
        """Show which tools cover one area: endpoints, organizations, policies or updates.

        All tools are always available; this is only a guide. Makes no API call.
        """

        async def action(_client: Action1Client) -> dict:
            return {"domain": domain, "tools": DOMAIN_TOOLS[domain]}

        return await run_tool("action1_navigate", client_factory, action)
