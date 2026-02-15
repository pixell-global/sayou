"""Streamable-HTTP transport for sayou MCP server + REST API."""

from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.routing import Mount

from sayou.api.routes import create_router
from sayou.server import create_server


def create_http_app(*, host: str = "127.0.0.1", port: int = 8080) -> Starlette:
    """Create a Starlette ASGI app with both MCP and REST endpoints.

    - ``/mcp`` — Streamable-HTTP MCP transport
    - ``/api/v1/...`` — REST API
    """
    server, ws = create_server()

    # Configure FastMCP transport settings
    server.settings.host = host
    server.settings.port = port
    server.settings.stateless_http = True

    # Build MCP ASGI app
    mcp_app = server.streamable_http_app()

    # Build REST API
    rest_app = FastAPI(title="sayou", version="0.1.0")
    rest_router = create_router(ws)
    rest_app.include_router(rest_router)

    # Combine into a single Starlette app
    app = Starlette(
        routes=[
            Mount("/api", app=rest_app),
            Mount("/", app=mcp_app),
        ]
    )

    return app
