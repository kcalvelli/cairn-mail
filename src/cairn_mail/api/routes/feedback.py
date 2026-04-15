"""API routes for DFSL (Dynamic Few-Shot Learning) feedback management."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from ..models import (
    FeedbackDeleteResponse,
    FeedbackEntryResponse,
    FeedbackListResponse,
    FeedbackStatsResponse,
)
from ...db.models import Feedback

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all DFSL feedback entries.

    Returns user corrections that are used as few-shot examples for classification.

    Args:
        request: FastAPI request
        account_id: Optional account ID filter
        limit: Maximum entries to return
        offset: Pagination offset

    Returns:
        List of feedback entries
    """
    db = request.app.state.db

    try:
        with db.session() as session:
            query = select(Feedback).order_by(Feedback.corrected_at.desc())

            if account_id:
                query = query.where(Feedback.account_id == account_id)

            # Get total count
            count_query = select(Feedback)
            if account_id:
                count_query = count_query.where(Feedback.account_id == account_id)
            total = len(list(session.execute(count_query).scalars().all()))

            # Apply pagination
            query = query.limit(limit).offset(offset)
            entries = list(session.execute(query).scalars().all())

            return FeedbackListResponse(
                entries=[
                    FeedbackEntryResponse(
                        id=fb.id,
                        account_id=fb.account_id,
                        message_id=fb.message_id,
                        sender_domain=fb.sender_domain,
                        subject_pattern=fb.subject_pattern,
                        original_tags=fb.original_tags,
                        corrected_tags=fb.corrected_tags,
                        context_snippet=fb.context_snippet,
                        corrected_at=fb.corrected_at,
                        used_count=fb.used_count,
                    )
                    for fb in entries
                ],
                total=total,
            )

    except Exception as e:
        logger.error(f"Error listing feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account ID"),
):
    """Get DFSL learning statistics.

    Shows how many corrections have been made and how often they're used.

    Args:
        request: FastAPI request
        account_id: Optional account ID filter (if not provided, aggregates all accounts)

    Returns:
        Feedback statistics
    """
    db = request.app.state.db

    try:
        if account_id:
            # Get stats for specific account
            stats = db.get_feedback_stats(account_id)
        else:
            # Aggregate stats across all accounts
            from sqlalchemy import func

            with db.session() as session:
                total = session.query(Feedback).count()
                total_used = session.query(func.sum(Feedback.used_count)).scalar() or 0

                # Top domains across all accounts
                domain_counts = (
                    session.query(Feedback.sender_domain, func.count(Feedback.id))
                    .group_by(Feedback.sender_domain)
                    .order_by(func.count(Feedback.id).desc())
                    .limit(10)
                    .all()
                )

                stats = {
                    "total_corrections": total,
                    "total_usage": total_used,
                    "top_domains": [{"domain": d, "count": c} for d, c in domain_counts],
                }

        return FeedbackStatsResponse(
            total_corrections=stats["total_corrections"],
            total_usage=stats["total_usage"],
            top_domains=stats["top_domains"],
        )

    except Exception as e:
        logger.error(f"Error getting feedback stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{feedback_id}", response_model=FeedbackDeleteResponse)
async def delete_feedback(request: Request, feedback_id: int):
    """Delete a specific feedback entry.

    Removes a correction from the learning history. Future classifications
    will no longer use this example.

    Args:
        request: FastAPI request
        feedback_id: Feedback entry ID to delete

    Returns:
        Deletion status
    """
    db = request.app.state.db

    try:
        with db.session() as session:
            feedback = session.get(Feedback, feedback_id)
            if not feedback:
                raise HTTPException(status_code=404, detail=f"Feedback entry {feedback_id} not found")

            session.delete(feedback)
            session.commit()

            logger.info(f"Deleted feedback entry {feedback_id}")
            return FeedbackDeleteResponse(
                success=True,
                deleted_count=1,
                message=f"Deleted feedback entry {feedback_id}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("", response_model=FeedbackDeleteResponse)
async def reset_all_feedback(
    request: Request,
    account_id: Optional[str] = Query(None, description="Filter by account ID (delete only for this account)"),
):
    """Reset all DFSL learning by deleting all feedback entries.

    This reverts classification behavior to the base model without any
    user preference learning.

    Args:
        request: FastAPI request
        account_id: Optional account ID to reset only that account's feedback

    Returns:
        Deletion status
    """
    db = request.app.state.db

    try:
        with db.session() as session:
            query = session.query(Feedback)
            if account_id:
                query = query.filter(Feedback.account_id == account_id)

            count = query.count()
            query.delete(synchronize_session=False)
            session.commit()

            scope = f"account {account_id}" if account_id else "all accounts"
            logger.info(f"Reset DFSL learning for {scope}: deleted {count} entries")

            return FeedbackDeleteResponse(
                success=True,
                deleted_count=count,
                message=f"Deleted {count} feedback entries for {scope}",
            )

    except Exception as e:
        logger.error(f"Error resetting feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
