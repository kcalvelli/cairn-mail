"""API routes for maintenance operations."""

import asyncio
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel

from ...providers.base import Message as ProviderMessage

logger = logging.getLogger(__name__)


def db_message_to_provider_message(db_msg) -> ProviderMessage:
    """Convert database Message to provider Message for classifier."""
    return ProviderMessage(
        id=db_msg.id,
        thread_id=db_msg.thread_id or db_msg.id,
        subject=db_msg.subject,
        from_email=db_msg.from_email,
        to_emails=db_msg.to_emails or [],
        date=db_msg.date,
        snippet=db_msg.snippet or "",
        body_text=db_msg.body_text,
        body_html=db_msg.body_html,
        labels=set(db_msg.provider_labels or []),
        is_unread=db_msg.is_unread,
        folder=db_msg.folder or "inbox",
    )

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


class JobStatus(str, Enum):
    """Job status enum."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class JobState:
    """In-memory job state tracker."""

    def __init__(self, job_id: str, operation: str, total: int = 0):
        self.job_id = job_id
        self.operation = operation
        self.status = JobStatus.PENDING
        self.progress = 0
        self.total = total
        self.errors: List[str] = []
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.cancel_requested = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "job_id": self.job_id,
            "operation": self.operation,
            "status": self.status.value,
            "progress": self.progress,
            "total": self.total,
            "errors": self.errors,
            "error_count": len(self.errors),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# In-memory job storage (not persistent across restarts)
_jobs: Dict[str, JobState] = {}


class ReclassifyRequest(BaseModel):
    """Request model for reclassify operations."""

    override_user_edits: bool = False


class ReclassifyResponse(BaseModel):
    """Response model for reclassify operations."""

    job_id: str
    operation: str
    status: str
    total: int


class JobStatusResponse(BaseModel):
    """Response model for job status."""

    job_id: str
    operation: str
    status: str
    progress: int
    total: int
    errors: List[str]
    error_count: int
    started_at: Optional[str]
    completed_at: Optional[str]


class StatsRefreshResponse(BaseModel):
    """Response model for stats refresh."""

    success: bool
    message: str


class TagConfigResponse(BaseModel):
    """Response model for tag configuration."""

    tags: List[Dict]
    use_default_tags: bool
    excluded_tags: List[str]
    total_count: int
    default_count: int
    custom_count: int


def get_job(job_id: str) -> JobState:
    """Get job by ID or raise 404."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _jobs[job_id]


async def run_reclassify(
    job: JobState,
    db,
    classifier,
    unclassified_only: bool = False,
    override_user_edits: bool = False,
):
    """Background task to run reclassification."""
    job.status = JobStatus.RUNNING
    job.started_at = datetime.now()

    try:
        # Get messages to reclassify
        if unclassified_only:
            messages = db.get_unclassified_messages()
        else:
            messages = db.list_messages(limit=10000)  # Get all messages

        job.total = len(messages)
        batch_size = 50

        for i in range(0, len(messages), batch_size):
            # Check for cancellation
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now()
                return

            batch = messages[i : i + batch_size]

            for message in batch:
                try:
                    # Skip user-edited messages unless override requested
                    # (detected by presence of feedback entries)
                    if not override_user_edits and db.has_user_feedback(message.id):
                        job.progress += 1
                        continue

                    # Convert database message to provider message for classifier
                    provider_msg = db_message_to_provider_message(message)

                    # Reclassify the message with DFSL support
                    # (classifier.classify is synchronous, run in thread)
                    result = await asyncio.to_thread(
                        classifier.classify,
                        provider_msg,
                        db=db,
                        account_id=message.account_id,
                    )

                    if result:
                        # Update classification in database
                        db.store_classification(
                            message_id=message.id,
                            tags=result.tags,
                            priority=result.priority,
                            todo=result.todo,
                            can_archive=result.can_archive,
                            model=classifier.config.model,
                            confidence=result.confidence,
                        )

                    job.progress += 1

                except Exception as e:
                    error_msg = f"Message {message.id}: {str(e)}"
                    job.errors.append(error_msg)
                    logger.error(f"Reclassify error: {error_msg}")
                    job.progress += 1

            # Small delay between batches to avoid overwhelming the system
            await asyncio.sleep(0.1)

        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.errors.append(f"Job failed: {str(e)}")
        job.completed_at = datetime.now()
        logger.error(f"Reclassify job failed: {e}")


@router.post("/reclassify-all", response_model=ReclassifyResponse)
async def reclassify_all(
    request: Request,
    body: ReclassifyRequest,
    background_tasks: BackgroundTasks,
):
    """Start a job to reclassify all messages.

    Args:
        request: FastAPI request
        body: Request body with options
        background_tasks: FastAPI background tasks

    Returns:
        Job information
    """
    db = request.app.state.db
    classifier = getattr(request.app.state, "classifier", None)

    if not classifier:
        raise HTTPException(status_code=503, detail="Classifier not available")

    # Get total message count
    total = db.get_message_count()

    # Create job
    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, operation="reclassify-all", total=total)
    _jobs[job_id] = job

    # Start background task
    background_tasks.add_task(
        run_reclassify,
        job,
        db,
        classifier,
        unclassified_only=False,
        override_user_edits=body.override_user_edits,
    )

    return ReclassifyResponse(
        job_id=job_id,
        operation="reclassify-all",
        status=job.status.value,
        total=total,
    )


