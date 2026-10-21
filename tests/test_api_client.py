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
"""OAuth exchange, paging and tool behaviour against a mocked Action1 API."""

import json

import httpx
import pytest

from action1_mcp import api_client
from action1_mcp.api_client import Action1Credentials
from action1_mcp.server import _credentials_var, create_mcp_server

ENDPOINTS_PAGE = {
    "items": [
        {
            "id": "ep-1",
            "self": "/API/endpoints/managed/org-1/ep-1",
            "name": "WS-001",
            "OS": "Windows 11",
            "user": "EXAMPLE\\alice",
            "update_status": "ERROR",
            "disk": "C: 512GB",
            "video": "Example GPU",
        }
    ],
    "total_items": "120",
    "limit": "50",
    "next_page": "https://app.action1.com/api/3.0/endpoints/managed/org-1?from=50&limit=50",
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


class FakeAction1:
    """Records requests; answers the token call and then ``reply``."""

    def __init__(self, reply=None, token_status=200):
        self.requests: list[httpx.Request] = []
        self.reply = reply or (lambda r: httpx.Response(200, json={"items": []}))
        self.token_status = token_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/oauth2/token"):
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"message": "invalid client"})
            return httpx.Response(200, json={"access_token": "jwt-123", "expires_in": 3600, "token_type": "Bearer"})
        return self.reply(request)


async def _call(monkeypatch, fake: FakeAction1, tool: str, args: dict, **creds):
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    mcp = create_mcp_server()
    ctx = _credentials_var.set(
        Action1Credentials(creds.get("api_key", "key@example.com"), creds.get("secret", "YOUR_SECRET"),
                           creds.get("region", "NorthAmerica"), creds.get("default_org_id"))
    )
    try:
        content, _ = await mcp.call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


async def test_token_exchange_then_bearer_call(monkeypatch):
    fake = FakeAction1(lambda r: httpx.Response(200, json=ENDPOINTS_PAGE))
    result = await _call(monkeypatch, fake, "action1_list_endpoints", {"organization_id": "org-1", "limit": 500})

    token_req, api_req = fake.requests
    assert str(token_req.url) == "https://app.action1.com/api/3.0/oauth2/token"
    assert json.loads(token_req.content) == {"client_id": "key@example.com", "client_secret": "YOUR_SECRET"}
    assert api_req.headers["authorization"] == "Bearer jwt-123"
    assert api_req.url.path == "/api/3.0/endpoints/managed/org-1"
    assert api_req.url.params["limit"] == "200"  # clamped

    assert result["total_items"] == 120
    assert result["has_more"] is True and result["next_offset"] == 50
    item = result["items"][0]
    assert item["name"] == "WS-001" and item["update_status"] == "ERROR"
    assert "self" not in item and "disk" not in item


async def test_token_is_fetched_once_per_request(monkeypatch):
    fake = FakeAction1(lambda r: httpx.Response(200, json={"items": []}))
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    client = api_client.Action1Client(Action1Credentials("k", "s"), http_client=http)
    await client.get("/organizations")
    await client.get("/organizations")
    assert [r.url.path for r in fake.requests].count("/api/3.0/oauth2/token") == 1


async def test_bad_credentials_map_to_unauthorized(monkeypatch):
    fake = FakeAction1(token_status=400)
    result = await _call(monkeypatch, fake, "action1_list_organizations", {}, secret="wrong-secret")
    assert result["error"]["code"] == "unauthorized"
    assert "wrong-secret" not in json.dumps(result)


async def test_default_org_and_all(monkeypatch):
    fake = FakeAction1()
    await _call(monkeypatch, fake, "action1_list_missing_updates", {}, default_org_id="org-9")
    await _call(monkeypatch, fake, "action1_list_missing_updates", {"security_severity": "Critical"})
    paths = [r.url.path for r in fake.requests if not r.url.path.endswith("/oauth2/token")]
    assert paths == ["/api/3.0/updates/org-9", "/api/3.0/updates/all"]
    assert fake.requests[-1].url.params["security_severity"] == "Critical"


async def test_missing_updates_for_one_endpoint(monkeypatch):
    fake = FakeAction1()
    await _call(monkeypatch, fake, "action1_list_missing_updates", {"organization_id": "org-1", "endpoint_id": "ep-1"})
    assert fake.requests[-1].url.path == "/api/3.0/endpoints/managed/org-1/ep-1/missing-updates"


async def test_policies_need_a_specific_org(monkeypatch):
    fake = FakeAction1()
    result = await _call(monkeypatch, fake, "action1_list_policies", {})
    assert result["error"]["code"] == "invalid_argument"
    assert fake.requests == []

    await _call(monkeypatch, fake, "action1_list_policies", {"organization_id": "org-1", "offset": 50})
    assert fake.requests[-1].url.path == "/api/3.0/automations/schedules/org-1"
    assert fake.requests[-1].url.params["from"] == "50"


async def test_get_endpoint_uses_region_host(monkeypatch):
    fake = FakeAction1(lambda r: httpx.Response(200, json={"id": "ep-1", "self": "x", "name": "WS-001"}))
    result = await _call(monkeypatch, fake, "action1_get_endpoint", {"endpoint_id": "ep-1"}, region="Europe")
    assert fake.requests[-1].url.host == "app.eu.action1.com"
    assert fake.requests[-1].url.path == "/api/3.0/endpoints/managed/all/ep-1"
    assert result == {"id": "ep-1", "name": "WS-001"}


def test_size_cap_continues_after_the_last_returned_item():
    from action1_mcp._json import dump_json_capped
    from action1_mcp.tools._common import list_result

    doc = {"items": [{"id": i, **{f"f{j}": f"value-{j:04d}" for j in range(120)}} for i in range(50)],
           "total_items": 500, "next_page": "https://app.action1.com/api/3.0/endpoints?from=100&limit=50"}
    out = json.loads(dump_json_capped(list_result(doc)))
    n = len(out["items"])
    assert 0 < n < 50 and out["count"] == n
    assert out["next_offset"] == 50 + n and "_resume" not in out
