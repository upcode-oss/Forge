import hashlib
import json
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import database
from app.main import app
from app.models import MCPKey

KEYS = "/api/v1/auth/mcp-keys"
MCP = "/api/v1/mcp/"


@pytest.fixture
def mcp_client(admin):
    yield admin, "safe-admin-password", lambda: database.engine


def create_key(client, password, scopes=None, **extra):
    response = client.post(
        KEYS,
        json={
            "name": "Test MCP client",
            "scopes": scopes or ["profile.read"],
            "password": password,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def rpc(client, key, method, params=None, *, headers=None, path=MCP):
    return client.post(
        path,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {},
        },
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
            **(headers or {}),
        },
    )


def call(client, key, name, arguments=None):
    response = rpc(client, key, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    value = response.json()
    assert "result" in value, value
    return value["result"]["structuredContent"]


def test_key_is_hashed_and_only_shown_once(mcp_client):
    client, password, engine = mcp_client
    created = create_key(client, password)
    raw = created["key"]
    assert raw.startswith("forge_mcp_")
    assert client.get(KEYS).headers["cache-control"] == "no-store"
    listed = client.get(KEYS).json()
    assert len(listed["keys"]) == 1
    assert raw not in json.dumps(listed)
    assert "digest" not in listed["keys"][0]
    with Session(engine()) as db:
        stored = db.scalar(select(MCPKey))
        assert stored.digest == hashlib.sha256(raw.encode()).hexdigest()
        assert stored.scopes == '["profile.read"]'


def test_official_protocol_and_sessionless_owner_identity(mcp_client):
    client, password, _ = mcp_client
    raw = create_key(client, password)["key"]
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401
    response = rpc(
        client,
        raw,
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1.0"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["serverInfo"]["name"] == "Upcode Forge"
    tools = rpc(client, raw, "tools/list").json()
    assert [tool["name"] for tool in tools["result"]["tools"]] == ["get_current_user"]
    result = call(client, raw, "get_current_user")
    assert result["status"] == 200, result
    assert result["data"]["username"] == "admin"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_or_query_string_cannot_authenticate_mcp(mcp_client):
    client, password, _ = mcp_client
    raw = create_key(client, password)["key"]
    response = client.post(MCP, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
    assert "Bearer" in response.headers["www-authenticate"]
    assert rpc(client, "wrong", "tools/list").status_code == 401
    assert rpc(client, raw, "tools/list", path=MCP + "?access_token=" + raw).status_code == 400
    assert (
        rpc(client, raw, "tools/list", headers={"Origin": "https://untrusted.example"}).status_code
        == 403
    )
    assert rpc(client, raw, "tools/list", headers={"Host": "untrusted.example"}).status_code == 403


def test_revocation_and_expiry_are_checked_on_every_request(mcp_client):
    client, password, engine = mcp_client
    created = create_key(client, password)
    raw, key_id = created["key"], created["record"]["id"]
    assert rpc(client, raw, "tools/list").status_code == 200
    assert client.delete(KEYS + "/" + key_id).status_code == 200
    assert rpc(client, raw, "tools/list").status_code == 401
    created = create_key(client, password)
    with Session(engine()) as db:
        db.get(MCPKey, created["record"]["id"]).expires_at = datetime.now(UTC) - timedelta(
            seconds=1
        )
        db.commit()
    assert rpc(client, created["key"], "tools/list").status_code == 401


def test_key_scopes_cannot_be_expanded_by_arguments(mcp_client):
    client, password, _ = mcp_client
    raw = create_key(client, password)["key"]
    result = call(client, raw, "create_repository", {"payload": {"name": "denied"}})
    assert result["status"] == 403, result
    response = client.post(
        KEYS,
        json={
            "name": "Forged owner",
            "password": password,
            "scopes": ["profile.read"],
            "user_id": "other",
        },
    )
    assert response.status_code == 422
    assert call(client, raw, "create_mcp_key")["status"] == 404
    assert call(client, raw, "api_request", {"path": "/users", "method": "POST"})["status"] == 404


def test_password_change_invalidates_existing_mcp_keys(mcp_client):
    client, password, _ = mcp_client
    raw = create_key(client, password)["key"]
    response = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": password,
            "new_password": "ChangedPassword123",
        },
    )
    assert response.status_code == 200, response.text
    assert rpc(client, raw, "tools/list").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "ChangedPassword123",
            },
        ).status_code
        == 200
    )
    assert client.get(KEYS).json()["keys"][0]["status"] == "credentials_changed"