@router.post("/reclassify-unclassified", response_model=ReclassifyResponse)
async def reclassify_unclassified(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Start a job to reclassify only unclassified messages.

    Args:
        request: FastAPI request
        background_tasks: FastAPI background tasks

    Returns:
        Job information
    """
    db = request.app.state.db
    classifier = getattr(request.app.state, "classifier", None)

    if not classifier:
        raise HTTPException(status_code=503, detail="Classifier not available")

    # Get unclassified message count
    unclassified = db.get_unclassified_messages()
    total = len(unclassified)

    # Create job
    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id, operation="reclassify-unclassified", total=total)
    _jobs[job_id] = job

    # Start background task
    background_tasks.add_task(
        run_reclassify,
        job,
        db,
        classifier,
        unclassified_only=True,
        override_user_edits=False,
    )

    return ReclassifyResponse(
        job_id=job_id,
        operation="reclassify-unclassified",
        status=job.status.value,
        total=total,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Get the status of a maintenance job.

    Args:
        job_id: Job ID

    Returns:
        Job status information
    """
    job = get_job(job_id)
    return JobStatusResponse(**job.to_dict())


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a running maintenance job.

    Args:
        job_id: Job ID

    Returns:
        Cancellation status
    """
    job = get_job(job_id)

    if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job.status.value}",
        )

    job.cancel_requested = True
    return {"status": "cancel_requested", "job_id": job_id}


@router.post("/refresh-stats", response_model=StatsRefreshResponse)
async def refresh_stats(request: Request):
    """Refresh tag statistics by recalculating counts.

    Args:
        request: FastAPI request

    Returns:
        Refresh status
    """
    db = request.app.state.db

    try:
        # Recalculate tag counts
        db.refresh_tag_stats()
        return StatsRefreshResponse(
            success=True,
            message="Statistics refreshed successfully",
        )
    except Exception as e:
        logger.error(f"Failed to refresh stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh stats: {str(e)}")


class FeedbackCleanupResponse(BaseModel):
    """Response model for feedback cleanup."""

    success: bool
    removed_count: int
    message: str


@router.post("/cleanup-feedback", response_model=FeedbackCleanupResponse)
async def cleanup_feedback(
    request: Request,
    max_age_days: int = 90,
    max_per_account: int = 100,
):
    """Manually trigger DFSL feedback cleanup.

    Removes old feedback entries to prevent unbounded growth.

    Args:
        request: FastAPI request
        max_age_days: Remove entries older than this many days
        max_per_account: Maximum entries to keep per account

    Returns:
        Cleanup status
    """
    db = request.app.state.db

    try:
        removed = db.cleanup_feedback(max_age_days=max_age_days, max_per_account=max_per_account)
        return FeedbackCleanupResponse(
            success=True,
            removed_count=removed,
            message=f"Removed {removed} old feedback entries",
        )
    except Exception as e:
        logger.error(f"Failed to cleanup feedback: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup feedback: {str(e)}")


@router.get("/tag-config", response_model=TagConfigResponse)
async def get_tag_config(request: Request):
    """Get the current tag configuration.

    Returns merged tag list with source information.

    Args:
        request: FastAPI request

    Returns:
        Tag configuration details
    """
    from ...config import ConfigLoader, get_tag_names, DEFAULT_TAGS

    config = ConfigLoader.load_config()
    merged_tags = ConfigLoader.get_merged_tags(config)

    # Get AI config
    ai_config = config.get("ai", {}) if config else {}
    use_default_tags = ai_config.get("useDefaultTags", True)
    excluded_tags = ai_config.get("excludeTags", [])
    custom_tags = ai_config.get("tags", [])

    # Get default tag names for comparison
    default_tag_names = get_tag_names(DEFAULT_TAGS)
    custom_tag_names = get_tag_names(custom_tags)

    # Add source flag to each tag
    tags_with_source = []
    for tag in merged_tags:
        tag_copy = dict(tag)
        if tag["name"] in custom_tag_names:
            tag_copy["source"] = "custom"
        elif tag["name"] in default_tag_names:
            tag_copy["source"] = "default"
        else:
            tag_copy["source"] = "unknown"
        tags_with_source.append(tag_copy)

    # Count tags by source
    default_count = sum(1 for t in tags_with_source if t["source"] == "default")
    custom_count = sum(1 for t in tags_with_source if t["source"] == "custom")

    return TagConfigResponse(
        tags=tags_with_source,
        use_default_tags=use_default_tags,
        excluded_tags=excluded_tags,
        total_count=len(tags_with_source),
        default_count=default_count,
        custom_count=custom_count,
    )
