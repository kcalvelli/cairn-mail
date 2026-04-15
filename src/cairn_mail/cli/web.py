"""Web UI server command."""

import logging
from pathlib import Path

import typer
from rich.console import Console

console = Console()
web_app = typer.Typer(help="Start web UI server")

logger = logging.getLogger(__name__)


@web_app.command("start")
def start_web_server(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host to bind to (default: localhost only)",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="Port to listen on",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload (development mode)",
    ),
) -> None:
    """Start the web UI server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error: uvicorn not installed[/red]")
        console.print("Install with: pip install 'cairn-mail[api]'")
        raise typer.Exit(1)

    console.print("[bold blue]Starting cairn-mail web UI[/bold blue]")
    console.print(f"Server: http://{host}:{port}")
    console.print("Press Ctrl+C to stop\n")

    # Start uvicorn server
    # Use "warning" for uvicorn to suppress noisy access logs
    # Our application logs are configured separately in api/main.py
    uvicorn.run(
        "cairn_mail.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
        access_log=False,  # Disable access logging entirely
    )


@web_app.callback(invoke_without_command=True)
def web_callback(
    ctx: typer.Context,
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        "-h",
        help="Host to bind to (default: localhost only)",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="Port to listen on",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload (development mode)",
    ),
) -> None:
    """Start web UI server (default command)."""
    # If no subcommand, run start
    if ctx.invoked_subcommand is None:
        start_web_server(host, port, reload)
