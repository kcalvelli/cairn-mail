"""API routes for draft management."""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class DraftCreate(BaseModel):
    """Request model for creating a draft.

    Only account_id is required - partial drafts are allowed.
    """

    account_id: str
    subject: Optional[str] = ""  # Allow empty subject for partial drafts
    to_emails: Optional[List[str]] = []  # Allow empty recipients for partial drafts
    cc_emails: Optional[List[str]] = None
    bcc_emails: Optional[List[str]] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None


class DraftCountResponse(BaseModel):
    """Response model for draft count."""

    count: int


class DraftUpdate(BaseModel):
    """Request model for updating a draft."""

    subject: Optional[str] = None
    to_emails: Optional[List[str]] = None
    cc_emails: Optional[List[str]] = None
    bcc_emails: Optional[List[str]] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None


class DraftResponse(BaseModel):
    """Response model for a draft."""

    id: str
    account_id: str
    subject: str
    to_emails: List[str]
    cc_emails: Optional[List[str]]
    bcc_emails: Optional[List[str]]
    body_text: Optional[str]
    body_html: Optional[str]
    thread_id: Optional[str]
    in_reply_to: Optional[str]
    created_at: str
    updated_at: str


@router.post("", response_model=DraftResponse)
async def create_draft(draft: DraftCreate, request: Request):
    """Create a new draft.

    Args:
        draft: Draft data
        request: FastAPI request

    Returns:
        Created draft
    """
    db = request.app.state.db

    # Generate draft ID
    draft_id = str(uuid.uuid4())

    # Create draft in database
    created_draft = db.create_draft(
        draft_id=draft_id,
        account_id=draft.account_id,
        subject=draft.subject,
        to_emails=draft.to_emails,
        cc_emails=draft.cc_emails,
        bcc_emails=draft.bcc_emails,
        body_text=draft.body_text,
        body_html=draft.body_html,
        thread_id=draft.thread_id,
        in_reply_to=draft.in_reply_to,
    )

    return DraftResponse(
        id=created_draft.id,
        account_id=created_draft.account_id,
        subject=created_draft.subject,
        to_emails=created_draft.to_emails,
        cc_emails=created_draft.cc_emails,
        bcc_emails=created_draft.bcc_emails,
        body_text=created_draft.body_text,
        body_html=created_draft.body_html,
        thread_id=created_draft.thread_id,
        in_reply_to=created_draft.in_reply_to,
        created_at=created_draft.created_at.isoformat(),
        updated_at=created_draft.updated_at.isoformat(),
    )


@router.get("/count", response_model=DraftCountResponse)
async def get_draft_count(request: Request, account_id: Optional[str] = None):
    """Get the count of drafts.

    Args:
        request: FastAPI request
        account_id: Optional account ID filter

    Returns:
        Draft count
    """
    db = request.app.state.db
    drafts = db.list_drafts(account_id=account_id)
    return DraftCountResponse(count=len(drafts))


@router.get("", response_model=List[DraftResponse])
async def list_drafts(request: Request, account_id: Optional[str] = None):
    """List all drafts, optionally filtered by account.

    Args:
        request: FastAPI request
        account_id: Optional account ID filter

    Returns:
        List of drafts
    """
    db = request.app.state.db

    drafts = db.list_drafts(account_id=account_id)

    return [
        DraftResponse(
            id=draft.id,
            account_id=draft.account_id,
            subject=draft.subject,
            to_emails=draft.to_emails,
            cc_emails=draft.cc_emails,
            bcc_emails=draft.bcc_emails,
            body_text=draft.body_text,
            body_html=draft.body_html,
            thread_id=draft.thread_id,
            in_reply_to=draft.in_reply_to,
            created_at=draft.created_at.isoformat(),
            updated_at=draft.updated_at.isoformat(),
        )
        for draft in drafts
    ]


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(draft_id: str, request: Request):
    """Get a specific draft by ID.

    Args:
        draft_id: Draft ID
        request: FastAPI request

    Returns:
        Draft data

    Raises:
        HTTPException: If draft not found
    """
    db = request.app.state.db

    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    return DraftResponse(
        id=draft.id,
        account_id=draft.account_id,
        subject=draft.subject,
        to_emails=draft.to_emails,
        cc_emails=draft.cc_emails,
        bcc_emails=draft.bcc_emails,
        body_text=draft.body_text,
        body_html=draft.body_html,
        thread_id=draft.thread_id,
        in_reply_to=draft.in_reply_to,
        created_at=draft.created_at.isoformat(),
        updated_at=draft.updated_at.isoformat(),
    )


@router.patch("/{draft_id}", response_model=DraftResponse)
async def update_draft(draft_id: str, updates: DraftUpdate, request: Request):
    """Update an existing draft.

    Args:
        draft_id: Draft ID
        updates: Draft updates
        request: FastAPI request

    Returns:
        Updated draft

    Raises:
        HTTPException: If draft not found
    """
    db = request.app.state.db

    updated_draft = db.update_draft(
        draft_id=draft_id,
        subject=updates.subject,
        to_emails=updates.to_emails,
        cc_emails=updates.cc_emails,
        bcc_emails=updates.bcc_emails,
        body_text=updates.body_text,
        body_html=updates.body_html,
    )

    if not updated_draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    return DraftResponse(
        id=updated_draft.id,
        account_id=updated_draft.account_id,
        subject=updated_draft.subject,
        to_emails=updated_draft.to_emails,
        cc_emails=updated_draft.cc_emails,
        bcc_emails=updated_draft.bcc_emails,
        body_text=updated_draft.body_text,
        body_html=updated_draft.body_html,
        thread_id=updated_draft.thread_id,
        in_reply_to=updated_draft.in_reply_to,
        created_at=updated_draft.created_at.isoformat(),
        updated_at=updated_draft.updated_at.isoformat(),
    )


@router.delete("/{draft_id}")
async def delete_draft(draft_id: str, request: Request):
    """Delete a draft.

    Args:
        draft_id: Draft ID
        request: FastAPI request

    Returns:
        Success message

    Raises:
        HTTPException: If draft not found
    """
    db = request.app.state.db

    deleted = db.delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")

    return {"status": "deleted", "draft_id": draft_id}