def test_creation_requires_password_and_enrolled_second_factor(mcp_client):
    client, password, _ = mcp_client
    original = create_key(client, password)["key"]
    setup = client.post("/api/v1/auth/2fa/setup", json={"password": password}).json()
    enabled = client.post(
        "/api/v1/auth/2fa/enable",
        json={
            "password": password,
            "code": pyotp.TOTP(setup["secret"]).now(),
        },
    )
    assert enabled.status_code == 200, enabled.text
    assert rpc(client, original, "tools/list").status_code == 401
    codes = enabled.json()["recovery_codes"]
    assert client.get(KEYS).json()["requires_two_factor"] is True
    payload = {"name": "Proof test", "password": password, "scopes": ["profile.read"]}
    assert client.post(KEYS, json=payload).status_code == 401
    assert (
        client.post(
            KEYS,
            json={
                **payload,
                "password": "wrong",
                "two_factor_code": codes[0],
            },
        ).status_code
        == 401
    )
    raw = create_key(client, password, two_factor_code=codes[0])["key"]
    assert rpc(client, raw, "tools/list").status_code == 200
    assert (
        client.post(
            KEYS,
            json={
                **payload,
                "two_factor_code": codes[0],
            },
        ).status_code
        == 401
    )

    assert (
        client.post(
            "/api/v1/auth/2fa/disable",
            json={
                "password": password,
                "code": codes[1],
            },
        ).status_code
        == 200
    )
    assert rpc(client, raw, "tools/list").status_code == 401


def test_unknown_scopes_and_invalid_expiration_are_rejected(mcp_client):
    client, password, _ = mcp_client
    payload = {"name": "Rejected", "password": password, "scopes": ["*"]}
    assert client.post(KEYS, json=payload).status_code == 422
    assert client.post(KEYS, json={**payload, "scopes": []}).status_code == 422
    for days in (0, -1, 366):
        assert (
            client.post(
                KEYS,
                json={
                    **payload,
                    "scopes": ["profile.read"],
                    "expires_in_days": days,
                },
            ).status_code
            == 422
        )
    assert client.get(KEYS).json()["keys"] == []


def test_every_tool_has_a_closed_valid_input_schema():
    from app.mcp_tools import TOOLS

    for tool in TOOLS:
        schema = tool.definition().input_schema
        assert schema["additionalProperties"] is False
        assert "user_id" not in schema.get("properties", {})


def checked(response, status=201):
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def repositories(mcp_client):
    admin, password, engine = mcp_client
    alice = checked(
        admin.post(
            "/api/v1/users",
            json={
                "username": "alice",
                "email": "alice@example.com",
                "display_name": "Alice",
                "password": "AlicePassword123",
            },
        )
    )
    own = checked(
        admin.post(
            "/api/v1/repositories", json={"name": "shared-with-alice", "visibility": "private"}
        )
    )
    readonly = checked(
        admin.post(
            "/api/v1/repositories", json={"name": "readonly-for-alice", "visibility": "private"}
        )
    )
    foreign = checked(
        admin.post(
            "/api/v1/repositories",
            json={"name": "foreign-secret-repository", "visibility": "private"},
        )
    )
    for repo, role in ((own, "write"), (readonly, "read")):
        checked(
            admin.put(
                f"/api/v1/repositories/{repo['id']}/members",
                json={"username": "alice", "role": role},
            ),
            200,
        )
    ticket = checked(
        admin.post(
            f"/api/v1/repositories/{foreign['id']}/tickets", json={"title": "Foreign secret issue"}
        )
    )
    organization = checked(
        admin.post(
            "/api/v1/organizations",
            json={
                "name": "Private organization",
                "slug": "private-org",
                "visibility": "private",
            },
        )
    )
    org_repo = checked(
        admin.post(
            "/api/v1/repositories",
            json={
                "organization": organization["slug"],
                "name": "private-org-code",
                "visibility": "private",
            },
        )
    )
    checked(
        admin.put(
            f"/api/v1/repositories/{org_repo['id']}/members",
            json={
                "username": "alice",
                "role": "maintain",
            },
        ),
        200,
    )
    other = TestClient(app, headers={"X-Forge-Request": "1"})
    checked(
        other.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "AlicePassword123"}
        ),
        200,
    )
    key = create_key(
        other, "AlicePassword123", ["profile.read", "repositories.read", "repositories.write"]
    )
    try:
        yield {
            "admin": admin,
            "alice": other,
            "alice_id": alice["id"],
            "engine": engine,
            "own": own["id"],
            "readonly": readonly["id"],
            "foreign": foreign["id"],
            "org_repo": org_repo["id"],
            "key": key["key"],
            "ticket": ticket["id"],
        }
    finally:
        other.close()


