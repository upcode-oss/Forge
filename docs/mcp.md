# Personal MCP access

Forge exposes a Streamable HTTP MCP server at
`https://forge.example.com/api/v1/mcp`. Use the same public origin as
the application.

## Create a key

MCP is **disabled by default**, including when upgrading an existing installation.
An administrator must enable it under **Instance & System → MCP access** first.
Migration `0012` stores the opt-in flag on the instance, defaulting to false.

While disabled, the profile hides MCP key management, new keys cannot be created,
and every MCP request returns HTTP 404, even with an existing valid key. Disabling
the feature takes effect on subsequent requests immediately. Existing keys remain
stored; they can be revoked while disabled and work again after re-enabling only
if still unrevoked, unexpired, and authorized.

Open **Profile & Access Tokens → MCP access keys → Generate MCP key**.

1. Give the key a name and choose an expiration (30 days, 90 days, or one year in
   the interface; the API accepts 1–365 days).
2. Select the permissions needed by your MCP client. Only permissions your account
   currently has are offered. Read permissions are selected initially; write,
   create, maintain, and delete permissions require explicit selection.
3. Confirm your current password. If you use 2FA, also enter a new authenticator
   code or unused recovery code.
4. Save the personal key when it is displayed. It cannot be displayed again.
5. Configure a client that supports Streamable HTTP with a custom
   `Authorization: Bearer <YOUR_PERSONAL_MCP_KEY>` header.

Keys are personal: you can list and revoke only your own keys. Revocation and
expiration apply to every subsequent request, including requests from clients
that already connected. Password changes, password resets where supported, and
2FA configuration changes invalidate previously generated MCP keys. Generate a new
key after these account-security changes.

This is explicit personal-key authentication. It does not expose OAuth login,
dynamic client registration, anonymous tools, or a separate administrator service
account. Clients must support supplying a bearer header.

## Permission boundaries

Every tool call must satisfy all of these checks:

- The key exists, is unexpired and unrevoked, and its owner is still active with
  unchanged account credentials and 2FA enrollment, with MCP enabled on the instance.
- The operation's permission was selected when this key was created.
- The owner still has that permission now. Forged or excessive scopes are rejected
  by the key-creation API, independently of the interface.
- The application API allows the owner to access the specific project or
  repository and any nested task, document, sprint, file, issue, or pull request.

Project and repository IDs are identifiers, never permission grants. Changing an
ID in a tool call cannot change the acting user or bypass membership checks.
Existing keys do not gain additional operation scopes when a user gains a new
role. Access to individual objects follows the owner's current roles and
memberships, so losing a project/team/repository grant removes access immediately
for subsequent requests.

The MCP dispatcher uses a fixed operation allowlist and dispatches through the
existing application API and its access checks. It does not forward browser
cookies or create browser/JWT sessions, and it does not expose an arbitrary URL,
HTTP method, SQL query, key-management, authentication, or user-administration tool.
An MCP key is not accepted as a browser session or general REST API bearer token.

Forge retains its Read, Write, and Maintain repository roles and private
organization boundaries. A key with Write scope cannot write to a repository
where its owner only has Read access. Even an instance administrator or explicit
repository collaborator cannot bypass private organization membership. Repository
deletion additionally requires full `owner/repository` name confirmation.

## Available tools

| Scope | Tools |
| --- | --- |
| `profile.read` | Read the key owner's account |
| `repositories.read` | List/read accessible repositories, branches, files, commits/diffs, issues/PRs, comments and collaborator grants |
| `repositories.write` | Create issues/PRs, comment and close/reopen tickets where the owner has Write access |
| `repositories.create` | Create a repository using existing personal/organization creation rights |
| `repositories.maintain` | Update/delete repositories, manage collaborators, and merge PRs where the owner has Maintain access |

Only tools allowed by both the key's scope ceiling and the owner's current
permissions appear in `tools/list`. A cached tool definition does not grant
access: `tools/call` checks permissions again.

Tool arguments contain typed IDs, filters, and (for writes) a `payload` matching
the existing API request schema. PATCH requests preserve omitted fields.
Results contain the API `status` and `data`; denied or failed operations set
`isError`.

## Connection example

A client supplies these HTTP headers to the endpoint above:

```http
Authorization: Bearer <YOUR_PERSONAL_MCP_KEY>
Accept: application/json, text/event-stream
Content-Type: application/json
```

The official Python SDK negotiates current and legacy MCP protocol versions:

```python
import asyncio
import os

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(headers={
        "Authorization": "Bearer " + os.environ["FORGE_MCP_KEY"],
    }) as http:
        async with Client(streamable_http_client(
            "https://forge.example.com/api/v1/mcp", http_client=http,
        ), cache=None) as client:
            tools = await client.list_tools()
            print([tool.name for tool in tools.tools])

asyncio.run(main())
```

Keep keys in client secret storage or environment variables, never in URLs,
shared configuration, screenshots, or Git. Use HTTPS for remote access. Requests
with a supplied foreign Origin or untrusted Host are rejected. Direct browser
clients must use the application's configured origin.

## Storage, upgrades, and verification

Migration `0011` creates `mcp_keys` through the existing setup/startup migration
workflow. Rebuild and restart both backend and frontend to install the MCP SDK and
show key management. Existing users and data are preserved.

Only SHA-256 digests of random 256-bit keys are stored, together with the scope
ceiling, expiration, owner, revocation and last-use timestamps, and a fingerprint
of the account credentials and 2FA enrollment. Neither the raw key nor account
password is stored in the key table. Personal-key responses use
`Cache-Control: no-store`.

The server uses the official MCP Python SDK with stateless HTTP and a 1 MiB
request-body limit. The existing frontend API proxy forwards MCP headers and JSON
responses; no extra public backend port or shared instance credential is required.

`tests/test_mcp.py` covers official SDK clients in modern and legacy modes,
disabled-by-default behavior, restricted settings activation and immediate shutdown,
per-user scope issuance, one-time key display and hashing, expiry/revocation,
password and 2FA changes, owner deactivation, private object access, nested-ID
substitution, membership/role removal, narrowed keys, and migration compatibility.

See the [MCP Streamable HTTP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http)
and [official Python SDK](https://py.sdk.modelcontextprotocol.io/run/asgi/).
