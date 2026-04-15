"""Sync-related API endpoints."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Optional, Set

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks

from ..models import SyncStatusResponse, SyncResultResponse, TriggerSyncRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# Thread pool for running blocking sync operations in parallel
_sync_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="sync-")

# Global sync state - now tracks multiple accounts
_sync_state = {
    "is_syncing": False,
    "syncing_accounts": set(),  # Set of account IDs currently syncing
    "last_sync": None,
}


def get_sync_state() -> dict:
    """Get current sync state."""
    state = _sync_state.copy()
    # Convert set to list for JSON serialization
    state["syncing_accounts"] = list(state["syncing_accounts"])
    # For backwards compatibility, set current_account to first syncing account
    state["current_account"] = state["syncing_accounts"][0] if state["syncing_accounts"] else None
    return state


def set_sync_state(is_syncing: bool, account_ids: Optional[Set[str]] = None):
    """Update sync state."""
    _sync_state["is_syncing"] = is_syncing
    if account_ids is not None:
        _sync_state["syncing_accounts"] = account_ids
    elif not is_syncing:
        _sync_state["syncing_accounts"] = set()
    if not is_syncing:
        _sync_state["last_sync"] = datetime.now(timezone.utc)


def add_syncing_account(account_id: str):
    """Add an account to the syncing set."""
    _sync_state["syncing_accounts"].add(account_id)
    _sync_state["is_syncing"] = True


def remove_syncing_account(account_id: str):
    """Remove an account from the syncing set."""
    _sync_state["syncing_accounts"].discard(account_id)
    if not _sync_state["syncing_accounts"]:
        _sync_state["is_syncing"] = False
        _sync_state["last_sync"] = datetime.now(timezone.utc)


def _sync_account_blocking(account, ai_config, db, max_messages: int, config: dict = None):
    """Synchronously sync a single account (runs in thread pool).

    This blocking function is run in a thread pool to allow parallel
    sync of multiple accounts.

    Returns:
        Tuple of (account_id, result, error) where result is SyncResult
        or None if there was an error.
    """
    from ...action_agent import ActionAgent
    from ...config.actions import merge_actions
    from ...gateway_client import GatewayClient
    from ...sync_engine import SyncEngine
    from ...ai_classifier import AIClassifier
    from ...providers.factory import ProviderFactory

    provider = ProviderFactory.create_from_account(account)

    try:
        provider.authenticate()

        ai_classifier = AIClassifier(ai_config)

        # Initialize action agent if gateway integration is enabled
        action_agent = None
        if config and config.get("gateway", {}).get("enable", False):
            gateway_config = config.get("gateway", {})
            gateway_url = gateway_config.get("url", "http://localhost:8085")
            custom_actions = config.get("actions", {})
            actions = merge_actions(
                custom_actions if custom_actions else None,
                gateway_config=gateway_config,
            )

            if actions:
                ai_settings = config.get("ai", {})
                gateway = GatewayClient(base_url=gateway_url)
                action_agent = ActionAgent(
                    database=db,
                    gateway=gateway,
                    actions=actions,
                    ai_endpoint=ai_settings.get("endpoint", "http://localhost:18789"),
                    ai_model=ai_settings.get("model", "claude-sonnet-4-20250514"),
                )

        sync_engine = SyncEngine(
            provider=provider,
            database=db,
            ai_classifier=ai_classifier,
            label_prefix=account.settings.get("label_prefix", "AI"),
            action_agent=action_agent,
        )

        result = sync_engine.sync(max_messages=max_messages)
        logger.info(f"Sync completed for {account.id}: {result}")
        return (account.id, result, None)

    except Exception as e:
        logger.error(f"Sync failed for {account.id}: {e}", exc_info=True)
        return (account.id, None, str(e))
    finally:
        provider.release()


async def _sync_single_account(account, ai_config, db, max_messages: int, loop, config: dict = None):
    """Async wrapper to sync a single account using thread pool.

    Sends WebSocket events and manages sync state for one account.
    """
    from ..websocket import send_sync_started, send_sync_completed, send_error, send_new_messages, send_messages_updated, send_action_completed
    from functools import partial

    account_id = account.id
    add_syncing_account(account_id)

    try:
        # Send WebSocket event: sync started
        await send_sync_started(account_id)

        # Run blocking sync in thread pool (use partial to pass config kwarg)
        sync_fn = partial(_sync_account_blocking, account, ai_config, db, max_messages, config)
        account_id, result, error = await loop.run_in_executor(
            _sync_executor,
            sync_fn,
        )

        if error:
            await send_error(f"Sync failed for {account_id}", error)
        else:
            # Send push notifications for new messages (even if PWA is closed)
            if result.new_messages:
                try:
                    from ...push_service import create_push_service
                    from ...config.loader import ConfigLoader
                    push_svc = create_push_service(db, ConfigLoader.load_config())
                    if push_svc:
                        push_svc.notify_new_messages(
                            [msg.to_dict() for msg in result.new_messages]
                        )
                except Exception as e:
                    logger.warning(f"Push notification error: {e}")

            # Send WebSocket event: new messages for notifications
            if result.new_messages:
                await send_new_messages([msg.to_dict() for msg in result.new_messages])

            # Send WebSocket event: action tag changes
            if result.action_modified_messages:
                await send_messages_updated(result.action_modified_messages, "tags_updated")

            # Send WebSocket event: action completion toasts
            for action_result in result.action_results:
                await send_action_completed(
                    action_name=action_result["action_name"],
                    status=action_result["status"],
                    message_subject=action_result.get("message_subject", ""),
                )

            # Send WebSocket event: sync completed
            await send_sync_completed(account_id, {
                "fetched": result.messages_fetched,
                "classified": result.messages_classified,
                "labeled": result.labels_updated,
                "errors": len(result.errors),
                "new_count": len(result.new_messages),
            })

    finally:
        remove_syncing_account(account_id)


async def run_sync_task(db, account_id: Optional[str], max_messages: int):
    """Run sync in background, syncing multiple accounts in parallel."""
    from ...ai_classifier import AIConfig
    from ...config.loader import ConfigLoader
    from ..websocket import send_error

    try:
        # Load AI config from file (shared across all accounts)
        config = ConfigLoader.load_config()
        ai_settings = ConfigLoader.get_ai_config(config)
        custom_tags = ConfigLoader.get_custom_tags(config)

        if custom_tags:
            tag_names = [t["name"] for t in custom_tags]
            logger.info(f"Using custom tags from config: {tag_names}")

        # Create shared AI config
        ai_config = AIConfig(
            model=ai_settings["model"],
            endpoint=ai_settings["endpoint"],
            temperature=ai_settings["temperature"],
            custom_tags=custom_tags,
        )

        # Get account(s) to sync
        if account_id:
            accounts = [db.get_account(account_id)]
            if not accounts[0]:
                logger.error(f"Account {account_id} not found")
                await send_error(f"Account {account_id} not found")
                return
        else:
            accounts = db.list_accounts()

        # Filter out None accounts
        accounts = [a for a in accounts if a]

        if not accounts:
            logger.warning("No accounts to sync")
            return

        # Get event loop for running in executor
        loop = asyncio.get_event_loop()

        # Sync all accounts in parallel
        logger.info(f"Starting parallel sync for {len(accounts)} account(s)")
        tasks = [
            _sync_single_account(account, ai_config, db, max_messages, loop, config)
            for account in accounts
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All account syncs completed")

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        await send_error("Sync failed", str(e))
    finally:
        # Ensure state is cleaned up
        set_sync_state(False)


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(request: Request):
    """Get current sync status."""
    state = get_sync_state()

    message = "Idle"
    if state["is_syncing"]:
        syncing = state.get("syncing_accounts", [])
        if len(syncing) == 1:
            message = f"Syncing account: {syncing[0]}"
        elif syncing:
            message = f"Syncing {len(syncing)} accounts: {', '.join(syncing)}"
        else:
            message = "Syncing..."

    return SyncStatusResponse(
        is_syncing=state["is_syncing"],
        current_account=state.get("current_account"),
        last_sync=state.get("last_sync"),
        message=message,
    )


@router.post("/sync", response_model=SyncStatusResponse)
async def trigger_sync(
    request: Request,
    background_tasks: BackgroundTasks,
    body: TriggerSyncRequest = TriggerSyncRequest(),
):
    """Trigger a manual sync operation."""
    db = request.app.state.db
    state = get_sync_state()

    # Check if already syncing
    if state["is_syncing"]:
        raise HTTPException(
            status_code=409,
            detail=f"Sync already in progress for account: {state.get('current_account')}"
        )

    # Start sync in background
    background_tasks.add_task(
        run_sync_task,
        db,
        body.account_id,
        body.max_messages,
    )

    return SyncStatusResponse(
        is_syncing=True,
        current_account=body.account_id,
        message="Sync started",
    )