def test_repository_lists_and_identity_follow_key_owner_even_with_admin_cookie(repositories):
    ctx = repositories
    result = call(ctx["admin"], ctx["key"], "list_repositories")
    assert result["status"] == 200, result
    assert {item["id"] for item in result["data"]} == {ctx["own"], ctx["readonly"]}
    assert call(ctx["admin"], ctx["key"], "get_current_user")["data"]["username"] == "alice"


def test_foreign_code_and_issues_cannot_be_read_or_changed(repositories):
    ctx = repositories
    for repo_id in (ctx["foreign"], ctx["org_repo"]):
        for name, arguments in [
            ("get_repository", {}),
            ("list_branches", {}),
            ("list_tree", {"ref": "main"}),
            ("read_file", {"ref": "main", "path": "README.md"}),
            ("list_commits", {"ref": "main"}),
            ("get_commit_diff", {"sha": "a" * 40}),
            ("list_tickets", {}),
            ("get_ticket", {"ticket_id": ctx["ticket"]}),
            ("get_pull_request_diff", {"ticket_id": ctx["ticket"]}),
            ("create_ticket", {"payload": {"title": "Intrusion"}}),
            ("comment_on_ticket", {"ticket_id": ctx["ticket"], "payload": {"body": "Intrusion"}}),
            ("set_ticket_state", {"ticket_id": ctx["ticket"], "state": "closed"}),
            ("list_collaborators", {}),
        ]:
            result = call(ctx["admin"], ctx["key"], name, {"repo_id": repo_id, **arguments})
            assert result["status"] == 404, (name, result)
            assert "secret" not in json.dumps(result).lower(), (name, result)
    assert (
        ctx["admin"]
        .get(f"/api/v1/repositories/{ctx['foreign']}/tickets/{ctx['ticket']}")
        .json()["state"]
        == "open"
    )


def test_ticket_ids_cannot_escape_the_accessible_repository(repositories):
    ctx = repositories
    for name, arguments in [
        ("get_ticket", {}),
        ("get_pull_request_diff", {}),
        ("comment_on_ticket", {"payload": {"body": "Intrusion"}}),
        ("set_ticket_state", {"state": "closed"}),
    ]:
        result = call(
            ctx["admin"],
            ctx["key"],
            name,
            {
                "repo_id": ctx["own"],
                "ticket_id": ctx["ticket"],
                **arguments,
            },
        )
        assert result["status"] == 404, (name, result)


def test_write_scope_does_not_upgrade_readonly_repository_membership(repositories):
    ctx = repositories
    result = call(
        ctx["admin"],
        ctx["key"],
        "read_file",
        {
            "repo_id": ctx["readonly"],
            "ref": "main",
            "path": "README.md",
        },
    )
    assert result["status"] == 200, result
    result = call(
        ctx["admin"],
        ctx["key"],
        "create_ticket",
        {
            "repo_id": ctx["readonly"],
            "payload": {"title": "Intrusion"},
        },
    )
    assert result["status"] == 403, result
    allowed = call(
        ctx["admin"],
        ctx["key"],
        "create_ticket",
        {
            "repo_id": ctx["own"],
            "payload": {"title": "Created via MCP", "body": "Allowed"},
        },
    )
    assert allowed["status"] == 201, allowed
    assert allowed["data"]["author"] == "alice"


def test_key_cannot_include_maintain_from_inaccessible_private_organization(repositories):
    ctx = repositories
    available = {permission["scope"] for permission in ctx["alice"].get(KEYS).json()["permissions"]}
    assert "repositories.maintain" not in available
    response = ctx["alice"].post(
        KEYS,
        json={
            "name": "Overgrant",
            "password": "AlicePassword123",
            "scopes": ["repositories.maintain"],
        },
    )
    assert response.status_code == 403
    assert (
        ctx["alice"]
        .post(
            KEYS,
            json={
                "name": "Admin",
                "password": "AlicePassword123",
                "scopes": ["admin"],
            },
        )
        .status_code
        == 422
    )


