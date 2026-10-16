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
"""Credential middleware: 401 on missing headers, region handling, isolation."""

import asyncio

import pytest
from starlette.testclient import TestClient

from action1_mcp.__main__ import build_http_app
from action1_mcp.server import (
    GatewayCredentialsMiddleware,
    _credentials_var,
    create_mcp_server,
    get_client_from_context,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
CREDS = {"X-Action1-API-Key": "api-key-example@action1.com", "X-Action1-Secret": "YOUR_SECRET"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("drop", ["X-Action1-API-Key", "X-Action1-Secret"])
def test_missing_header_returns_401(drop):
    headers = MCP_HEADERS | {k: v for k, v in CREDS.items() if k != drop}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=headers)
    assert resp.status_code == 401
    body = resp.json()
    assert body["required_headers"] == ["X-Action1-API-Key", "X-Action1-Secret"]
    assert drop in body["message"]


def test_unknown_region_returns_400():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS | {"X-Action1-Region": "AsiaPacific"})
    assert resp.status_code == 400
    assert "Europe" in resp.json()["allowed_values"]


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    assert "action1_list_endpoints" in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(GatewayCredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


BASE = [(b"x-action1-api-key", b"key"), (b"x-action1-secret", b"secret")]


@pytest.mark.parametrize(
    "value,host",
    [
        (None, "app.action1.com"),
        (b"", "app.action1.com"),
        (b"us", "app.action1.com"),
        (b"NorthAmerica", "app.action1.com"),
        (b"NA-2", "app.na-2.action1.com"),
        (b"europe", "app.eu.action1.com"),
        (b"uk", "app.uk.action1.com"),
        (b"Australia", "app.au.action1.com"),
    ],
)
def test_region_values(value, host):
    headers = BASE + ([(b"x-action1-region", value)] if value is not None else [])
    seen = _run_middleware(headers)
    assert seen["client"].base_url == f"https://{host}/api/3.0"
    assert _credentials_var.get() is None


def test_default_org_header_reaches_client():
    seen = _run_middleware(BASE + [(b"x-action1-default-org-id", b"org-123")])
    assert seen["client"].default_org_id == "org-123"
    assert _run_middleware(BASE)["client"].default_org_id is None


def test_concurrent_requests_do_not_share_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().api_key
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().api_key))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(key: bytes) -> dict:
        return {"type": "http", "path": "/mcp", "headers": [(b"x-action1-api-key", key), (b"x-action1-secret", b"s")]}

    async def both():
        await asyncio.gather(middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send))

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_secrets():
    seen = _run_middleware([(b"x-action1-api-key", b"secret-key"), (b"x-action1-secret", b"secret-value")])
    text = repr(seen["credentials"])
    assert "secret-key" not in text and "secret-value" not in text
