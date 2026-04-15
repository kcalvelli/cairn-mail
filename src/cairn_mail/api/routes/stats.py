"""Statistics and analytics API endpoints."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import TagsListResponse, TagResponse, StatsResponse, AvailableTagsResponse, AvailableTagResponse
from ...config.actions import merge_actions
from ...config.tags import DEFAULT_TAGS, action_tags_from_definitions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/tags", response_model=TagsListResponse)
async def list_tags(
    request: Request,
    exclude_hidden_accounts: bool = Query(False, description="Exclude hidden accounts (for GUI)"),
):
    """List all tags (AI + account) with counts and percentages.

    Only counts messages in inbox (excludes trash) so counts match
    what users see when filtering by tag.
    Use exclude_hidden_accounts=true to filter out hidden accounts (for GUI use).
    """
    db = request.app.state.db

    try:
        # Get hidden account IDs for filtering (only if requested for GUI)
        accounts = db.list_accounts()
        hidden_account_ids = []
        if exclude_hidden_accounts:
            hidden_account_ids = [
                acc.id for acc in accounts
                if acc.settings and acc.settings.get("hidden", False)
            ]

        # Get messages in inbox only (exclude trash, optionally exclude hidden accounts)
        all_messages = db.query_messages(
            folder="inbox",
            exclude_account_ids=hidden_account_ids if hidden_account_ids else None,
            limit=100000,
        )
        total_messages = len(all_messages)

        # Count AI tags
        tag_counts = {}
        total_classified = 0

        for message in all_messages:
            classification = db.get_classification(message.id)
            if classification:
                total_classified += 1
                for tag in classification.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        # Build AI tag responses
        tags = []
        for tag_name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_classified * 100) if total_classified > 0 else 0
            tags.append(TagResponse(
                name=tag_name,
                count=count,
                percentage=percentage,
                type="ai",
            ))

        # Count messages per account (account tags)
        account_counts = {}
        for message in all_messages:
            account_id = message.account_id
            account_counts[account_id] = account_counts.get(account_id, 0) + 1

        # Get account details to include email as tag name (optionally exclude hidden accounts)
        if exclude_hidden_accounts:
            account_map = {acc.id: acc for acc in accounts if acc.id not in hidden_account_ids}
        else:
            account_map = {acc.id: acc for acc in accounts}

        # Build account tag responses
        for account_id, count in sorted(account_counts.items(), key=lambda x: x[1], reverse=True):
            account = account_map.get(account_id)
            if account:  # Will be None for hidden accounts
                percentage = (count / total_messages * 100) if total_messages > 0 else 0
                tags.append(TagResponse(
                    name=account.email,  # Use email as tag name
                    count=count,
                    percentage=percentage,
                    type="account",
                ))

        return TagsListResponse(
            tags=tags,
            total_classified=total_classified,
        )

    except Exception as e:
        logger.error(f"Error listing tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tags/available", response_model=AvailableTagsResponse)
async def list_available_tags(request: Request):
    """List all available tags from the taxonomy.

    Returns all defined tags that can be used for classification,
    not just tags currently assigned to messages.
    """
    try:
        # Get tags from config if available (includes custom tags)
        config = getattr(request.app.state, 'config', None)
        custom_tags = []

        if config and hasattr(config, 'ai') and config.ai:
            custom_tags = config.ai.get('tags', [])

        # Build response from default tags + custom tags
        tags = []
        seen_names = set()

        # Add default tags
        for tag in DEFAULT_TAGS:
            tags.append(AvailableTagResponse(
                name=tag["name"],
                description=tag["description"],
                category=tag["category"],
            ))
            seen_names.add(tag["name"])

        # Add custom tags that aren't in defaults
        for tag in custom_tags:
            if tag.get("name") and tag["name"] not in seen_names:
                tags.append(AvailableTagResponse(
                    name=tag["name"],
                    description=tag.get("description", f"Custom tag: {tag['name']}"),
                    category=tag.get("category", "custom"),
                ))
                seen_names.add(tag["name"])

        # Add action tags from action definitions (only if gateway is enabled)
        app_config = getattr(request.app.state, 'config', None) or {}
        if isinstance(app_config, dict) and app_config.get("gateway", {}).get("enable", False):
            custom_actions = app_config.get("actions", {})
            actions = merge_actions(custom_actions if custom_actions else None)
            action_tags = action_tags_from_definitions(actions)
            for tag in action_tags:
                if tag["name"] not in seen_names:
                    tags.append(AvailableTagResponse(
                        name=tag["name"],
                        description=tag["description"],
                        category="action",
                    ))
                    seen_names.add(tag["name"])

        return AvailableTagsResponse(tags=tags)

    except Exception as e:
        logger.error(f"Error listing available tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    request: Request,
    exclude_hidden_accounts: bool = Query(False, description="Exclude hidden accounts (for GUI)"),
):
    """Get overall system statistics.

    Only counts messages in inbox (excludes trash).
    Use exclude_hidden_accounts=true to filter out hidden accounts (for GUI use).
    """
    db = request.app.state.db

    try:
        # Get hidden account IDs for filtering (only if requested for GUI)
        all_accounts = db.list_accounts()
        hidden_account_ids = []
        if exclude_hidden_accounts:
            hidden_account_ids = [
                acc.id for acc in all_accounts
                if acc.settings and acc.settings.get("hidden", False)
            ]
            # Visible accounts only for GUI
            accounts = [acc for acc in all_accounts if acc.id not in hidden_account_ids]
        else:
            accounts = all_accounts

        # Get messages in inbox only (exclude trash, optionally exclude hidden accounts)
        all_messages = db.query_messages(
            folder="inbox",
            exclude_account_ids=hidden_account_ids if hidden_account_ids else None,
            limit=100000,
        )
        unread_messages = db.query_messages(
            folder="inbox",
            is_unread=True,
            exclude_account_ids=hidden_account_ids if hidden_account_ids else None,
            limit=100000,
        )

        # Count classified messages
        classified_count = sum(1 for msg in all_messages if db.has_classification(msg.id))

        # Calculate classification rate
        total_count = len(all_messages)
        classification_rate = (classified_count / total_count * 100) if total_count > 0 else 0

        # Get top tags
        tag_counts = {}
        for message in all_messages:
            classification = db.get_classification(message.id)
            if classification:
                for tag in classification.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = []
        for tag_name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            percentage = (count / classified_count * 100) if classified_count > 0 else 0
            top_tags.append(TagResponse(
                name=tag_name,
                count=count,
                percentage=percentage,
            ))

        # Calculate accounts breakdown
        accounts_breakdown = {}
        for message in all_messages:
            account_id = message.account_id
            accounts_breakdown[account_id] = accounts_breakdown.get(account_id, 0) + 1

        # Get most recent last_sync across all accounts
        last_sync = None
        for account in accounts:
            if account.last_sync:
                if last_sync is None or account.last_sync > last_sync:
                    last_sync = account.last_sync

        return StatsResponse(
            total_messages=total_count,
            classified_messages=classified_count,
            unread_messages=len(unread_messages),
            classification_rate=classification_rate,
            accounts_count=len(accounts),
            top_tags=top_tags,
            accounts_breakdown=accounts_breakdown,
            last_sync=last_sync,
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