def test_membership_downgrades_and_revocation_apply_to_existing_keys(repositories):
    ctx = repositories
    checked(
        ctx["admin"].put(
            f"/api/v1/repositories/{ctx['own']}/members",
            json={
                "username": "alice",
                "role": "read",
            },
        ),
        200,
    )
    result = call(
        ctx["admin"],
        ctx["key"],
        "create_ticket",
        {
            "repo_id": ctx["own"],
            "payload": {"title": "Denied"},
        },
    )
    assert result["status"] == 403, result
    tools = rpc(ctx["admin"], ctx["key"], "tools/list").json()["result"]["tools"]
    assert "create_ticket" not in [tool["name"] for tool in tools]
    member = next(
        member
        for member in ctx["admin"].get(f"/api/v1/repositories/{ctx['own']}/members").json()
        if member["username"] == "alice"
    )
    checked(ctx["admin"].delete(f"/api/v1/repositories/{ctx['own']}/members/{member['id']}"), 200)
    assert (
        call(ctx["admin"], ctx["key"], "get_repository", {"repo_id": ctx["own"]})["status"] == 404
    )


def test_keys_are_private_to_their_owner_and_cannot_gain_unselected_write_scope(repositories):
    ctx = repositories
    readonly = create_key(ctx["alice"], "AlicePassword123", ["repositories.read"])["key"]
    result = call(
        ctx["admin"],
        readonly,
        "create_ticket",
        {
            "repo_id": ctx["own"],
            "payload": {"title": "Denied"},
        },
    )
    assert result["status"] == 403
    admin_key = create_key(ctx["admin"], "safe-admin-password")
    assert ctx["alice"].delete(KEYS + "/" + admin_key["record"]["id"]).status_code == 404
    assert admin_key["record"]["id"] not in {
        key["id"] for key in ctx["alice"].get(KEYS).json()["keys"]
    }


def test_inactive_owner_and_browser_csrf_protection(repositories):
    ctx = repositories
    # MCP bearer requests do not need the browser-only request header.
    assert (
        rpc(ctx["admin"], ctx["key"], "tools/list", headers={"X-Forge-Request": ""}).status_code
        == 200
    )
    assert (
        ctx["admin"]
        .post(
            KEYS,
            headers={"X-Forge-Request": ""},
            json={
                "name": "CSRF",
                "password": "safe-admin-password",
                "scopes": ["profile.read"],
            },
        )
        .status_code
        == 403
    )
    checked(
        ctx["admin"].put(f"/api/v1/users/{ctx['alice_id']}/active", params={"active": False}), 200
    )
    assert rpc(ctx["admin"], ctx["key"], "tools/list").status_code == 401


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_official_sdk_client_over_http_with_bearer_key(mcp_client, mode):
    import asyncio

    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    client, password, _ = mcp_client
    raw = create_key(client, password)["key"]

    def transport(request):
        response = client.request(
            request.method,
            str(request.url),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx2.Response(
            response.status_code, headers=response.headers, content=response.content
        )

    async def exercise():
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(transport),
            headers={"Authorization": "Bearer " + raw},
        ) as http:
            async with Client(
                streamable_http_client("http://testserver" + MCP, http_client=http),
                mode=mode,
                cache=None,
            ) as sdk:
                tools = await sdk.list_tools()
                assert [tool.name for tool in tools.tools] == ["get_current_user"]
                result = await sdk.call_tool("get_current_user", {})
                assert not result.is_error
                assert result.structured_content["data"]["username"] == "admin"

    asyncio.run(exercise())


def test_mcp_migration_preserves_existing_users(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from app.database import migrate

    url = f"sqlite:///{tmp_path / 'legacy-mcp.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash VARCHAR(255) NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO users (id, password_hash) VALUES ('1', 'existing-hash')")
        )
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        connection.execute(text("INSERT INTO alembic_version VALUES ('0010')"))
    migrate(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT password_hash FROM users")) == "existing-hash"
        assert connection.scalar(text("SELECT COUNT(*) FROM mcp_keys")) == 0
        foreign_keys = inspect(connection).get_foreign_keys("mcp_keys")
        assert foreign_keys[0]["referred_table"] == "users"
        assert foreign_keys[0]["constrained_columns"] == ["user_id"]
    engine.dispose()
