"""Message-related API endpoints."""

import asyncio
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

from ...db.models import Message, Classification
from ...providers.factory import ProviderFactory
from ..models import (
    MessageResponse,
    MessagesListResponse,
    UpdateTagsRequest,
    MarkReadRequest,
    SmartReply,
    SmartReplyResponse,
)
from ..websocket import send_messages_updated, send_messages_deleted, send_messages_restored

logger = logging.getLogger(__name__)
router = APIRouter()


# Request models for bulk operations
class BulkReadRequest(BaseModel):
    """Request to mark multiple messages as read/unread."""
    message_ids: List[str]
    is_unread: bool


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple messages."""
    message_ids: List[str]


def serialize_message(message: Message, classification: Optional[Classification] = None) -> dict:
    """Convert Message ORM object to API response dict."""
    data = {
        "id": message.id,
        "account_id": message.account_id,
        "thread_id": message.thread_id,
        "subject": message.subject,
        "from_email": message.from_email,
        "to_emails": message.to_emails,
        "date": message.date,
        "snippet": message.snippet,
        "is_unread": message.is_unread,
        "provider_labels": message.provider_labels,
        "has_attachments": message.has_attachments,
        "tags": [],
        "priority": None,
        "todo": False,
        "can_archive": False,
        "classified_at": None,
    }

    # Add classification data if available
    if classification:
        data.update({
            "tags": classification.tags,
            "priority": classification.priority,
            "todo": classification.todo,
            "can_archive": classification.can_archive,
            "classified_at": classification.classified_at,
            "confidence": classification.confidence,
        })

    return data


@router.get("/messages", response_model=MessagesListResponse)
async def list_messages(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    tag: Optional[str] = Query(None, description="Filter by single tag (deprecated)"),
    tags: Optional[List[str]] = Query(None, description="Filter by multiple tags (OR logic)"),
    is_unread: Optional[bool] = Query(None, description="Filter by read status"),
    folder: Optional[str] = Query(None, description="Filter by folder (inbox, sent, trash)"),
    thread_id: Optional[str] = Query(None, description="Filter by thread ID (for conversation view)"),
    search: Optional[str] = Query(None, description="Search in subject, from, snippet"),
    exclude_hidden_accounts: bool = Query(False, description="Exclude messages from hidden accounts (for GUI)"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """List messages with filtering and pagination.

    By default, all messages are returned including from hidden accounts.
    Use exclude_hidden_accounts=true to filter out hidden account messages (for GUI use).
    When an explicit account_id is provided, hidden filtering is skipped.
    """
    db = request.app.state.db

    try:
        # Get hidden account IDs for filtering (only if requested for GUI, and no explicit account_id)
        exclude_account_ids = None
        if exclude_hidden_accounts and account_id is None:
            accounts = db.list_accounts()
            exclude_account_ids = [
                acc.id for acc in accounts
                if acc.settings and acc.settings.get("hidden", False)
            ]

        # Query messages using database method
        messages = db.query_messages(
            account_id=account_id,
            tag=tag,
            tags=tags,
            is_unread=is_unread,
            folder=folder,
            thread_id=thread_id,
            exclude_account_ids=exclude_account_ids,
            limit=limit + 1,  # Fetch one extra to check if there are more
            offset=offset,
        )

        # Apply search filter if provided (simple client-side filter for now)
        if search:
            search_lower = search.lower()
            messages = [
                m for m in messages
                if search_lower in m.subject.lower()
                or search_lower in m.from_email.lower()
                or search_lower in m.snippet.lower()
            ]

        # Check if there are more results
        has_more = len(messages) > limit
        messages = messages[:limit]

        # Get classifications for all messages
        serialized = []
        for message in messages:
            classification = db.get_classification(message.id)
            serialized.append(serialize_message(message, classification))

        # Get actual total count with same filters
        total = db.count_messages(
            account_id=account_id,
            tag=tag,
            tags=tags,
            is_unread=is_unread,
            folder=folder,
            exclude_account_ids=exclude_account_ids,
        )

        # If search filter was applied, adjust total count
        # (search is client-side filtered, so count only what matched)
        if search:
            # Re-count after search filter
            search_lower = search.lower()
            all_messages = db.query_messages(
                account_id=account_id,
                tag=tag,
                tags=tags,
                is_unread=is_unread,
                folder=folder,
                limit=10000,  # Large limit to get all for count
                offset=0,
            )
            total = sum(
                1 for m in all_messages
                if search_lower in m.subject.lower()
                or search_lower in m.from_email.lower()
                or search_lower in m.snippet.lower()
            )

        return MessagesListResponse(
            messages=serialized,
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"Error listing messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/unread-count")
async def get_unread_count(
    request: Request,
    exclude_hidden_accounts: bool = Query(False, description="Exclude hidden accounts (for GUI)"),
):
    """Get count of unread messages in inbox.

    By default, includes all accounts. Use exclude_hidden_accounts=true for GUI.
    """
    db = request.app.state.db

    try:
        # Get hidden account IDs for filtering (only if requested for GUI)
        exclude_account_ids = None
        if exclude_hidden_accounts:
            accounts = db.list_accounts()
            exclude_account_ids = [
                acc.id for acc in accounts
                if acc.settings and acc.settings.get("hidden", False)
            ]

        count = db.count_messages(
            folder="inbox",
            is_unread=True,
            exclude_account_ids=exclude_account_ids if exclude_account_ids else None,
        )
        return {"count": count}
    except Exception as e:
        logger.error(f"Error getting unread count: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/bulk/read")
async def bulk_mark_read(request: Request, body: BulkReadRequest):
    """Mark multiple messages as read or unread.

    Updates local database immediately and queues provider syncs for background processing.
    This returns instantly regardless of how many messages are being updated.
    """
    db = request.app.state.db

    try:
        updated_count = 0
        updated_ids = []
        queued_count = 0
        errors = []

        operation = "mark_unread" if body.is_unread else "mark_read"

        for message_id in body.message_ids:
            try:
                # 1. Get message
                message = db.get_message(message_id)
                if not message:
                    errors.append({"message_id": message_id, "error": "Not found"})
                    continue

                # 2. Update local database immediately
                updated_message = db.update_message_read_status(message_id, body.is_unread)
                if updated_message:
                    updated_count += 1
                    updated_ids.append(message_id)

                    # 3. Queue for provider sync (non-blocking)
                    if db.queue_pending_operation(message.account_id, message_id, operation):
                        queued_count += 1
                else:
                    errors.append({"message_id": message_id, "error": "Update failed"})
            except Exception as e:
                errors.append({"message_id": message_id, "error": str(e)})
                logger.error(f"Error updating message {message_id}: {e}")

        # 4. Broadcast update to all clients
        if updated_ids:
            action = "unread" if body.is_unread else "read"
            asyncio.create_task(send_messages_updated(updated_ids, action))

        return {
            "updated": updated_count,
            "queued_for_sync": queued_count,
            "total": len(body.message_ids),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in bulk mark read: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/bulk/delete")
async def bulk_delete(request: Request, body: BulkDeleteRequest):
    """Delete multiple messages (moves to trash).

    Updates local database immediately and queues provider syncs for background processing.
    This returns instantly regardless of how many messages are being deleted.
    """
    db = request.app.state.db

    try:
        moved_to_trash_count = 0
        moved_ids = []
        queued_count = 0
        errors = []

        for message_id in body.message_ids:
            try:
                # 1. Get message
                message = db.get_message(message_id)
                if not message:
                    errors.append({"message_id": message_id, "error": "Not found"})
                    continue

                # 2. Update local database immediately
                updated = db.move_to_trash(message_id)
                if updated:
                    moved_to_trash_count += 1
                    moved_ids.append(message_id)

                    # 3. Queue for provider sync (non-blocking)
                    if db.queue_pending_operation(message.account_id, message_id, "trash"):
                        queued_count += 1
                else:
                    errors.append({"message_id": message_id, "error": "Failed to move to trash"})
            except Exception as e:
                errors.append({"message_id": message_id, "error": str(e)})
                logger.error(f"Error deleting message {message_id}: {e}")

        # 4. Broadcast delete to all clients
        if moved_ids:
            asyncio.create_task(send_messages_deleted(moved_ids, permanent=False))

        return {
            "moved_to_trash": moved_to_trash_count,
            "queued_for_sync": queued_count,
            "total": len(body.message_ids),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in bulk delete: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/bulk/restore")
async def bulk_restore(request: Request, body: BulkDeleteRequest):
    """Restore multiple messages from trash to inbox.

    Updates local database immediately and queues provider syncs for background processing.
    This returns instantly regardless of how many messages are being restored.
    """
    db = request.app.state.db

    try:
        restored_count = 0
        restored_ids = []
        queued_count = 0
        errors = []

        for message_id in body.message_ids:
            try:
                # 1. Get message
                message = db.get_message(message_id)
                if not message:
                    errors.append({"message_id": message_id, "error": "Not found"})
                    continue

                # 2. Update local database immediately
                updated = db.restore_from_trash(message_id)
                if updated:
                    restored_count += 1
                    restored_ids.append(message_id)

                    # 3. Queue for provider sync (non-blocking)
                    if db.queue_pending_operation(message.account_id, message_id, "restore"):
                        queued_count += 1
                else:
                    errors.append({"message_id": message_id, "error": "Not found in trash"})
            except Exception as e:
                errors.append({"message_id": message_id, "error": str(e)})
                logger.error(f"Error restoring message {message_id}: {e}")

        # 4. Broadcast restore to all clients
        if restored_ids:
            asyncio.create_task(send_messages_restored(restored_ids))

        return {
            "restored": restored_count,
            "queued_for_sync": queued_count,
            "total": len(body.message_ids),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in bulk restore: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/bulk/permanent-delete")
async def bulk_permanent_delete(request: Request, body: BulkDeleteRequest):
    """Permanently delete multiple messages (cannot be undone)."""
    db = request.app.state.db

    try:
        deleted_count = 0
        deleted_ids = []
        provider_synced_count = 0
        provider_failed_count = 0
        errors = []

        for message_id in body.message_ids:
            try:
                # Phase 1: Get message before deletion
                message = db.get_message(message_id)
                if not message:
                    errors.append({"message_id": message_id, "error": "Not found"})
                    continue

                # Phase 2: Sync to provider first (permanent delete)
                try:
                    account = db.get_account(message.account_id)
                    if account:
                        provider = ProviderFactory.create_from_account(account)
                        provider.authenticate()
                        provider.delete_message(message_id, permanent=True)
                        provider_synced_count += 1
                except Exception as e:
                    provider_failed_count += 1
                    logger.error(f"Provider permanent delete failed for {message_id}: {e}")

                # Phase 3: Delete from database
                success = db.delete_message(message_id)
                if success:
                    deleted_count += 1
                    deleted_ids.append(message_id)
                else:
                    errors.append({"message_id": message_id, "error": "Failed to delete"})
            except Exception as e:
                errors.append({"message_id": message_id, "error": str(e)})
                logger.error(f"Error permanently deleting message {message_id}: {e}")

        # Broadcast permanent delete to all clients
        if deleted_ids:
            asyncio.create_task(send_messages_deleted(deleted_ids, permanent=True))

        return {
            "deleted": deleted_count,
            "provider_synced": provider_synced_count,
            "provider_failed": provider_failed_count,
            "total": len(body.message_ids),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in bulk permanent delete: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class BulkTagsRequest(BaseModel):
    """Request to update tags on multiple messages."""
    message_ids: List[str]
    tags: List[str]


@router.put("/messages/bulk/tags")
async def bulk_update_tags(request: Request, body: BulkTagsRequest):
    """Update tags on multiple messages at once.

    Applies the same tag set to all listed messages. Records DFSL feedback
    for each update so the classification system learns from corrections.
    """
    db = request.app.state.db

    try:
        updated_count = 0
        updated_ids = []
        errors = []

        for message_id in body.message_ids:
            try:
                message = db.get_message(message_id)
                if not message:
                    errors.append({"message_id": message_id, "error": "Not found"})
                    continue

                classification = db.get_classification(message_id)
                if classification:
                    db.update_message_tags(
                        message_id=message_id,
                        tags=body.tags,
                        user_edited=True,
                    )
                else:
                    db.store_classification(
                        message_id=message_id,
                        tags=body.tags,
                        priority="normal",
                        todo=False,
                        can_archive=False,
                        model="manual",
                        confidence=1.0,
                    )

                updated_count += 1
                updated_ids.append(message_id)
            except Exception as e:
                errors.append({"message_id": message_id, "error": str(e)})
                logger.error(f"Error updating tags for message {message_id}: {e}")

        if updated_ids:
            asyncio.create_task(send_messages_updated(updated_ids, "tags_updated"))

        return {
            "updated": updated_count,
            "total": len(body.message_ids),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in bulk update tags: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(request: Request, message_id: str):
    """Get a single message by ID."""
    db = request.app.state.db

    try:
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        classification = db.get_classification(message_id)
        return serialize_message(message, classification)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/messages/{message_id}/tags", response_model=MessageResponse)
async def update_message_tags(
    request: Request,
    message_id: str,
    body: UpdateTagsRequest,
):
    """Update tags for a message."""
    db = request.app.state.db

    try:
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Get existing classification
        classification = db.get_classification(message_id)

        if classification:
            # Update existing classification with DFSL feedback recording
            db.update_message_tags(
                message_id=message_id,
                tags=body.tags,
                user_edited=True,  # Record DFSL feedback if tags changed
            )
        else:
            # Create new classification (manual tagging)
            db.store_classification(
                message_id=message_id,
                tags=body.tags,
                priority="normal",
                todo=False,
                can_archive=False,
                model="manual",
                confidence=1.0,
            )

        # Broadcast update to all clients
        asyncio.create_task(send_messages_updated([message_id], "tags_updated"))

        # Get updated classification
        updated_classification = db.get_classification(message_id)
        return serialize_message(message, updated_classification)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating tags for message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/{message_id}/body")
async def get_message_body(request: Request, message_id: str):
    """Get full message body (text and HTML) with inline attachments."""
    import base64

    db = request.app.state.db
    config = request.app.state.config

    try:
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # If body is not in database, fetch it from provider on-demand
        if not message.body_text and not message.body_html:
            logger.info(f"Body not in DB for {message_id}, fetching from provider")

            # Only attempt on-demand fetch if config is available
            if config:
                try:
                    # Get provider for this account
                    # Note: ProviderFactory is imported at module level
                    from ...config.loader import AccountConfig

                    # Find account config
                    account_config = None
                    for acc in config.accounts:
                        if acc.id == message.account_id:
                            account_config = acc
                            break

                    if account_config:
                        # Create provider and fetch body
                        provider = ProviderFactory.create_provider(account_config)
                        body_text, body_html = provider.fetch_body(message.id)

                        # Update database with fetched body
                        db.update_message_body(message.id, body_text, body_html)

                        # Update in-memory message object
                        message.body_text = body_text
                        message.body_html = body_html

                        logger.info(f"Fetched and cached body for {message_id}")
                    else:
                        logger.warning(f"Account config not found for {message.account_id}")
                except Exception as fetch_error:
                    logger.error(f"Failed to fetch body for {message_id}: {fetch_error}", exc_info=True)
                    # Continue and return what we have (might be None)
            else:
                logger.warning("Config not available, cannot fetch body on-demand")

        # Fetch inline attachments if HTML body contains cid: references
        inline_attachments = []
        if message.body_html and "cid:" in message.body_html:
            try:
                account = db.get_account(message.account_id)
                if account:
                    provider = ProviderFactory.create_from_account(account)
                    provider.authenticate()

                    # Get all attachments
                    attachments = provider.list_attachments(message_id)

                    # Filter to inline attachments with content_id
                    for att in attachments:
                        content_id = att.get("content_id", "")
                        if content_id and att.get("is_inline", False):
                            try:
                                # Fetch attachment data
                                data = provider.get_attachment(message_id, att["id"])
                                # Convert to base64 data URL
                                data_url = f"data:{att['content_type']};base64,{base64.b64encode(data).decode('ascii')}"
                                inline_attachments.append({
                                    "content_id": content_id,
                                    "data_url": data_url,
                                })
                                logger.debug(f"Fetched inline attachment: cid:{content_id}")
                            except Exception as att_error:
                                logger.warning(f"Failed to fetch inline attachment {att['id']}: {att_error}")
            except Exception as e:
                logger.warning(f"Failed to fetch inline attachments for {message_id}: {e}")

        return {
            "id": message.id,
            "body_text": message.body_text,
            "body_html": message.body_html,
            "inline_attachments": inline_attachments,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting message body {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/{message_id}/read", response_model=MessageResponse)
async def mark_message_read(
    request: Request,
    message_id: str,
    body: MarkReadRequest,
):
    """Mark a message as read or unread.

    Updates local database immediately and queues provider sync for background processing.
    This provides instant UI feedback while ensuring provider sync happens reliably.
    """
    db = request.app.state.db

    try:
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # 1. Update local database immediately
        updated_message = db.update_message_read_status(message_id, body.is_unread)
        if not updated_message:
            raise HTTPException(status_code=404, detail="Message not found")

        # 2. Queue for provider sync (non-blocking)
        operation = "mark_unread" if body.is_unread else "mark_read"
        db.queue_pending_operation(message.account_id, message_id, operation)

        # 3. Broadcast update to all clients
        action = "unread" if body.is_unread else "read"
        asyncio.create_task(send_messages_updated([message_id], action))

        classification = db.get_classification(message_id)
        response = serialize_message(updated_message, classification)
        response["provider_synced"] = False  # Will sync during next background sync
        response["queued_for_sync"] = True
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/messages/{message_id}")
async def delete_message(request: Request, message_id: str):
    """Delete a message (moves to trash).

    Updates local database immediately and queues provider sync for background processing.
    """
    db = request.app.state.db

    try:
        # Check if message exists
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # 1. Update local database immediately
        updated_message = db.move_to_trash(message_id)
        if not updated_message:
            raise HTTPException(status_code=500, detail="Failed to move message to trash")

        # 2. Queue for provider sync (non-blocking)
        db.queue_pending_operation(message.account_id, message_id, "trash")

        # 3. Broadcast delete to all clients
        asyncio.create_task(send_messages_deleted([message_id], permanent=False))

        return {
            "status": "moved_to_trash",
            "message_id": message_id,
            "provider_synced": False,
            "queued_for_sync": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/{message_id}/restore")
async def restore_message(request: Request, message_id: str):
    """Restore a message from trash to inbox.

    Updates local database immediately and queues provider sync for background processing.
    """
    db = request.app.state.db

    try:
        # Get message before restore (to get account_id)
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # 1. Restore from trash in local database immediately
        updated_message = db.restore_from_trash(message_id)
        if not updated_message:
            raise HTTPException(status_code=404, detail="Message not found in trash")

        # 2. Queue for provider sync (non-blocking)
        db.queue_pending_operation(message.account_id, message_id, "restore")

        # 3. Broadcast restore to all clients
        asyncio.create_task(send_messages_restored([message_id]))

        classification = db.get_classification(message_id)
        response = serialize_message(updated_message, classification)
        response["provider_synced"] = False
        response["queued_for_sync"] = True
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/delete-all")
async def delete_all_messages(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    is_unread: Optional[bool] = Query(None, description="Filter by read status"),
    folder: Optional[str] = Query(None, description="Filter by folder"),
    search: Optional[str] = Query(None, description="Search filter"),
):
    """Delete all messages matching the given filters."""
    db = request.app.state.db

    try:
        # Query messages with filters (no limit to get all matching)
        messages = db.query_messages(
            account_id=account_id,
            tags=tags,
            is_unread=is_unread,
            folder=folder,
            limit=100000,  # Large limit to get all
            offset=0,
        )

        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            messages = [
                m for m in messages
                if search_lower in m.subject.lower()
                or search_lower in m.from_email.lower()
                or search_lower in m.snippet.lower()
            ]

        # Delete all matching messages (always move to trash)
        moved_to_trash_count = 0
        errors = []

        for message in messages:
            try:
                # Always move to trash
                updated = db.move_to_trash(message.id)
                if updated:
                    moved_to_trash_count += 1
                else:
                    errors.append({"message_id": message.id, "error": "Failed to move to trash"})
            except Exception as e:
                errors.append({"message_id": message.id, "error": str(e)})
                logger.error(f"Error deleting message {message.id}: {e}")

        return {
            "moved_to_trash": moved_to_trash_count,
            "total": len(messages),
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Error in delete all: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/clear-trash")
async def clear_trash(request: Request):
    """Permanently delete all messages in trash folder.

    Uses async pattern: immediately marks messages as 'deleting' and queues
    pending operations for provider sync. The sync engine will process the
    actual provider deletion in the background.
    """
    db = request.app.state.db

    try:
        # Query all messages in trash
        trash_messages = db.query_messages(folder="trash", limit=100000, offset=0)

        if not trash_messages:
            return {
                "deleted": 0,
                "queued": 0,
                "total": 0,
            }

        # Mark messages as 'deleting' and queue pending operations
        queued_count = 0
        errors = []

        for message in trash_messages:
            try:
                # Queue a delete operation for async provider sync
                db.queue_pending_operation(
                    account_id=message.account_id,
                    message_id=message.id,
                    operation="delete",
                )
                queued_count += 1
            except Exception as e:
                errors.append({"message_id": message.id, "error": str(e)})
                logger.error(f"Error queuing delete for message {message.id}: {e}")

        # Mark all trash messages as 'deleting' so they don't show in trash view
        # This is done in bulk for efficiency
        with db.session() as session:
            for message in trash_messages:
                msg = session.get(Message, message.id)
                if msg and msg.folder == "trash":
                    msg.folder = "deleting"
            session.commit()

        logger.info(f"Clear trash: queued {queued_count} messages for deletion")

        return {
            "deleted": queued_count,  # Messages are marked for deletion
            "queued": queued_count,   # Operations queued for provider sync
            "total": len(trash_messages),
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"Error clearing trash: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/search")
async def search_messages(
    request: Request,
    q: str = Query(..., description="Search query"),
    account_id: Optional[str] = Query(None, description="Filter by account"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Full-text search across message bodies and subjects using FTS5."""
    db = request.app.state.db

    try:
        # Use FTS5 virtual table for full-text search
        # For now, fall back to simple LIKE search (FTS5 integration can be enhanced later)
        with db.session() as session:
            from sqlalchemy import or_
            query = session.query(Message)

            if account_id:
                query = query.where(Message.account_id == account_id)

            # Simple text search (can be enhanced with FTS5 later)
            search_pattern = f"%{q}%"
            query = query.where(
                or_(
                    Message.subject.like(search_pattern),
                    Message.from_email.like(search_pattern),
                    Message.snippet.like(search_pattern),
                    Message.body_text.like(search_pattern) if Message.body_text else False,
                )
            )

            # Order by date descending
            query = query.order_by(Message.date.desc())

            # Pagination
            total_query = query
            total = total_query.count()

            messages = query.offset(offset).limit(limit).all()

            # Serialize messages
            serialized = []
            for message in messages:
                classification = db.get_classification(message.id)
                serialized.append(serialize_message(message, classification))

            return {
                "messages": serialized,
                "total": total,
                "limit": limit,
                "offset": offset,
                "query": q,
            }

    except Exception as e:
        logger.error(f"Error searching messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages/{message_id}/smart-replies", response_model=SmartReplyResponse)
