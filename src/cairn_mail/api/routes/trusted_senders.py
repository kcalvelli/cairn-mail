"""API routes for trusted senders management."""

import logging

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    TrustedSenderCreate,
    TrustedSenderResponse,
    TrustedSenderListResponse,
    TrustedSenderCheckResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/trusted-senders", response_model=TrustedSenderResponse)
async def add_trusted_sender(request: Request, data: TrustedSenderCreate):
    """Add a trusted sender for auto-loading remote images.

    When a sender is trusted, their emails will automatically load remote images
    without requiring the user to click "Load images".
    """
    db = request.app.state.db

    try:
        trusted = db.add_trusted_sender(
            account_id=data.account_id,
            email_or_domain=data.email_or_domain,
            is_domain=data.is_domain,
        )
        return TrustedSenderResponse.model_validate(trusted)
    except Exception as e:
        logger.error(f"Error adding trusted sender: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trusted-senders", response_model=TrustedSenderListResponse)
async def list_trusted_senders(request: Request, account_id: str):
    """List all trusted senders for an account."""
    db = request.app.state.db

    try:
        senders = db.get_trusted_senders(account_id)
        return TrustedSenderListResponse(
            senders=[TrustedSenderResponse.model_validate(s) for s in senders],
            total=len(senders),
        )
    except Exception as e:
        logger.error(f"Error listing trusted senders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trusted-senders/{sender_id}")
async def remove_trusted_sender(request: Request, sender_id: int):
    """Remove a trusted sender."""
    db = request.app.state.db

    try:
        removed = db.remove_trusted_sender(sender_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Trusted sender not found")
        return {"success": True, "message": "Trusted sender removed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing trusted sender: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trusted-senders/check", response_model=TrustedSenderCheckResponse)
async def check_trusted_sender(request: Request, account_id: str, sender_email: str):
    """Check if a sender is trusted for an account.

    This endpoint is used by the frontend to determine whether to auto-load
    remote images for a given sender.
    """
    db = request.app.state.db

    try:
        is_trusted = db.is_sender_trusted(account_id, sender_email)
        return TrustedSenderCheckResponse(
            is_trusted=is_trusted,
            sender_email=sender_email,
        )
    except Exception as e:
        logger.error(f"Error checking trusted sender: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
