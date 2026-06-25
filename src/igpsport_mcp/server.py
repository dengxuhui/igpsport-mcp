"""MCP server construction and tool registry."""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .config import Config, load_config
from .tools import register_all
from .tools._service import IGPSportService

logger = logging.getLogger(__name__)


def build_server(config: Config | None = None) -> FastMCP:
    """Build the FastMCP instance with all 16 tools registered.

    Network/DB dependencies are created lazily by the service, so the server
    constructs (and completes the stdio handshake) without credentials.
    """
    config = config or load_config()
    logging.basicConfig(level=config.log_level)
    server = FastMCP("igpsport-mcp")
    register_all(server, IGPSportService(config))
    logger.debug("Built igpsport-mcp server (cache_dir=%s)", config.cache_dir)
    return server