async def get_smart_replies(request: Request, message_id: str):
    """Generate AI-powered smart reply suggestions for a message.

    Returns 3-4 short, contextual reply suggestions based on message content.
    Returns empty replies array for:
    - Messages in Sent folder
    - Messages tagged as newsletter or junk
    - When AI generation fails (graceful degradation)
    """
    db = request.app.state.db
    from datetime import datetime
    from ...ai_classifier import AIClassifier, AIConfig

    try:
        # Check if message exists
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Check if message is from sent folder - don't generate replies for own messages
        if message.folder == "sent":
            logger.debug(f"Skipping smart replies for sent message {message_id}")
            return SmartReplyResponse(
                replies=[],
                generated_at=datetime.utcnow(),
            )

        # Check classification - skip newsletters and junk
        classification = db.get_classification(message_id)
        if classification:
            skip_tags = {"newsletter", "junk"}
            if any(tag in skip_tags for tag in classification.tags):
                logger.debug(
                    f"Skipping smart replies for message {message_id} "
                    f"with tags {classification.tags}"
                )
                return SmartReplyResponse(
                    replies=[],
                    generated_at=datetime.utcnow(),
                )

        # Create provider Message object for AI classifier
        from ...providers.base import Message as ProviderMessage

        provider_message = ProviderMessage(
            id=message.id,
            thread_id=message.thread_id or "",
            subject=message.subject,
            from_email=message.from_email,
            to_emails=message.to_emails,
            date=message.date,
            snippet=message.snippet,
            body_text=message.body_text,
            body_html=message.body_html,
            is_unread=message.is_unread,
            has_attachments=message.has_attachments,
            labels=set(message.provider_labels) if message.provider_labels else set(),
        )

        # Generate replies using AI classifier
        try:
            # Get AI config from app state if available, otherwise use defaults
            ai_config = getattr(request.app.state, "ai_config", None)
            if ai_config is None:
                ai_config = AIConfig()

            classifier = AIClassifier(ai_config)
            reply_texts = classifier.generate_replies(provider_message)

            # Convert to SmartReply objects with IDs
            replies = [
                SmartReply(id=str(i + 1), text=text)
                for i, text in enumerate(reply_texts)
            ]

            return SmartReplyResponse(
                replies=replies,
                generated_at=datetime.utcnow(),
            )

        except Exception as ai_error:
            # Graceful degradation - return empty replies on AI error
            logger.warning(
                f"AI reply generation failed for message {message_id}: {ai_error}"
            )
            return SmartReplyResponse(
                replies=[],
                generated_at=datetime.utcnow(),
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting smart replies for {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
