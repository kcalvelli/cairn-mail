"""Base provider abstraction and data models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Protocol, Set


@dataclass
class Message:
    """Normalized message representation across providers."""

    id: str
    thread_id: str
    subject: str
    from_email: str
    to_emails: List[str]
    date: datetime
    snippet: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    labels: Set[str] = field(default_factory=set)
    is_unread: bool = True
    folder: str = "inbox"
    imap_folder: Optional[str] = None  # Actual IMAP folder name (e.g., "INBOX.Sent")
    has_attachments: bool = False

    def __post_init__(self) -> None:
        """Ensure labels is a set."""
        if isinstance(self.labels, list):
            self.labels = set(self.labels)


@dataclass
class Classification:
    """AI classification result."""

    tags: List[str]
    priority: str  # "high" or "normal"
    todo: bool
    can_archive: bool
    confidence: Optional[float] = None


@dataclass
class ProviderConfig:
    """Base configuration for email providers."""

    account_id: str
    email: str
    credential_file: str


class EmailProvider(Protocol):
    """Protocol defining the interface all email providers must implement."""

    def authenticate(self) -> None:
        """Authenticate with the provider using OAuth2 or credentials."""
        ...

    def fetch_messages(
        self, since: Optional[datetime] = None, max_results: int = 100
    ) -> List[Message]:
        """Fetch new/changed messages since last sync.

        Args:
            since: Only fetch messages newer than this timestamp
            max_results: Maximum number of messages to fetch

        Returns:
            List of Message objects
        """
        ...

    def update_labels(
        self, message_id: str, add_labels: Set[str], remove_labels: Set[str]
    ) -> None:
        """Update labels/categories on a message.

        Args:
            message_id: Provider-specific message ID
            add_labels: Labels to add
            remove_labels: Labels to remove
        """
        ...

    def create_label(self, name: str, color: Optional[str] = None) -> str:
        """Create a label/category if it doesn't exist (idempotent).

        Args:
            name: Label name
            color: Optional color for the label (provider-specific format)

        Returns:
            Label ID
        """
        ...

    def list_labels(self) -> Dict[str, str]:
        """Get all labels/categories.

        Returns:
            Dict mapping label name to label ID
        """
        ...

    def get_label_mapping(self) -> Dict[str, str]:
        """Map AI tag names to provider label IDs.

        Returns:
            Dict mapping AI tag to provider label ID
        """
        ...

    def move_to_trash(self, message_id: str) -> None:
        """Move a message to the provider's trash/deleted folder.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails (network error, auth failure, etc.)
        """
        ...

    def restore_from_trash(self, message_id: str) -> None:
        """Restore a message from trash to its original folder.

        The original folder is retrieved from the database. If not available,
        the message is restored to the default inbox folder.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails or message not found in trash
        """
        ...

    def delete_message(self, message_id: str, permanent: bool = False) -> None:
        """Delete a message from the provider.

        Args:
            message_id: Provider-specific message ID
            permanent: If True, permanently delete. If False, move to trash.

        Raises:
            RuntimeError: If the operation fails
        """
        ...

    def send_message(self, mime_message: bytes, thread_id: Optional[str] = None) -> str:
        """Send a message via the provider.

        Args:
            mime_message: RFC822 MIME message as bytes
            thread_id: Optional thread ID for replies

        Returns:
            Sent message ID

        Raises:
            RuntimeError: If send fails
        """
        ...

    def list_attachments(self, message_id: str) -> List[Dict[str, str]]:
        """List attachments for a message.

        Args:
            message_id: Provider-specific message ID

        Returns:
            List of attachment metadata dicts with keys: id, filename, content_type, size

        Raises:
            RuntimeError: If message not found or fetch fails
        """
        ...

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment data.

        Args:
            message_id: Provider-specific message ID
            attachment_id: Attachment identifier

        Returns:
            Binary attachment data

        Raises:
            RuntimeError: If attachment not found or download fails
        """
        ...

    def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails
        """
        ...

    def mark_as_unread(self, message_id: str) -> None:
        """Mark a message as unread.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails
        """
        ...


class BaseEmailProvider(ABC):
    """Abstract base class for email providers with common functionality."""

    def __init__(self, config: ProviderConfig):
        """Initialize provider with configuration.

        Args:
            config: Provider configuration
        """
        self.config = config
        self.account_id = config.account_id
        self.email = config.email
        self._label_cache: Optional[Dict[str, str]] = None

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the provider."""
        pass

    def release(self) -> None:
        """Release connection back to pool (if applicable).

        This is called after sync completes to return the connection
        to the pool for reuse. Providers that don't use connection
        pooling can leave this as a no-op.
        """
        pass

    def close(self) -> None:
        """Close and dispose of the connection.

        Called when the provider is no longer needed. Should clean up
        any resources and close connections.
        """
        pass

    @abstractmethod
    def fetch_messages(
        self, since: Optional[datetime] = None, max_results: int = 100
    ) -> List[Message]:
        """Fetch messages from provider."""
        pass

    @abstractmethod
    def update_labels(
        self, message_id: str, add_labels: Set[str], remove_labels: Set[str]
    ) -> None:
        """Update labels on a message."""
        pass

    @abstractmethod
    def create_label(self, name: str, color: Optional[str] = None) -> str:
        """Create a label."""
        pass

    @abstractmethod
    def list_labels(self) -> Dict[str, str]:
        """List all labels."""
        pass

    @abstractmethod
    def move_to_trash(self, message_id: str) -> None:
        """Move a message to the provider's trash/deleted folder.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails (network error, auth failure, etc.)
        """
        pass

    @abstractmethod
    def restore_from_trash(self, message_id: str) -> None:
        """Restore a message from trash to its original folder.

        The original folder is retrieved from the database. If not available,
        the message is restored to the default inbox folder.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails or message not found in trash
        """
        pass

    @abstractmethod
    def delete_message(self, message_id: str, permanent: bool = False) -> None:
        """Delete a message from the provider.

        Args:
            message_id: Provider-specific message ID
            permanent: If True, permanently delete. If False, move to trash.

        Raises:
            RuntimeError: If the operation fails
        """
        pass

    @abstractmethod
    def send_message(self, mime_message: bytes, thread_id: Optional[str] = None) -> str:
        """Send a message via the provider.

        Args:
            mime_message: RFC822 MIME message as bytes
            thread_id: Optional thread ID for replies

        Returns:
            Sent message ID

        Raises:
            RuntimeError: If send fails
        """
        pass

    @abstractmethod
    def list_attachments(self, message_id: str) -> List[Dict[str, str]]:
        """List attachments for a message.

        Args:
            message_id: Provider-specific message ID

        Returns:
            List of attachment metadata dicts with keys: id, filename, content_type, size

        Raises:
            RuntimeError: If message not found or fetch fails
        """
        pass

    @abstractmethod
    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment data.

        Args:
            message_id: Provider-specific message ID
            attachment_id: Attachment identifier

        Returns:
            Binary attachment data

        Raises:
            RuntimeError: If attachment not found or download fails
        """
        pass

    @abstractmethod
    def mark_as_read(self, message_id: str) -> None:
        """Mark a message as read.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails
        """
        pass

    @abstractmethod
    def mark_as_unread(self, message_id: str) -> None:
        """Mark a message as unread.

        Args:
            message_id: Provider-specific message ID

        Raises:
            RuntimeError: If the operation fails
        """
        pass

    def get_label_mapping(self) -> Dict[str, str]:
        """Get mapping of AI tags to provider labels.

        Default implementation - can be overridden by subclasses.

        Returns:
            Dict mapping AI tag to provider label ID
        """
        if self._label_cache is None:
            self._label_cache = self.list_labels()
        return self._label_cache

    def map_tags_to_labels(
        self, tags: List[str], label_prefix: str = "AI"
    ) -> Set[str]:
        """Map AI tags to provider-specific label names.

        Args:
            tags: List of AI tags (e.g., ["work", "finance"])
            label_prefix: Prefix for labels (e.g., "AI" -> "AI/Work")

        Returns:
            Set of provider label names
        """
        return {f"{label_prefix}/{tag.capitalize()}" for tag in tags}

    def ensure_labels_exist(
        self, label_names: Set[str], colors: Optional[Dict[str, str]] = None
    ) -> None:
        """Ensure that labels exist, creating them if necessary.

        Args:
            label_names: Set of label names to ensure exist
            colors: Optional mapping of label names to colors
        """
        existing_labels = self.list_labels()
        colors = colors or {}

        for label_name in label_names:
            if label_name not in existing_labels:
                color = colors.get(label_name)
                self.create_label(label_name, color)
                # Invalidate cache
                self._label_cache = None
