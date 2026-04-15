"""Pydantic models for API request/response validation."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# Response Models


class MessageResponse(BaseModel):
    """Message response model."""

    id: str
    account_id: str
    thread_id: Optional[str] = None
    subject: str
    from_email: str
    to_emails: List[str]
    date: datetime
    snippet: str
    is_unread: bool
    provider_labels: List[str]
    tags: List[str] = []  # From classification
    priority: Optional[str] = None
    todo: bool = False
    can_archive: bool = False
    confidence: Optional[float] = None  # Classification confidence 0.0-1.0
    classified_at: Optional[datetime] = None
    has_attachments: bool = False

    class Config:
        from_attributes = True


class MessagesListResponse(BaseModel):
    """List of messages with pagination."""

    messages: List[MessageResponse]
    total: int
    limit: int
    offset: int


class AccountResponse(BaseModel):
    """Account response model."""

    id: str
    name: str
    email: str
    provider: str
    last_sync: Optional[datetime] = None
    hidden: bool = False

    class Config:
        from_attributes = True


class AccountStatsResponse(BaseModel):
    """Account statistics."""

    account_id: str
    total_messages: int
    unread_messages: int
    classified_messages: int
    classification_rate: float
    last_sync: Optional[datetime] = None


class TagResponse(BaseModel):
    """Tag with count."""

    name: str
    count: int
    percentage: float
    type: str = "ai"  # 'ai' or 'account'


class TagsListResponse(BaseModel):
    """List of tags with counts."""

    tags: List[TagResponse]
    total_classified: int


class AvailableTagResponse(BaseModel):
    """Available tag from taxonomy."""

    name: str
    description: str
    category: str


class AvailableTagsResponse(BaseModel):
    """List of all available tags from taxonomy."""

    tags: List[AvailableTagResponse]


class StatsResponse(BaseModel):
    """Overall system statistics."""

    total_messages: int
    classified_messages: int
    unread_messages: int
    classification_rate: float
    accounts_count: int
    top_tags: List[TagResponse]
    accounts_breakdown: Dict[str, int] = {}  # Map of account_id to message count
    last_sync: Optional[datetime] = None  # Most recent sync across all accounts


class SyncStatusResponse(BaseModel):
    """Current sync status."""

    is_syncing: bool
    current_account: Optional[str] = None
    last_sync: Optional[datetime] = None
    message: str = "Idle"


class SyncResultResponse(BaseModel):
    """Sync operation result."""

    account_id: str
    fetched: int
    classified: int
    labeled: int
    errors: int
    duration: float


class ConfigResponse(BaseModel):
    """AI configuration."""

    enable: bool
    model: str
    endpoint: str
    temperature: float
    tags: List[dict]  # [{name: str, description: str}]


# Request Models


class UpdateTagsRequest(BaseModel):
    """Request to update message tags."""

    tags: List[str] = Field(..., min_length=0, max_length=20)


class MarkReadRequest(BaseModel):
    """Request to mark message as read/unread."""

    is_unread: bool


class TriggerSyncRequest(BaseModel):
    """Request to trigger manual sync."""

    account_id: Optional[str] = None
    max_messages: int = Field(default=100, ge=1, le=1000)


class UpdateConfigRequest(BaseModel):
    """Request to update AI configuration."""

    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    tags: Optional[List[dict]] = None


# WebSocket Models


class WebSocketMessage(BaseModel):
    """WebSocket message."""

    type: str
    data: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Smart Replies Models


class SmartReply(BaseModel):
    """Individual smart reply suggestion."""

    id: str
    text: str


class SmartReplyResponse(BaseModel):
    """Smart reply suggestions response."""

    replies: List[SmartReply]
    generated_at: datetime


# DFSL Feedback Models


class FeedbackEntryResponse(BaseModel):
    """Single feedback entry for DFSL."""

    id: int
    account_id: str
    message_id: Optional[str] = None
    sender_domain: str
    subject_pattern: Optional[str] = None
    original_tags: List[str]
    corrected_tags: List[str]
    context_snippet: Optional[str] = None
    corrected_at: datetime
    used_count: int

    class Config:
        from_attributes = True


class FeedbackListResponse(BaseModel):
    """List of feedback entries."""

    entries: List[FeedbackEntryResponse]
    total: int


class FeedbackStatsResponse(BaseModel):
    """DFSL feedback statistics."""

    total_corrections: int
    total_usage: int
    top_domains: List[Dict[str, int]]


class FeedbackDeleteResponse(BaseModel):
    """Response for feedback deletion."""

    success: bool
    deleted_count: int
    message: str


# Trusted Senders Models


class TrustedSenderCreate(BaseModel):
    """Request to add a trusted sender."""

    account_id: str
    email_or_domain: str
    is_domain: bool = False


class TrustedSenderResponse(BaseModel):
    """Single trusted sender entry."""

    id: int
    account_id: str
    email_or_domain: str
    is_domain: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TrustedSenderListResponse(BaseModel):
    """List of trusted senders."""

    senders: List[TrustedSenderResponse]
    total: int


class TrustedSenderCheckResponse(BaseModel):
    """Response for checking if a sender is trusted."""

    is_trusted: bool
    sender_email: str


# Action tag models


class ActionDefinitionResponse(BaseModel):
    """Available action tag definition."""

    name: str
    description: str
    server: str
    tool: str
    enabled: bool
    available: bool  # Whether the MCP tool is available in gateway


class ActionsListResponse(BaseModel):
    """List of available action definitions."""

    actions: List[ActionDefinitionResponse]


class ActionLogEntryResponse(BaseModel):
    """Action log entry."""

    id: str
    message_id: str
    account_id: str
    action_name: str
    server: str
    tool: str
    status: str
    error: Optional[str] = None
    extracted_data: Optional[dict] = None
    tool_result: Optional[dict] = None
    attempts: int
    processed_at: str


class ActionLogResponse(BaseModel):
    """Paginated action log response."""

    entries: List[ActionLogEntryResponse]
    total: int
