"""Main CLI entry point."""

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

from .. import __version__

# Create Typer app
app = typer.Typer(
    name="cairn-mail",
    help="AI-enhanced email workflow with two-way sync",
    add_completion=False,
)

console = Console()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"cairn-mail version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging"),
) -> None:
    """cairn-mail: AI-enhanced email with two-way sync."""
    # Configure logging
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
    )


# Import subcommands
from .accounts import accounts_app
from .auth import auth_app
from .mcp import mcp_app
from .sync import sync_app
from .status import status_app
from .web import web_app

app.add_typer(accounts_app, name="accounts")
app.add_typer(auth_app, name="auth")
app.add_typer(mcp_app, name="mcp")
app.add_typer(sync_app, name="sync")
app.add_typer(status_app, name="status")
app.add_typer(web_app, name="web")


if __name__ == "__main__":
    app()
