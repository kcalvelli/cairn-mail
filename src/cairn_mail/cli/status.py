"""Status command for viewing sync state and statistics."""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..db.database import Database

console = Console()
status_app = typer.Typer(help="View sync status and statistics")


@status_app.callback(invoke_without_command=True)
def show_status(
    ctx: typer.Context,
    db_path: Path = typer.Option(
        Path.home() / ".local/share/cairn-mail/mail.db",
        "--db",
        help="Database path",
    ),
) -> None:
    """Show sync status for all configured accounts."""
    # Only run if no subcommand was invoked
    if ctx.invoked_subcommand is not None:
        return

    console.print("[bold blue]cairn-mail Status[/bold blue]\n")

    # Initialize database
    if not db_path.exists():
        console.print("[yellow]No database found - run 'cairn-mail sync run' first[/yellow]")
        raise typer.Exit(0)

    db = Database(db_path)

    # Get all accounts
    accounts = db.list_accounts()

    if not accounts:
        console.print("[yellow]No accounts configured[/yellow]")
        raise typer.Exit(0)

    # Accounts table
    table = Table(title="Configured Accounts")
    table.add_column("Account ID", style="cyan")
    table.add_column("Email", style="green")
    table.add_column("Provider")
    table.add_column("Last Sync", style="yellow")
    table.add_column("Messages")
    table.add_column("Unread")

    for account in accounts:
        # Get message counts
        all_messages = db.query_messages(account_id=account.id, limit=10000)
        unread_messages = db.query_messages(account_id=account.id, is_unread=True, limit=10000)

        last_sync_str = (
            account.last_sync.strftime("%Y-%m-%d %H:%M:%S")
            if account.last_sync
            else "[dim]Never[/dim]"
        )

        table.add_row(
            account.id,
            account.email,
            account.provider,
            last_sync_str,
            str(len(all_messages)),
            str(len(unread_messages)),
        )

    console.print(table)

    # Overall statistics
    console.print("\n[bold]Overall Statistics[/bold]")

    total_messages = db.query_messages(limit=100000)
    total_classified = sum(1 for msg in total_messages if db.has_classification(msg.id))

    stats_table = Table(show_header=False)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green")

    stats_table.add_row("Total Messages", str(len(total_messages)))
    stats_table.add_row("Classified Messages", str(total_classified))
    stats_table.add_row("Classification Rate", f"{(total_classified/len(total_messages)*100) if total_messages else 0:.1f}%")

    console.print(stats_table)

    # Tag distribution
    if total_classified > 0:
        console.print("\n[bold]Tag Distribution[/bold]")

        tag_counts = {}
        for msg in total_messages:
            classification = db.get_classification(msg.id)
            if classification:
                for tag in classification.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        tag_table = Table()
        tag_table.add_column("Tag", style="cyan")
        tag_table.add_column("Count", style="green")
        tag_table.add_column("Percentage", style="yellow")

        for tag, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_classified) * 100
            tag_table.add_row(tag, str(count), f"{percentage:.1f}%")

        console.print(tag_table)

    # Database info
    console.print("\n[bold]Database Information[/bold]")
    db_size = db_path.stat().st_size / 1024 / 1024  # MB
    console.print(f"Location: {db_path}")
    console.print(f"Size: {db_size:.2f} MB")
