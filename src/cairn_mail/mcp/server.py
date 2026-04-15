"""MCP server for cairn-mail.

This module provides the main MCP server that exposes email operations
as tools for AI assistants.
"""

import logging

from mcp.server.fastmcp import FastMCP

from .client import CairnMailClient
from .tools import register_tools

logger = logging.getLogger(__name__)

# Default API URL
DEFAULT_API_URL = "http://localhost:8080"


def create_server(api_url: str = DEFAULT_API_URL) -> FastMCP:
    """Create and configure the MCP server.

    Args:
        api_url: Base URL of the cairn-mail API

    Returns:
        Configured FastMCP server instance
    """
    # Create the MCP server
    mcp = FastMCP("cairn-mail")

    # Create API client
    client = CairnMailClient(base_url=api_url)

    # Register all tools
    register_tools(mcp, client)

    logger.info(f"MCP server created with API URL: {api_url}")

    return mcp


def run_server(api_url: str = DEFAULT_API_URL) -> None:
    """Run the MCP server.

    This function blocks and runs the server using stdio transport.

    Args:
        api_url: Base URL of the cairn-mail API
    """
    mcp = create_server(api_url)

    logger.info("Starting MCP server on stdio transport...")

    # Run the server (this blocks)
    mcp.run()
