"""Sync command for manual email synchronization."""

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..action_agent import ActionAgent
from ..ai_classifier import AIClassifier, AIConfig
from ..config.actions import merge_actions
from ..config.loader import ConfigLoader
from ..db.database import Database
from ..gateway_client import GatewayClient, GatewayError
from ..providers.factory import ProviderFactory
from ..sync_engine import SyncEngine

console = Console()
sync_app = typer.Typer(help="Email synchronization commands")
logger = logging.getLogger(__name__)


def _create_ai_config(config: dict) -> AIConfig:
    """Create AIConfig from loaded configuration.

    Args:
        config: Configuration dict from ConfigLoader.load_config()

    Returns:
        AIConfig with settings from config file
    """
    ai_settings = ConfigLoader.get_ai_config(config)
    custom_tags = ConfigLoader.get_custom_tags(config)

    return AIConfig(
        model=ai_settings.get("model", "claude-sonnet-4-20250514"),
        endpoint=ai_settings.get("endpoint", "http://localhost:18789"),
        temperature=ai_settings.get("temperature", 0.3),
        custom_tags=custom_tags,
    )


def _create_action_agent(config: dict, db: Database) -> Optional[ActionAgent]:
    """Create ActionAgent from loaded configuration if actions are configured.

    Args:
        config: Configuration dict from ConfigLoader.load_config()
        db: Database instance

    Returns:
        ActionAgent if configured, None otherwise
    """
    # Check if gateway integration is enabled
    gateway_config = config.get("gateway", {})
    if not gateway_config.get("enable", False):
        return None

    gateway_url = gateway_config.get("url", "http://localhost:8085")

    # Get custom actions from config
    custom_actions = config.get("actions", {})
    actions = merge_actions(
        custom_actions if custom_actions else None,
        gateway_config=gateway_config,
    )

    if not actions:
        return None

    ai_settings = ConfigLoader.get_ai_config(config)

    gateway = GatewayClient(base_url=gateway_url)
    return ActionAgent(
        database=db,
        gateway=gateway,
        actions=actions,
        ai_endpoint=ai_settings.get("endpoint", "http://localhost:18789"),
        ai_model=ai_settings.get("model", "claude-sonnet-4-20250514"),
    )


@sync_app.command("run")
def sync_run(
    account: Optional[str] = typer.Option(None, "--account", "-a", help="Account ID to sync"),
    max_messages: int = typer.Option(100, "--max", help="Maximum messages to fetch"),
    db_path: Path = typer.Option(
        Path.home() / ".local/share/axios-ai-mail/mail.db",
        "--db",
        help="Database path",
    ),
) -> None:
    """Manually trigger email sync."""
    console.print("[bold blue]Starting email sync...[/bold blue]")

    # Initialize database
    db = Database(db_path)

    # Load configuration and sync to database
    config = ConfigLoader.load_config()
    if config:
        ConfigLoader.sync_to_database(db, config)

    # Get accounts to sync
    if account:
        db_account = db.get_account(account)
        if not db_account:
            console.print(f"[red]Account not found: {account}[/red]")
            raise typer.Exit(1)
        accounts = [db_account]
    else:
        accounts = db.list_accounts()

    if not accounts:
        console.print("[yellow]No accounts configured[/yellow]")
        console.print("\nAdd accounts to your home.nix configuration and run 'home-manager switch'")
        raise typer.Exit(0)

    # Sync each account
    results = []
    for db_account in accounts:
        console.print(f"\n[bold]Syncing account: {db_account.email}[/bold]")

        # Initialize provider using factory pattern
        provider = ProviderFactory.create_from_account(db_account)
        try:
            provider.authenticate()

            # Initialize AI classifier with config from file
            ai_config = _create_ai_config(config)
            ai_classifier = AIClassifier(ai_config)

            # Log tag configuration
            if ai_config.custom_tags:
                tag_names = [t["name"] for t in ai_config.custom_tags]
                logger.info(f"Using custom tags from config: {tag_names}")

            # Initialize action agent (optional)
            action_agent = _create_action_agent(config, db)
            if action_agent:
                logger.info(f"Action agent enabled with {len(action_agent.actions)} actions")

            # Initialize sync engine
            sync_engine = SyncEngine(
                provider=provider,
                database=db,
                ai_classifier=ai_classifier,
                label_prefix=db_account.settings.get("label_prefix", "AI"),
                action_agent=action_agent,
            )

            # Run sync
            result = sync_engine.sync(max_messages=max_messages)
            results.append(result)

            # Send push notifications for new messages (even if PWA is closed)
            if result.new_messages:
                try:
                    from ..push_service import create_push_service

                    push_svc = create_push_service(db, config)
                    if push_svc:
                        sent = push_svc.notify_new_messages(
                            [msg.to_dict() for msg in result.new_messages]
                        )
                        if sent:
                            console.print(f"  Push notifications sent: {sent}")
                except Exception as e:
                    logger.warning(f"Push notification error: {e}")

            # Display result
            if result.errors:
                console.print(f"[yellow]⚠ Sync completed with {len(result.errors)} errors[/yellow]")
            else:
                console.print("[green]✓ Sync completed successfully[/green]")

            console.print(f"  Messages fetched: {result.messages_fetched}")
            console.print(f"  Messages classified: {result.messages_classified}")
            console.print(f"  Labels updated: {result.labels_updated}")
            if result.actions_processed:
                console.print(f"  Actions: {result.actions_succeeded}/{result.actions_processed} succeeded")
            console.print(f"  Duration: {result.duration_seconds:.2f}s")

        except Exception as e:
            console.print(f"[red]Sync failed for {db_account.email}: {e}[/red]")
            logger.exception("Sync error")
        finally:
            # Release connection back to pool
            provider.release()

    # Summary
    if results:
        console.print("\n[bold]Sync Summary[/bold]")
        table = Table()
        table.add_column("Account")
        table.add_column("Fetched")
        table.add_column("Classified")
        table.add_column("Labeled")
        table.add_column("Errors")

        for result in results:
            table.add_row(
                result.account_id,
                str(result.messages_fetched),
                str(result.messages_classified),
                str(result.labels_updated),
                str(len(result.errors)),
            )

        console.print(table)


