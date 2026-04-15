"""Account maintenance CLI commands."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from ..config.loader import ConfigLoader
from ..db.database import Database

accounts_app = typer.Typer(help="Account maintenance commands")
console = Console()


def get_db() -> Database:
    """Get database instance."""
    db_path = Path.home() / ".local" / "share" / "cairn-mail" / "mail.db"
    return Database(db_path)


@accounts_app.command("list")
def list_accounts() -> None:
    """List all accounts with their status (active, orphaned, or new).

    Active accounts are defined in your Nix config and exist in database.
    Orphaned accounts exist only in the database (no longer in config).
    New accounts are in config but not yet synced to database.
    """
    db = get_db()
    config = ConfigLoader.load_config()

    # Get accounts from config and database
    config_accounts = config.get("accounts", {})
    config_account_ids = set(config_accounts.keys())
    db_accounts = db.list_accounts()
    db_account_ids = {a.id for a in db_accounts}

    if not db_accounts and not config_accounts:
        console.print("[yellow]No accounts found in database or config[/yellow]")
        return

    table = Table(title="Email Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Email", style="white")
    table.add_column("Provider", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Messages", justify="right")
    table.add_column("Last Sync", style="dim")

    # Show database accounts first
    for account in db_accounts:
        status = "[green]Active[/green]" if account.id in config_account_ids else "[yellow]Orphaned[/yellow]"

        # Count messages for this account
        message_count = db.count_messages(account_id=account.id)

        # Format last sync
        last_sync = account.last_sync.strftime("%Y-%m-%d %H:%M") if account.last_sync else "Never"

        table.add_row(
            account.id,
            account.email,
            account.provider,
            status,
            str(message_count),
            last_sync,
        )

    # Show new accounts (in config but not in database)
    new_accounts = []
    for account_id, account_config in config_accounts.items():
        if account_id not in db_account_ids:
            new_accounts.append((account_id, account_config))
            table.add_row(
                account_id,
                account_config.get("email", "unknown"),
                account_config.get("provider", "unknown"),
                "[blue]New[/blue]",
                "-",
                "Never",
            )

    console.print(table)

    # Show warnings and hints
    orphaned = [a for a in db_accounts if a.id not in config_account_ids]

    if new_accounts:
        console.print()
        console.print(f"[blue]ℹ Found {len(new_accounts)} new account(s) in config.[/blue]")
        console.print("  Run [bold]cairn-mail sync run[/bold] to sync them.")

    if orphaned:
        console.print()
        console.print(f"[yellow]⚠ Found {len(orphaned)} orphaned account(s).[/yellow]")
        console.print("  Run [bold]cairn-mail accounts cleanup[/bold] to remove them.")
        if new_accounts:
            console.print("  Or run [bold]cairn-mail accounts migrate <old> <new>[/bold] to preserve messages.")


@accounts_app.command("cleanup")
def cleanup_orphaned(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without actually deleting"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompts"),
) -> None:
    """Remove orphaned accounts and their messages.

    Orphaned accounts are those that exist in the database but are no longer
    defined in your Nix configuration.
    """
    db = get_db()
    config = ConfigLoader.load_config()

    config_accounts = set(config.get("accounts", {}).keys())
    db_accounts = db.list_accounts()

    orphaned = [a for a in db_accounts if a.id not in config_accounts]

    if not orphaned:
        console.print("[green]✓ No orphaned accounts found[/green]")
        return

    console.print(f"Found {len(orphaned)} orphaned account(s):\n")

    total_messages = 0
    for account in orphaned:
        message_count = db.count_messages(account_id=account.id)
        total_messages += message_count
        console.print(f"  • [cyan]{account.id}[/cyan] ({account.email})")
        console.print(f"    Provider: {account.provider}, Messages: {message_count}")

    console.print()
    console.print(f"[bold]Total messages to delete: {total_messages}[/bold]")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        return

    if not force:
        if not Confirm.ask("\nPermanently delete these accounts and their messages?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Delete orphaned accounts and their data
    for account in orphaned:
        _delete_account_data(db, account.id)
        console.print(f"[green]✓ Deleted account: {account.id}[/green]")

    console.print(f"\n[green]✓ Cleanup complete. Removed {len(orphaned)} account(s) and {total_messages} message(s).[/green]")


@accounts_app.command("migrate")
def migrate_account(
    source: str = typer.Argument(..., help="Source account ID"),
    dest: str = typer.Argument(..., help="Destination account ID"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be migrated"),
) -> None:
    """Migrate messages from one account to another.

    This is useful when you rename an account in your Nix config.
    The source account will become orphaned after migration.

    Example:
        cairn-mail accounts migrate personal gmail
    """
    db = get_db()

    # Verify source exists
    source_account = db.get_account(source)
    if not source_account:
        console.print(f"[red]Error: Source account '{source}' not found[/red]")
        raise typer.Exit(1)

    # Verify destination exists
    dest_account = db.get_account(dest)
    if not dest_account:
        console.print(f"[red]Error: Destination account '{dest}' not found[/red]")
        console.print("Make sure to sync the new account first: cairn-mail sync run")
        raise typer.Exit(1)

    # Count messages to migrate
    message_count = db.count_messages(account_id=source)

    console.print(f"Migration: [cyan]{source}[/cyan] → [cyan]{dest}[/cyan]")
    console.print(f"  Source: {source_account.email} ({message_count} messages)")
    console.print(f"  Destination: {dest_account.email}")

    if message_count == 0:
        console.print("\n[yellow]No messages to migrate[/yellow]")
        return

    if dry_run:
        console.print(f"\n[yellow]Dry run - would migrate {message_count} message(s)[/yellow]")
        return

    if not Confirm.ask(f"\nMigrate {message_count} message(s)?"):
        console.print("[yellow]Cancelled[/yellow]")
        return

    # Perform migration
    migrated = _migrate_messages(db, source, dest)
    console.print(f"\n[green]✓ Migrated {migrated} message(s) from {source} to {dest}[/green]")
    console.print(f"\nYou can now clean up the orphaned account with:")
    console.print(f"  [dim]cairn-mail accounts cleanup[/dim]")


@accounts_app.command("delete")
def delete_account(
    account_id: str = typer.Argument(..., help="Account ID to delete"),
    keep_messages: bool = typer.Option(False, "--keep-messages", help="Keep messages (reassign to another account later)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete an account and optionally its messages.

    Use --keep-messages to preserve messages for later migration.
    """
    db = get_db()

    account = db.get_account(account_id)
    if not account:
        console.print(f"[red]Error: Account '{account_id}' not found[/red]")
        raise typer.Exit(1)

    message_count = db.count_messages(account_id=account_id)

    console.print(f"Account: [cyan]{account_id}[/cyan]")
    console.print(f"  Email: {account.email}")
    console.print(f"  Provider: {account.provider}")
    console.print(f"  Messages: {message_count}")

    if keep_messages:
        console.print("\n[yellow]Note: Messages will be orphaned (no account association)[/yellow]")

    if not force:
        action = "delete account (keep messages)" if keep_messages else f"delete account and {message_count} message(s)"
        if not Confirm.ask(f"\nPermanently {action}?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    if keep_messages:
        _delete_account_only(db, account_id)
        console.print(f"\n[green]✓ Deleted account: {account_id}[/green]")
        console.print(f"[yellow]Note: {message_count} message(s) are now orphaned[/yellow]")
    else:
        _delete_account_data(db, account_id)
        console.print(f"\n[green]✓ Deleted account {account_id} and {message_count} message(s)[/green]")


@accounts_app.command("check")
def check_account(
    account_id: str = typer.Argument(..., help="Account ID to check"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed diagnostics"),
) -> None:
    """Test connection and authentication for an account.

    Diagnoses connection issues by testing:
    - Network connectivity to server
    - Authentication with credentials
    - Folder access (INBOX)
    - Message count

    Example:
        cairn-mail accounts check companies
    """
    import imaplib
    import socket
    from ..providers.factory import ProviderFactory
    from ..providers.implementations.imap import IMAPProvider
    from ..providers.implementations.gmail import GmailProvider

    db = get_db()
    config = ConfigLoader.load_config()

    # Check if account exists in config
    config_accounts = config.get("accounts", {})
    if account_id not in config_accounts:
        console.print(f"[red]Account '{account_id}' not found in config[/red]")
        console.print("\nAvailable accounts in config:")
        for aid in config_accounts:
            console.print(f"  • {aid}")
        raise typer.Exit(1)

    account_config = config_accounts[account_id]
    provider_type = account_config.get("provider", "unknown")
    email_addr = account_config.get("email", "unknown")

    console.print(f"\n[bold]Checking account: {account_id}[/bold]")
    console.print(f"  Email: {email_addr}")
    console.print(f"  Provider: {provider_type}")

    # Sync config to database first
    ConfigLoader.sync_to_database(db, config)
    db_account = db.get_account(account_id)

    if not db_account:
        console.print("[red]Account not found in database after config sync[/red]")
        raise typer.Exit(1)

    # Provider-specific checks
    if provider_type == "imap":
        _check_imap_account(db_account, account_config, verbose)
    elif provider_type == "gmail":
        _check_gmail_account(db_account, account_config, verbose)
    else:
        console.print(f"[yellow]Unknown provider type: {provider_type}[/yellow]")
        raise typer.Exit(1)


def _check_imap_account(db_account, account_config: dict, verbose: bool) -> None:
    """Check IMAP account connectivity."""
    import imaplib
    import socket
    from ..credentials import Credentials

    # IMAP settings can be in account_config.imap (old format) or account_config.settings (new format)
    settings = account_config.get("settings", {})
    imap_settings = account_config.get("imap", {})

    # Try settings.imap_* first (Nix-generated), then imap.* (legacy)
    host = settings.get("imap_host") or imap_settings.get("host", "")
    port = settings.get("imap_port") or imap_settings.get("port", 993)
    use_ssl = settings.get("imap_tls") if settings.get("imap_tls") is not None else imap_settings.get("tls", True)
    credential_file = account_config.get("credential_file", "")

    console.print(f"\n[bold]IMAP Connection Test[/bold]")
    console.print(f"  Host: {host}")
    console.print(f"  Port: {port}")
    console.print(f"  TLS: {'Yes' if use_ssl else 'No'}")

    # Step 1: Check credential file
    console.print(f"\n[dim]Step 1: Checking credentials...[/dim]")
    try:
        from pathlib import Path
        cred_path = Path(credential_file)
        if not cred_path.exists():
            console.print(f"[red]✗ Credential file not found: {credential_file}[/red]")
            console.print("\nRun: [bold]cairn-mail auth[/bold] to set up credentials")
            raise typer.Exit(1)

        password = Credentials.load_password(credential_file)
        console.print(f"[green]✓ Credentials loaded from {credential_file}[/green]")
    except PermissionError as e:
        console.print(f"[red]✗ Credential file permission error: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Failed to load credentials: {e}[/red]")
        raise typer.Exit(1)

    # Step 2: Test network connectivity
    console.print(f"\n[dim]Step 2: Testing network connectivity to {host}:{port}...[/dim]")
    try:
        sock = socket.create_connection((host, port), timeout=10)
        sock.close()
        console.print(f"[green]✓ Server reachable at {host}:{port}[/green]")
    except socket.timeout:
        console.print(f"[red]✗ Connection timed out to {host}:{port}[/red]")
        console.print("\nPossible causes:")
        console.print("  • Server is down or unreachable")
        console.print("  • Firewall blocking the connection")
        console.print("  • Wrong host or port")
        raise typer.Exit(1)
    except socket.gaierror as e:
        console.print(f"[red]✗ DNS resolution failed for {host}: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗ Network error: {e}[/red]")
        raise typer.Exit(1)

    # Step 3: Test IMAP connection
    console.print(f"\n[dim]Step 3: Establishing IMAP connection...[/dim]")
    try:
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port)
        else:
            conn = imaplib.IMAP4(host, port)
        console.print(f"[green]✓ IMAP connection established[/green]")
    except Exception as e:
        console.print(f"[red]✗ IMAP connection failed: {e}[/red]")
        raise typer.Exit(1)

    # Step 4: Test authentication
    console.print(f"\n[dim]Step 4: Authenticating as {db_account.email}...[/dim]")
    try:
        conn.login(db_account.email, password)
        console.print(f"[green]✓ Authentication successful[/green]")
    except imaplib.IMAP4.error as e:
        error_msg = str(e)
        console.print(f"[red]✗ Authentication failed: {error_msg}[/red]")
        console.print("\nCommon causes:")
        console.print("  • Wrong password or app password")
        console.print("  • Account requires app-specific password")
        console.print("  • IMAP access disabled in email settings")
        console.print("  • Account locked or suspended")
        raise typer.Exit(1)

    # Step 5: Check capabilities
    console.print(f"\n[dim]Step 5: Checking server capabilities...[/dim]")
    try:
        typ, capabilities = conn.capability()
        if typ == "OK" and capabilities:
            caps = capabilities[0].decode("utf-8", errors="ignore")
            supports_keywords = "KEYWORD" in caps
            supports_idle = "IDLE" in caps

            console.print("[green]✓ Capabilities retrieved[/green]")
            keyword_status = "[green]Yes[/green]" if supports_keywords else "[yellow]No (tags will not sync to server)[/yellow]"
            console.print(f"  KEYWORD extension: {keyword_status}")
            idle_status = "Yes" if supports_idle else "No"
            console.print(f"  IDLE extension: {idle_status}")

            if verbose:
                console.print(f"  [dim]All capabilities: {caps}[/dim]")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not retrieve capabilities: {e}[/yellow]")

    # Step 6: Test folder access
    folder = settings.get("imap_folder") or imap_settings.get("folder", "INBOX")
    console.print(f"\n[dim]Step 6: Selecting folder '{folder}'...[/dim]")
    try:
        typ, data = conn.select(folder)
        if typ == "OK":
            message_count = int(data[0].decode())
            console.print(f"[green]✓ Folder '{folder}' accessible[/green]")
            console.print(f"  Messages in folder: {message_count}")
        else:
            console.print(f"[red]✗ Failed to select folder: {data}[/red]")
            raise typer.Exit(1)
    except imaplib.IMAP4.error as e:
        console.print(f"[red]✗ Folder access failed: {e}[/red]")
        console.print(f"\nThe folder '{folder}' may not exist. Available folders:")
        try:
            typ, folders = conn.list()
            if typ == "OK":
                for f in folders[:10]:  # Show first 10
                    console.print(f"  • {f.decode()}")
        except:
            pass
        raise typer.Exit(1)

    # Step 7: Test message retrieval
    console.print(f"\n[dim]Step 7: Testing message retrieval...[/dim]")
    try:
        # Search for recent messages
        typ, data = conn.search(None, "ALL")
        if typ == "OK":
            msg_ids = data[0].split()
            total = len(msg_ids)
            console.print(f"[green]✓ Can search messages[/green]")
            console.print(f"  Total messages found: {total}")

            # Try to fetch one message header
            if msg_ids:
                latest_id = msg_ids[-1]
                typ, msg_data = conn.fetch(latest_id, "(ENVELOPE)")
                if typ == "OK":
                    console.print(f"[green]✓ Can fetch message headers[/green]")
                else:
                    console.print(f"[yellow]⚠ Could not fetch message header[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠ Message retrieval test failed: {e}[/yellow]")

    # Cleanup
    try:
        conn.logout()
    except:
        pass

    console.print(f"\n[bold green]✓ All checks passed for {db_account.email}[/bold green]")


def _check_gmail_account(db_account, account_config: dict, verbose: bool) -> None:
    """Check Gmail account connectivity."""
    from ..providers.factory import ProviderFactory

    console.print(f"\n[bold]Gmail API Connection Test[/bold]")

    credential_file = account_config.get("credential_file", "")

    # Step 1: Check credential file
    console.print(f"\n[dim]Step 1: Checking OAuth credentials...[/dim]")
    from pathlib import Path
    cred_path = Path(credential_file)
    if not cred_path.exists():
        console.print(f"[red]✗ Credential file not found: {credential_file}[/red]")
        console.print("\nRun: [bold]cairn-mail auth[/bold] to set up OAuth credentials")
        raise typer.Exit(1)
    console.print(f"[green]✓ Credential file exists: {credential_file}[/green]")

    # Step 2: Test authentication
    console.print(f"\n[dim]Step 2: Authenticating with Gmail API...[/dim]")
    try:
        provider = ProviderFactory.create_from_account(db_account)
        provider.authenticate()
        console.print(f"[green]✓ Gmail API authentication successful[/green]")
    except Exception as e:
        console.print(f"[red]✗ Gmail API authentication failed: {e}[/red]")
        console.print("\nPossible causes:")
        console.print("  • OAuth token expired - run 'cairn-mail auth' to refresh")
        console.print("  • Credentials revoked in Google Account settings")
        console.print("  • Network connectivity issues")
        raise typer.Exit(1)

    # Step 3: Test message retrieval
    console.print(f"\n[dim]Step 3: Testing message retrieval...[/dim]")
    try:
        messages = provider.fetch_messages(max_messages=1)
        console.print(f"[green]✓ Can fetch messages from Gmail API[/green]")
        if messages:
            console.print(f"  Latest message from: {messages[0].sender}")
    except Exception as e:
        console.print(f"[yellow]⚠ Message retrieval test failed: {e}[/yellow]")

    console.print(f"\n[bold green]✓ All checks passed for {db_account.email}[/bold green]")


@accounts_app.command("stats")
def account_stats(
    account_id: Optional[str] = typer.Argument(None, help="Account ID (optional, shows all if not specified)"),
) -> None:
    """Show detailed statistics for accounts."""
    db = get_db()

    if account_id:
        accounts = [db.get_account(account_id)]
        if not accounts[0]:
            console.print(f"[red]Error: Account '{account_id}' not found[/red]")
            raise typer.Exit(1)
    else:
        accounts = db.list_accounts()

    if not accounts:
        console.print("[yellow]No accounts found[/yellow]")
        return

    for account in accounts:
        console.print(f"\n[bold cyan]{account.id}[/bold cyan] ({account.email})")
        console.print(f"  Provider: {account.provider}")

        # Message stats
        total = db.count_messages(account_id=account.id)
        unread = db.count_messages(account_id=account.id, is_unread=True)
        inbox = db.count_messages(account_id=account.id, folder="inbox")
        trash = db.count_messages(account_id=account.id, folder="trash")

        console.print(f"  Messages: {total} total, {unread} unread")
        console.print(f"  Folders: {inbox} inbox, {trash} trash")

        if account.last_sync:
            console.print(f"  Last sync: {account.last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            console.print("  Last sync: Never")


def _delete_account_data(db: Database, account_id: str) -> None:
    """Delete an account and all its associated data."""
    from sqlalchemy import delete, select
    from ..db.models import Account, Message, Classification, Attachment

    with db.session() as session:
        # Get all message IDs for this account
        messages = session.execute(
            select(Message.id).where(Message.account_id == account_id)
        ).scalars().all()

        # Delete classifications for these messages
        if messages:
            session.execute(
                delete(Classification).where(Classification.message_id.in_(messages))
            )

            # Delete attachments for these messages
            session.execute(
                delete(Attachment).where(Attachment.message_id.in_(messages))
            )

        # Delete messages
        session.execute(
            delete(Message).where(Message.account_id == account_id)
        )

        # Delete the account
        session.execute(
            delete(Account).where(Account.id == account_id)
        )

        session.commit()


def _delete_account_only(db: Database, account_id: str) -> None:
    """Delete only the account record, keeping messages."""
    from sqlalchemy import delete
    from ..db.models import Account

    with db.session() as session:
        session.execute(
            delete(Account).where(Account.id == account_id)
        )
        session.commit()


def _migrate_messages(db: Database, source_id: str, dest_id: str) -> int:
    """Migrate messages from source account to destination."""
    from sqlalchemy import update
    from ..db.models import Message

    with db.session() as session:
        result = session.execute(
            update(Message)
            .where(Message.account_id == source_id)
            .values(account_id=dest_id)
        )
        session.commit()
        return result.rowcount
