"""SQLAlchemy models for axios-ai-mail database."""

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class PendingOperation(Base):
    """Queue of operations pending sync to email provider.

    Philosophy: Local database is source of truth. Provider sync is best-effort.
    Operations are queued here and processed during sync to avoid blocking the UI.

    Supported operations:
        - mark_read: Mark message as read on provider
        - mark_unread: Mark message as unread on provider
        - trash: Move message to trash on provider
        - restore: Restore message from trash on provider
        - delete: Permanently delete message from provider (also deletes from local DB)
    """

    __tablename__ = "pending_operations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # mark_read, mark_unread, trash, restore, delete
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, completed, failed

    # Relationships
    account: Mapped["Account"] = relationship()
    message: Mapped["Message"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<PendingOperation(id={self.id!r}, operation={self.operation!r}, "
            f"message_id={self.message_id!r}, status={self.status!r})>"
        )


class Account(Base):
    """Email account configuration."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # gmail, imap, outlook
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consecutive_empty_syncs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    settings: Mapped[Dict] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    messages: Mapped[List["Message"]] = relationship(back_populates="account", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Account(id={self.id!r}, email={self.email!r}, provider={self.provider!r})>"


class Message(Base):
    """Email message metadata."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    to_emails: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    is_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_labels: Mapped[List[str]] = mapped_column(JSON, nullable=False, default=list)
    folder: Mapped[str] = mapped_column(String(100), nullable=False, default="inbox")
    original_folder: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    imap_folder: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Actual IMAP folder name (e.g., "INBOX.Sent")
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="messages")
    classification: Mapped[Optional["Classification"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", uselist=False
    )
    feedback_entries: Mapped[List["Feedback"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id!r}, subject={self.subject!r})>"


class Classification(Base):
    """AI classification for a message."""

    __tablename__ = "classifications"

    message_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    tags: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)  # high, normal
    todo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_archive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Relationships
    message: Mapped["Message"] = relationship(back_populates="classification")

    def __repr__(self) -> str:
        return f"<Classification(message_id={self.message_id!r}, tags={self.tags!r})>"


class Feedback(Base):
    """User feedback for classification corrections (DFSL - Dynamic Few-Shot Learning).

    Stores user tag corrections to use as few-shot examples in future classifications.
    When the AI classifier processes new emails, it retrieves relevant corrections
    based on sender domain and recency to improve accuracy.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        String(255), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    sender_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject_pattern: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    original_tags: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    corrected_tags: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    context_snippet: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    corrected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    account: Mapped["Account"] = relationship()
    message: Mapped[Optional["Message"]] = relationship(back_populates="feedback_entries")

    def __repr__(self) -> str:
        return f"<Feedback(id={self.id}, sender_domain={self.sender_domain!r}, corrected_tags={self.corrected_tags!r})>"


class Draft(Base):
    """Email draft for composition."""

    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    in_reply_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    to_emails: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    cc_emails: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    bcc_emails: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account: Mapped["Account"] = relationship()
    attachments: Mapped[List["Attachment"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        foreign_keys="[Attachment.draft_id]"
    )

    def __repr__(self) -> str:
        return f"<Draft(id={self.id!r}, subject={self.subject!r})>"


class Attachment(Base):
    """Email attachment for drafts and messages."""

    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    draft_id: Mapped[Optional[str]] = mapped_column(
        String(255), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=True
    )
    message_id: Mapped[Optional[str]] = mapped_column(
        String(255), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    draft: Mapped[Optional["Draft"]] = relationship(back_populates="attachments", foreign_keys=[draft_id])
    message: Mapped[Optional["Message"]] = relationship(foreign_keys=[message_id])

    def __repr__(self) -> str:
        return f"<Attachment(id={self.id!r}, filename={self.filename!r}, size={self.size})>"


class ActionLog(Base):
    """Audit log of action tag executions.

    Records every action tag processing attempt with extracted data,
    tool results, and status for debugging and status tracking.
    """

    __tablename__ = "action_log"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_name: Mapped[str] = mapped_column(String(100), nullable=False)
    server: Mapped[str] = mapped_column(String(100), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    extracted_data: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    tool_result: Mapped[Optional[Dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, failed, skipped
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )

    # Relationships
    account: Mapped["Account"] = relationship()
    message: Mapped["Message"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<ActionLog(id={self.id!r}, action={self.action_name!r}, "
            f"status={self.status!r}, message_id={self.message_id!r})>"
        )


class PushSubscription(Base):
    """Web Push notification subscription.

    Stores browser push subscription details so the backend can send
    notifications even when the PWA is closed.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<PushSubscription(id={self.id}, endpoint={self.endpoint[:50]!r}...)>"


class TrustedSender(Base):
    """Trusted senders for auto-loading remote images.

    When a sender is trusted, their emails will automatically load remote images
    instead of blocking them by default.
    """

    __tablename__ = "trusted_senders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_or_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    is_domain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    account: Mapped["Account"] = relationship()

    def __repr__(self) -> str:
        return f"<TrustedSender(id={self.id}, email_or_domain={self.email_or_domain!r}, is_domain={self.is_domain})>"