@sync_app.command("reclassify")
def sync_reclassify(
    account: str = typer.Argument(..., help="Account ID to reclassify"),
    max_messages: Optional[int] = typer.Option(None, "--max", help="Maximum messages to reclassify"),
    db_path: Path = typer.Option(
        Path.home() / ".local/share/axios-ai-mail/mail.db",
        "--db",
        help="Database path",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
) -> None:
    """Reclassify all messages for an account."""
    console.print(f"[bold blue]Reclassifying messages for account: {account}[/bold blue]")

    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]")

    # Initialize database
    db = Database(db_path)

    # Load configuration and sync to database
    config = ConfigLoader.load_config()
    if config:
        ConfigLoader.sync_to_database(db, config)

    # Get account
    db_account = db.get_account(account)
    if not db_account:
        console.print(f"[red]Account not found: {account}[/red]")
        raise typer.Exit(1)

    try:
        # Initialize provider using factory pattern
        provider = ProviderFactory.create_from_account(db_account)
        provider.authenticate()

        # Initialize AI classifier with config from file
        ai_config = _create_ai_config(config)
        ai_classifier = AIClassifier(ai_config)

        # Log tag configuration
        if ai_config.custom_tags:
            tag_names = [t["name"] for t in ai_config.custom_tags]
            console.print(f"Using custom tags: {', '.join(tag_names)}")

        # Initialize action agent (for preserving action tags during reclassification)
        action_agent = _create_action_agent(config, db)

        # Initialize sync engine
        sync_engine = SyncEngine(
            provider=provider,
            database=db,
            ai_classifier=ai_classifier,
            label_prefix=db_account.settings.get("label_prefix", "AI"),
            action_agent=action_agent,
        )

        # Run reclassification
        with console.status("[bold green]Reclassifying messages..."):
            result = sync_engine.reclassify_all(max_messages=max_messages)

        # Display result
        if result.errors:
            console.print(f"[yellow]⚠ Reclassification completed with {len(result.errors)} errors[/yellow]")
        else:
            console.print("[green]✓ Reclassification completed successfully[/green]")

        console.print(f"  Messages classified: {result.messages_classified}")
        console.print(f"  Labels updated: {result.labels_updated}")
        console.print(f"  Duration: {result.duration_seconds:.2f}s")

        if result.errors and typer.confirm("Show errors?"):
            for error in result.errors[:10]:  # Show first 10
                console.print(f"  [red]•[/red] {error}")

    except Exception as e:
        console.print(f"[red]Reclassification failed: {e}[/red]")
        logger.exception("Reclassification error")
        raise typer.Exit(1)
