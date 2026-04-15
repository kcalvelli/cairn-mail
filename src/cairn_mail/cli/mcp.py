"""CLI commands for MCP server."""

import typer
from rich.console import Console

console = Console()

mcp_app = typer.Typer(
    name="mcp",
    help="MCP (Model Context Protocol) server for AI assistants",
    add_completion=False,
)


@mcp_app.callback(invoke_without_command=True)
def mcp_main(
    ctx: typer.Context,
    api_url: str = typer.Option(
        "http://localhost:8080",
        "--api-url",
        "-u",
        help="Base URL of the cairn-mail API",
    ),
) -> None:
    """Start the MCP server.

    The MCP server exposes email operations as tools for AI assistants.
    It communicates via stdio and calls the cairn-mail REST API.

    Make sure the web service is running before starting the MCP server:
        systemctl status cairn-mail-web.service

    Example AI assistant configuration (Claude Desktop):
        {
          "mcpServers": {
            "cairn-mail": {
              "command": "cairn-mail",
              "args": ["mcp"]
            }
          }
        }
    """
    # Only run if no subcommand was invoked
    if ctx.invoked_subcommand is None:
        from ..mcp import run_server

        # Suppress logging to stderr since MCP uses stdio
        import logging

        logging.getLogger().handlers = []

        run_server(api_url=api_url)


@mcp_app.command("info")
def mcp_info() -> None:
    """Show information about available MCP tools."""
    from rich.table import Table

    table = Table(title="cairn-mail MCP Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Description", style="white")

    tools = [
        ("list_accounts", "List all configured email accounts"),
        ("search_emails", "Search for emails with filters (account, folder, unread, tags, text)"),
        ("read_email", "Get the full content of an email by ID"),
        ("compose_email", "Create a draft email (does not send)"),
        ("send_email", "Send a draft or compose and send in one step"),
        ("reply_to_email", "Create a reply draft for an email thread"),
        ("mark_read", "Mark messages as read or unread"),
        ("delete_email", "Delete emails (move to trash or permanently)"),
    ]

    for name, desc in tools:
        table.add_row(name, desc)

    console.print(table)
    console.print()
    console.print("[dim]Run 'cairn-mail mcp' to start the MCP server.[/dim]")
