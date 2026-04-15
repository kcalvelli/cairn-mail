"""API routes for sending email messages."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...email.mime_builder import MIMEBuilder
from ...providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/send", tags=["send"])


class SendRequest(BaseModel):
    """Request model for sending a message."""

    draft_id: str


class SendResponse(BaseModel):
    """Response model for sent message."""

    message_id: str
    status: str
    draft_id: str


@router.post("", response_model=SendResponse)
async def send_message(send_request: SendRequest, request: Request):
    """Send a draft message via the provider.

    This will:
    1. Build MIME message from draft
    2. Send via provider (Gmail API or SMTP)
    3. Delete draft upon success

    Args:
        send_request: Send request with draft_id
        request: FastAPI request

    Returns:
        Send response with message ID

    Raises:
        HTTPException: If draft not found, account not found, or send fails
    """
    db = request.app.state.db
    draft_id = send_request.draft_id

    # Get draft
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    # Get account
    account = db.get_account(draft.account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {draft.account_id} not found")

    # Get attachments
    attachments = db.list_attachments(draft_id=draft_id)
    logger.info(f"Sending draft {draft_id} with {len(attachments)} attachment(s)")

    # Log attachment details for debugging
    for att in attachments:
        data_size = len(att.data) if att.data else 0
        logger.info(f"  Attachment: {att.filename}, stored size: {att.size}, actual data: {data_size} bytes")

    try:
        # Build MIME message
        # Use real_name from account settings if configured
        from_name = account.settings.get("real_name") or None
        mime_message = MIMEBuilder.build_from_draft(
            draft=draft,
            attachments=attachments,
            from_name=from_name,
            from_email=account.email,
        )

        # Log final message size
        message_bytes = mime_message.as_bytes()
        logger.info(f"Built MIME message: {len(message_bytes)} bytes total")

        # Validate size for Gmail (25MB limit)
        if account.provider == "gmail":
            is_valid, size = MIMEBuilder.validate_size(mime_message, max_size_mb=25)
            if not is_valid:
                raise HTTPException(
                    status_code=413,
                    detail=f"Message too large ({size / (1024 * 1024):.2f}MB, limit is 25MB)"
                )

        # Create provider and send
        provider = ProviderFactory.create_from_account(account)
        provider.authenticate()

        message_id = provider.send_message(
            mime_message=message_bytes,
            thread_id=draft.thread_id,
        )

        logger.info(f"Sent message {message_id} for draft {draft_id}")

        # Delete draft upon successful send
        db.delete_draft(draft_id)
        logger.info(f"Deleted draft {draft_id} after successful send")

        return SendResponse(
            message_id=message_id,
            status="sent",
            draft_id=draft_id,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        logger.error(f"Failed to send message for draft {draft_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")
