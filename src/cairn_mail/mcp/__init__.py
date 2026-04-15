"""MCP (Model Context Protocol) server for cairn-mail.

This module provides an MCP server that exposes email operations as tools
for AI assistants to automate email workflows.
"""

from .server import create_server, run_server

__all__ = ["create_server", "run_server"]
