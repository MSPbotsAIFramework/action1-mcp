# Action1 MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Action1](https://www.action1.com)
API. It lets an AI agent read an MSP's Action1 data: organizations (clients), managed
endpoints, missing OS and third-party updates, and scheduled automations. All tools are
read-only.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored; the OAuth access token is obtained per request and not cached
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Action1-API-Key` | Yes | string | none | - | API credential Client ID | `api-key-xxxx@action1.com` |
| `X-Action1-Secret` | Yes | string | none | - | API credential Client Secret | `YOUR_SECRET` |
| `X-Action1-Region` | No | string | `NorthAmerica` | `NorthAmerica` (`us`, `na`), `NorthAmerica-2` (`NA-2`), `Europe` (`eu`), `UnitedKingdom` (`uk`), `Australia` (`au`); case-insensitive | Action1 data centre of the account | `Europe` |
| `X-Action1-Default-Org-Id` | No | string | none | - | Organization used when a tool call omits `organization_id` | `your-org-id` |

Where to get them:

- **Client ID / Secret**: in the Action1 console, open the **API Credentials** page and create a
  credential. The server exchanges them for a short-lived OAuth token on each request.
- **Region**: the data centre your Action1 account lives in (the console host, e.g.
  `app.eu.action1.com` = `Europe`).
- **Organization id**: returned by `action1_list_organizations`.
- **Permissions**: the credential's role needs `view_endpoints` (endpoints), `view_automations`
  (policies) and one of `approve_updates` / `view_dashboards` / `manage_automations` (missing
  updates).

A request to `/mcp` without the required headers gets HTTP 401 with the list of required
headers. An unknown region does not block `tools/list`; tools then return an `invalid_argument`
error naming the allowed regions.

## Tools

All tools return a JSON string. List tools return `{items, count, total_items, has_more,
next_offset}`; pass `next_offset` as `offset` to get the next page. `limit` defaults to 50
(max 200). `organization_id` defaults to `X-Action1-Default-Org-Id`; for endpoints and updates
the value `all` (also used when no default is set) covers every organization.

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `action1_navigate` | Show the tools of one area | **domain** (`endpoints`, `organizations`, `policies`, `updates`) |
| `action1_list_organizations` | List organizations (clients) | - |
| `action1_list_endpoints` | List managed endpoints | organization_id, limit, offset, filter, status, online_status, update_status, reboot_required |
| `action1_get_endpoint` | Full record of one endpoint | **endpoint_id**, organization_id |
| `action1_list_policies` | Scheduled automations of one organization | organization_id, limit, offset, filter |
| `action1_list_missing_updates` | Missing updates, per organization or endpoint | organization_id, limit, offset, endpoint_id, security_severity, approval_status, filter |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "unauthorized", "message": "Action1 rejected the API key / secret (token request failed)", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`.

## Run locally

```bash
uv sync
uv run python -m action1_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t action1-mcp:dev .
docker run --rm -p 8080:8080 action1-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Action1-API-Key: api-key-xxxx@action1.com" \
  -H "X-Action1-Secret: YOUR_SECRET" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# endpoints with critical updates missing, across all organizations
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Action1-API-Key: api-key-xxxx@action1.com" \
  -H "X-Action1-Secret: YOUR_SECRET" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"action1_list_endpoints","arguments":{"organization_id":"all","update_status":"ERROR","limit":10}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **Policies = automations.** Action1 now calls policies "automations";
  `action1_list_policies` lists the scheduled automations of an organization.
- **Region values.** Both the canonical data-centre names and short codes (`us`, `eu`, `uk`,
  `au`, `NA-2`) are accepted. `UnitedKingdom` is supported.
- **List trimming.** `action1_list_endpoints` returns a summary per endpoint; use
  `action1_get_endpoint` for the full record.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
