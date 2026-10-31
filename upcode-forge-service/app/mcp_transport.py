"""Streamable HTTP MCP using the SDK and the application's existing access checks."""

import json
import logging
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, ListToolsResult, TextContent
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import mcp_keys, mcp_tools
from app.config import settings
from app.database import get_db
from app.models import Instance

logger = logging.getLogger(__name__)


def public_origin(db):
    instance = db.get(Instance, 1)
    if instance is None:
        mcp_keys.fail(503, "Complete the installation setup first.")
    return instance.public_url


def error_details(error):
    return error.status_code, str(error.detail)


class DelegatedAPI:
    """Set trusted identity metadata without creating or forwarding a user session."""

    def __init__(self, app, raw_key):
        self.app = app
        self.raw_key = raw_key

    async def __call__(self, scope, receive, send):
        await self.app({**scope, "upcode_mcp_key": self.raw_key}, receive, send)


class MCPApplication:
    def __init__(self, app):
        self.app = app
        self.inner = None

    @asynccontextmanager
    async def run(self):
        # Recreate the manager for each application lifespan, including test/restart cycles.
        server = Server(
            "Upcode Forge",
            version="0.1.0",
            instructions="Use only tools allowed by the personal key. Project/repository access is checked on every call.",
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
            get_tool_input_schema=lambda name: (
                mcp_tools.BY_NAME[name].input_model.model_json_schema()
                if name in mcp_tools.BY_NAME
                else None
            ),
        )
        self.inner = server.streamable_http_app(
            streamable_http_path="/api/v1/mcp",
            json_response=True,
            stateless_http=True,
            max_request_body_size=1024 * 1024,
            # Dynamic instance origins and proxy hosts are checked in __call__ below.
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        try:
            async with server.session_manager.run():
                yield
        finally:
            self.inner = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        if self.inner is None:
            return await JSONResponse({"error": "MCP is not ready."}, status_code=503)(
                scope, receive, send
            )
        request = Request(scope)
        try:
            if any(
                name in request.query_params for name in ("key", "token", "api_key", "access_token")
            ):
                mcp_keys.fail(400, "Send the MCP key only in the Authorization header.")
            with contextmanager(get_db)() as db:
                mcp_keys.require_enabled(db)
                origin = public_origin(db).rstrip("/")
                bootstrap = settings().bootstrap_origin
                allowed_origins = {origin, bootstrap.rstrip("/")}
                if (
                    request.headers.get("origin") is not None
                    and request.headers["origin"] not in allowed_origins
                ):
                    mcp_keys.fail(403, "Untrusted MCP request origin.")
                allowed_hosts = {"localhost", "127.0.0.1", "::1", "backend"}
                allowed_hosts.update(urlsplit(value).hostname for value in allowed_origins)
                if request.url.hostname not in allowed_hosts:
                    mcp_keys.fail(403, "Untrusted MCP request host.")
                authorization = request.headers.get("authorization", "")
                kind, _, raw = authorization.partition(" ")
                if kind.lower() != "bearer" or not raw.strip():
                    mcp_keys.fail(401, "A personal MCP bearer key is required.")
                raw = raw.strip()
                mcp_keys.authenticate(db, raw, touch=True)
        except HTTPException as error:
            status, message = error_details(error)
            headers = {"Cache-Control": "no-store"}
            if status == 401:
                headers["WWW-Authenticate"] = 'Bearer realm="Upcode Forge MCP"'
            return await JSONResponse({"error": message}, status_code=status, headers=headers)(
                scope, receive, send
            )
        await self.inner({**scope, "upcode_mcp_token": raw}, receive, send)

    def principal(self, ctx, db):
        request = ctx.request
        raw = request.scope.get("upcode_mcp_token") if request else None
        user, record, scopes = mcp_keys.authenticate(db, raw)
        return raw, user, record, scopes

    async def list_tools(self, ctx, params):
        del params
        with contextmanager(get_db)() as db:
            _, _, _, scopes = self.principal(ctx, db)
            return ListToolsResult(
                tools=[tool.definition() for tool in mcp_tools.TOOLS if tool.scope in scopes]
            )

    async def call_tool(self, ctx, params):
        try:
            with contextmanager(get_db)() as db:
                raw, user, _, scopes = self.principal(ctx, db)
                tool = mcp_tools.BY_NAME.get(params.name)
                if tool is None:
                    return self.result(404, {"error": "Unknown MCP tool."})
                if tool.scope not in scopes:
                    return self.result(
                        403,
                        {"error": "This key and its owner do not have the required permission."},
                    )
                arguments = params.arguments or {}
                path, query, payload = tool.request(arguments)
                mcp_tools.validate_arguments(db, user, tool, arguments)
            # Dispatch only the fixed method/path above. No client-controlled URLs,
            # session cookies, alternate identities, or administrator credentials are forwarded.
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=DelegatedAPI(self.app, raw)),
                base_url="http://backend",
                headers={"X-Forge-Request": "1"},
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    tool.method,
                    "/api/v1" + path,
                    params=query,
                    **({"json": payload} if payload is not None else {}),
                )
            body = response.json() if response.content else {"ok": True}
            return self.result(response.status_code, body)
        except ValidationError:
            return self.result(422, {"error": "Invalid tool arguments."})
        except HTTPException as error:
            status, message = error_details(error)
            return self.result(status, {"error": message})
        except Exception:
            logger.exception("MCP operation failed")
            return self.result(500, {"error": "The MCP operation could not be completed."})

    @staticmethod
    def result(status, body):
        value = {"status": status, "data": body}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=False))],
            structured_content=value,
            is_error=status >= 300,
        )
