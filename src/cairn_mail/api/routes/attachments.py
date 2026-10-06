"""API routes for attachment management."""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...providers.factory import ProviderFactory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/attachments", tags=["attachments"])


class AttachmentResponse(BaseModel):
    """Response model for attachment metadata."""

    id: str
    filename: str
    content_type: str
    size: int
    draft_id: Optional[str]
    message_id: Optional[str]
    created_at: str


@router.post("/drafts/{draft_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(
    draft_id: str, file: UploadFile = File(...), request: Request = None
):
    """Upload an attachment to a draft.

    Args:
        draft_id: Draft ID to attach to
        file: Uploaded file
        request: FastAPI request

    Returns:
        Attachment metadata

    Raises:
        HTTPException: If draft not found
    """
    db = request.app.state.db

    # Verify draft exists
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    # Read file data
    file_data = await file.read()

    # Generate attachment ID
    attachment_id = str(uuid.uuid4())

    # Store attachment in database
    attachment = db.add_attachment(
        attachment_id=attachment_id,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(file_data),
        data=file_data,
        draft_id=draft_id,
    )

    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        draft_id=attachment.draft_id,
        message_id=attachment.message_id,
        created_at=attachment.created_at.isoformat(),
    )


@router.post(
    "/drafts/{draft_id}/forward-from/{message_id}",
    response_model=List[AttachmentResponse],
)
async def copy_forwarded_attachments(draft_id: str, message_id: str, request: Request):
    """Copy every attachment on a received message onto a draft.

    This is what makes Forward actually forward. Inline images ride along too:
    the compose editor strips <img> tags, so dropping them would silently lose
    content. Anything already on the draft (same filename + size) is skipped,
    so a double-fire from the UI doesn't double the payload.
    """
    db = request.app.state.db

    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    message = db.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

    account = db.get_account(message.account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {message.account_id} not found")

    existing = {(a.filename, a.size) for a in db.list_attachments(draft_id=draft_id)}

    try:
        provider = ProviderFactory.create_from_account(account)
        provider.authenticate()
        source_attachments = provider.list_attachments(message_id)

        copied = []
        for att in source_attachments:
            data = provider.get_attachment(message_id, att["id"])
            if (att["filename"], len(data)) in existing:
                continue
            copied.append(
                db.add_attachment(
                    attachment_id=str(uuid.uuid4()),
                    filename=att["filename"],
                    content_type=att.get("content_type") or "application/octet-stream",
                    size=len(data),
                    data=data,
                    draft_id=draft_id,
                )
            )
    except Exception as e:
        logger.error(
            f"Failed to copy attachments from {message_id} to draft {draft_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to copy forwarded attachments")

    logger.info(f"Copied {len(copied)} attachment(s) from {message_id} to draft {draft_id}")

    return [
        AttachmentResponse(
            id=att.id,
            filename=att.filename,
            content_type=att.content_type,
            size=att.size,
            draft_id=att.draft_id,
            message_id=att.message_id,
            created_at=att.created_at.isoformat(),
        )
        for att in copied
    ]


@router.get("/drafts/{draft_id}/attachments", response_model=List[AttachmentResponse])
async def list_draft_attachments(draft_id: str, request: Request):
    """List all attachments for a draft.

    Args:
        draft_id: Draft ID
        request: FastAPI request

    Returns:
        List of attachment metadata
    """
    db = request.app.state.db

    attachments = db.list_attachments(draft_id=draft_id)

    return [
        AttachmentResponse(
            id=att.id,
            filename=att.filename,
            content_type=att.content_type,
            size=att.size,
            draft_id=att.draft_id,
            message_id=att.message_id,
            created_at=att.created_at.isoformat(),
        )
        for att in attachments
    ]


@router.get("/messages/{message_id}/attachments", response_model=List[AttachmentResponse])
async def list_message_attachments(message_id: str, request: Request):
    """List all attachments for a message.

    This fetches from the provider (Gmail/IMAP) in real-time.

    Args:
        message_id: Message ID
        request: FastAPI request

    Returns:
        List of attachment metadata

    Raises:
        HTTPException: If message not found or provider error
    """
    db = request.app.state.db
    logger.info(f"Listing attachments for message {message_id}")

    # Get message to determine account
    message = db.get_message(message_id)
    if not message:
        logger.warning(f"Message {message_id} not found in database")
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

    logger.info(f"Message found: has_attachments={message.has_attachments}, account={message.account_id}")

    # Get account
    account = db.get_account(message.account_id)
    if not account:
        logger.warning(f"Account {message.account_id} not found in database")
        raise HTTPException(status_code=404, detail=f"Account {message.account_id} not found")

    logger.info(f"Account found: provider={account.provider}, email={account.email}")

    try:
        # Create provider and fetch attachments
        provider = ProviderFactory.create_from_account(account)
        provider.authenticate()
        logger.info(f"Provider authenticated for {account.provider}")

        attachments = provider.list_attachments(message_id)
        logger.info(f"Provider returned {len(attachments)} attachments for {message_id}")

        for att in attachments:
            logger.info(f"  Attachment: {att.get('filename', 'unknown')} ({att.get('size', 0)} bytes)")

        return [
            AttachmentResponse(
                id=att["id"],
                filename=att["filename"],
                content_type=att["content_type"],
                size=int(att["size"]),
                draft_id=None,
                message_id=message_id,
                created_at=message.date.isoformat(),
            )
            for att in attachments
        ]

    except Exception as e:
        logger.error(f"Failed to list attachments for message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list attachments")


@router.get("/{attachment_id}/download")
async def download_attachment(attachment_id: str, message_id: Optional[str] = None, request: Request = None):
    """Download an attachment.

    For draft attachments: use attachment_id only
    For message attachments: use attachment_id and message_id

    Args:
        attachment_id: Attachment ID
        message_id: Optional message ID (for provider attachments)
        request: FastAPI request

    Returns:
        File download

    Raises:
        HTTPException: If attachment not found
    """
    db = request.app.state.db

    if message_id:
        # Download from provider (Gmail/IMAP)
        message = db.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")

        account = db.get_account(message.account_id)
        if not account:
            raise HTTPException(status_code=404, detail=f"Account {message.account_id} not found")

        try:
            # Create provider and download attachment
            provider = ProviderFactory.create_from_account(account)
            provider.authenticate()

            attachment_data = provider.get_attachment(message_id, attachment_id)

            # Get filename from list_attachments
            attachments = provider.list_attachments(message_id)
            filename = next(
                (att["filename"] for att in attachments if att["id"] == attachment_id),
                "attachment.bin"
            )
            content_type = next(
                (att["content_type"] for att in attachments if att["id"] == attachment_id),
                "application/octet-stream"
            )

            return Response(
                content=attachment_data,
                media_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            logger.error(f"Failed to download attachment {attachment_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to download attachment")

    else:
        # Download from database (draft attachment)
        attachment = db.get_attachment(attachment_id)
        if not attachment:
            raise HTTPException(status_code=404, detail=f"Attachment {attachment_id} not found")

        return Response(
            content=attachment.data,
            media_type=attachment.content_type,
            headers={"Content-Disposition": f'attachment; filename="{attachment.filename}"'},
        )


@router.delete("/{attachment_id}")
async def delete_attachment(attachment_id: str, request: Request):
    """Delete an attachment (draft attachments only).

    Args:
        attachment_id: Attachment ID
        request: FastAPI request

    Returns:
        Success message

    Raises:
        HTTPException: If attachment not found
    """
    db = request.app.state.db

    deleted = db.delete_attachment(attachment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Attachment {attachment_id} not found")

    return {"status": "deleted", "attachment_id": attachment_id}
