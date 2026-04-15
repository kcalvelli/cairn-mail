"""Sync engine for coordinating email fetch, classification, and label updates."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Set

from .action_agent import ActionAgent
from .ai_classifier import AIClassifier, AIConfig
from .db.database import Database
from .db.models import PendingOperation
from .providers.base import BaseEmailProvider, Message

logger = logging.getLogger(__name__)


@dataclass
class NewMessageInfo:
    """Info about a new message for notifications."""

    id: str
    subject: str
    from_email: str
    snippet: str

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "subject": self.subject,
            "from_email": self.from_email,
            "snippet": self.snippet,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""

    account_id: str
    messages_fetched: int
    messages_classified: int
    labels_updated: int
    errors: List[str]
    duration_seconds: float
    new_messages: List[NewMessageInfo] = None
    pending_ops_processed: int = 0
    pending_ops_failed: int = 0
    actions_processed: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    action_modified_messages: List[str] = None
    action_results: List[dict] = None

    def __post_init__(self):
        if self.new_messages is None:
            self.new_messages = []
        if self.action_modified_messages is None:
            self.action_modified_messages = []
        if self.action_results is None:
            self.action_results = []

    def __str__(self) -> str:
        """String representation."""
        return (
            f"SyncResult(account={self.account_id}, "
            f"fetched={self.messages_fetched}, "
            f"classified={self.messages_classified}, "
            f"labels_updated={self.labels_updated}, "
            f"pending_ops={self.pending_ops_processed}/{self.pending_ops_processed + self.pending_ops_failed}, "
            f"actions={self.actions_succeeded}/{self.actions_processed}, "
            f"errors={len(self.errors)}, "
            f"duration={self.duration_seconds:.2f}s)"
        )


class SyncEngine:
    """Orchestrates email sync, AI classification, and label updates."""

    def __init__(
        self,
        provider: BaseEmailProvider,
        database: Database,
        ai_classifier: AIClassifier,
        label_prefix: str = "AI",
        action_agent: Optional[ActionAgent] = None,
    ):
        """Initialize sync engine.

        Args:
            provider: Email provider instance
            database: Database instance
            ai_classifier: AI classifier instance
            label_prefix: Prefix for AI-generated labels (e.g., "AI" -> "AI/Work")
            action_agent: Optional action agent for processing action tags
        """
        self.provider = provider
        self.db = database
        self.ai_classifier = ai_classifier
        self.label_prefix = label_prefix
        self.account_id = provider.account_id
        self.action_agent = action_agent

    def sync(self, max_messages: int = 100) -> SyncResult:
        """Perform a complete sync operation.

        1. Process pending operations queue (user actions waiting to sync)
        2. Fetch new messages from provider
        3. Store messages in database
        4. Classify unclassified messages
        5. Push AI labels back to provider
        6. Process action tags (if action agent is configured)
        7. Update sync timestamp
        8. Clean up old completed operations and action log

        Args:
            max_messages: Maximum messages to fetch in this sync

        Returns:
            SyncResult with statistics
        """
        start_time = datetime.now(timezone.utc)
        errors = []
        messages_fetched = 0
        messages_classified = 0
        labels_updated = 0
        pending_ops_processed = 0
        pending_ops_failed = 0
        actions_processed = 0
        actions_succeeded = 0
        actions_failed = 0
        action_modified_messages: List[str] = []
        action_results: List[dict] = []
        new_messages: List[NewMessageInfo] = []

        logger.info(f"Starting sync for account {self.account_id}")

        try:
            # 1. Process pending operations queue FIRST (user actions take priority)
            pending_ops_processed, pending_ops_failed = self._process_pending_operations()

            # 2. Clean up old completed operations and stale feedback
            self.db.cleanup_completed_operations(older_than_hours=24)
            self.db.cleanup_feedback(max_age_days=90, max_per_account=100)

            # 3. Fetch messages from provider
            last_sync = self.db.get_last_sync_time(self.account_id)
            logger.info(f"Last sync: {last_sync}")

            messages = self.provider.fetch_messages(since=last_sync, max_results=max_messages)
            messages_fetched = len(messages)

            if not messages:
                logger.info("No new messages to process")

            # 4. Store messages in database
            for message in messages:
                try:
                    # Check if message already exists in database
                    existing_message = self.db.get_message(message.id)
                    is_new = existing_message is None

                    # For existing messages, preserve local state
                    # Philosophy: local consistency first, provider sync is best effort
                    if is_new:
                        is_unread = message.is_unread
                        folder = message.folder
                    else:
                        # Preserve local is_unread (user may have marked as read)
                        is_unread = existing_message.is_unread
                        # Preserve local folder (user may have moved to trash)
                        folder = existing_message.folder

                    self.db.create_or_update_message(
                        message_id=message.id,
                        account_id=self.account_id,
                        thread_id=message.thread_id,
                        subject=message.subject,
                        from_email=message.from_email,
                        to_emails=message.to_emails,
                        date=message.date,
                        snippet=message.snippet,
                        is_unread=is_unread,
                        provider_labels=list(message.labels),
                        folder=folder,
                        body_text=message.body_text,
                        body_html=message.body_html,
                        imap_folder=message.imap_folder,
                        has_attachments=message.has_attachments,
                    )

                    # Track new messages for notifications
                    if is_new:
                        new_messages.append(NewMessageInfo(
                            id=message.id,
                            subject=message.subject,
                            from_email=message.from_email,
                            snippet=message.snippet[:100] if message.snippet else "",
                        ))
                except Exception as e:
                    error_msg = f"Failed to store message {message.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            # 5. Classify unclassified inbox messages (no point tagging sent/trash)
            to_classify = [
                msg for msg in messages
                if msg.folder == "inbox" and not self.db.has_classification(msg.id)
            ]
            logger.info(f"Classifying {len(to_classify)} messages")

            for message in to_classify:
                try:
                    classification = self.ai_classifier.classify(
                        message, db=self.db, account_id=self.account_id
                    )

                    # Store classification in database
                    self.db.store_classification(
                        message_id=message.id,
                        tags=classification.tags,
                        priority=classification.priority,
                        todo=classification.todo,
                        can_archive=classification.can_archive,
                        model=self.ai_classifier.config.model,
                        confidence=classification.confidence,
                    )

                    messages_classified += 1

                    # 6. Push labels to provider
                    try:
                        add_labels, remove_labels = self._compute_label_changes(
                            message, classification
                        )

                        if add_labels or remove_labels:
                            # Ensure labels exist
                            self.provider.ensure_labels_exist(add_labels)

                            # Update labels on provider
                            self.provider.update_labels(
                                message.id, add_labels=add_labels, remove_labels=remove_labels
                            )

                            labels_updated += 1
                            logger.debug(
                                f"Updated labels for {message.id}: +{add_labels} -{remove_labels}"
                            )

                    except Exception as e:
                        error_msg = f"Failed to update labels for {message.id}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Failed to classify message {message.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            # 6. Process action tags (if action agent is configured)
            if self.action_agent:
                try:
                    action_stats = self.action_agent.process_actions(
                        account_id=self.account_id,
                    )
                    actions_processed = action_stats.get("processed", 0)
                    actions_succeeded = action_stats.get("succeeded", 0)
                    actions_failed = action_stats.get("failed", 0)
                    action_modified_messages = action_stats.get("modified_messages", [])
                    action_results = action_stats.get("action_results", [])
                except Exception as e:
                    error_msg = f"Action processing failed: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            # 7. Update last sync timestamp
            self.db.update_last_sync(self.account_id, datetime.now(timezone.utc))

            # 8. Clean up old action log entries
            if self.action_agent:
                try:
                    self.db.cleanup_action_log(max_age_days=90)
                except Exception as e:
                    logger.warning(f"Action log cleanup failed: {e}")

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            result = SyncResult(
                account_id=self.account_id,
                messages_fetched=messages_fetched,
                messages_classified=messages_classified,
                labels_updated=labels_updated,
                errors=errors,
                duration_seconds=duration,
                new_messages=new_messages,
                pending_ops_processed=pending_ops_processed,
                pending_ops_failed=pending_ops_failed,
                actions_processed=actions_processed,
                actions_succeeded=actions_succeeded,
                actions_failed=actions_failed,
                action_modified_messages=action_modified_messages,
                action_results=action_results,
            )

            logger.info(f"Sync completed: {result}")
            if new_messages:
                logger.info(f"New messages for notifications: {len(new_messages)}")
            return result

        except Exception as e:
            error_msg = f"Sync failed for account {self.account_id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return SyncResult(
                account_id=self.account_id,
                messages_fetched=messages_fetched,
                messages_classified=messages_classified,
                labels_updated=labels_updated,
                errors=errors,
                duration_seconds=duration,
                pending_ops_processed=pending_ops_processed,
                pending_ops_failed=pending_ops_failed,
                actions_processed=actions_processed,
                actions_succeeded=actions_succeeded,
                actions_failed=actions_failed,
            )

    def _compute_label_changes(
        self, message: Message, classification
    ) -> tuple[Set[str], Set[str]]:
        """Compute which labels to add/remove based on classification.

        Args:
            message: Message being classified
            classification: AI classification result

        Returns:
            Tuple of (labels_to_add, labels_to_remove)
        """
        # Map AI tags to provider labels
        ai_labels = self.provider.map_tags_to_labels(
            classification.tags, label_prefix=self.label_prefix
        )

        # Add priority label if high priority
        if classification.priority == "high":
            ai_labels.add(f"{self.label_prefix}/Priority")

        # Add todo label if action required
        if classification.todo:
            ai_labels.add(f"{self.label_prefix}/ToDo")

        # Current provider labels (filter to only AI labels)
        current_ai_labels = {
            label for label in message.labels if label.startswith(f"{self.label_prefix}/")
        }

        # Compute differences
        labels_to_add = ai_labels - current_ai_labels
        labels_to_remove = current_ai_labels - ai_labels

        # Handle archiving
        if classification.can_archive:
            # Remove inbox label (provider-specific)
            if "INBOX" in message.labels:
                labels_to_remove.add("INBOX")

        return labels_to_add, labels_to_remove

    def _process_pending_operations(self, max_ops: int = 50) -> tuple[int, int]:
        """Process pending operations queue.

        Syncs user-initiated actions (mark read, trash, restore) to the provider.
        This is called at the start of each sync to ensure user actions are
        reflected on the provider as soon as possible.

        Args:
            max_ops: Maximum operations to process in one batch

        Returns:
            Tuple of (processed_count, failed_count)
        """
        processed = 0
        failed = 0

        # Get pending operations for this account
        pending = self.db.get_pending_operations(
            account_id=self.account_id,
            limit=max_ops,
            status="pending",
        )

        if not pending:
            return 0, 0

        logger.info(f"Processing {len(pending)} pending operations for account {self.account_id}")

        for op in pending:
            try:
                # Execute operation against provider
                if op.operation == "mark_read":
                    self.provider.mark_as_read(op.message_id)
                elif op.operation == "mark_unread":
                    self.provider.mark_as_unread(op.message_id)
                elif op.operation == "trash":
                    self.provider.move_to_trash(op.message_id)
                elif op.operation == "restore":
                    self.provider.restore_from_trash(op.message_id)
                elif op.operation == "delete":
                    # Permanent delete: remove from provider, then from local DB
                    self.provider.delete_message(op.message_id, permanent=True)
                    # Delete from local DB - this CASCADE deletes the pending operation too
                    self.db.delete_message(op.message_id)
                    processed += 1
                    logger.info(f"Permanently deleted message {op.message_id} from provider and local DB")
                    continue  # Skip complete_pending_operation - record was cascade deleted
                else:
                    logger.warning(f"Unknown operation type: {op.operation}")
                    continue

                # Mark as completed (for non-delete operations)
                self.db.complete_pending_operation(op.id)
                processed += 1
                logger.debug(f"Completed pending operation: {op.operation} for {op.message_id}")

            except Exception as e:
                # Record failure (will retry up to max_attempts)
                self.db.fail_pending_operation(op.id, str(e))
                failed += 1
                logger.warning(
                    f"Failed to process pending operation {op.operation} "
                    f"for message {op.message_id}: {e}"
                )

        if processed or failed:
            logger.info(
                f"Pending operations: {processed} processed, {failed} failed "
                f"for account {self.account_id}"
            )

        return processed, failed

    def reclassify_all(self, max_messages: Optional[int] = None) -> SyncResult:
        """Reclassify all messages in the database.

        Args:
            max_messages: Maximum messages to reclassify (None for all)

        Returns:
            SyncResult with statistics
        """
        start_time = datetime.now(timezone.utc)
        errors = []
        messages_classified = 0
        labels_updated = 0

        logger.info(f"Starting reclassification for account {self.account_id}")

        # Get action tag names to preserve during reclassification
        action_tag_names = (
            self.action_agent.get_action_tag_names() if self.action_agent else []
        )

        try:
            # Get all messages for this account
            messages = self.db.query_messages(account_id=self.account_id, limit=max_messages or 10000)
            logger.info(f"Reclassifying {len(messages)} messages")

            for db_message in messages:
                try:
                    # Convert database message to Message object for classification
                    message = Message(
                        id=db_message.id,
                        thread_id=db_message.thread_id or "",
                        subject=db_message.subject,
                        from_email=db_message.from_email,
                        to_emails=db_message.to_emails,
                        date=db_message.date,
                        snippet=db_message.snippet,
                        body_text=db_message.body_text,
                        body_html=db_message.body_html,
                        labels=set(db_message.provider_labels),
                        is_unread=db_message.is_unread,
                        folder=db_message.folder,
                    )

                    # Classify (with DFSL support)
                    classification = self.ai_classifier.classify(
                        message, db=self.db, account_id=self.account_id
                    )

                    # Store classification (preserve action tags)
                    self.db.store_classification(
                        message_id=message.id,
                        tags=classification.tags,
                        priority=classification.priority,
                        todo=classification.todo,
                        can_archive=classification.can_archive,
                        model=self.ai_classifier.config.model,
                        confidence=classification.confidence,
                        preserve_tags=action_tag_names or None,
                    )

                    messages_classified += 1

                    # Update labels on provider
                    try:
                        add_labels, remove_labels = self._compute_label_changes(
                            message, classification
                        )

                        if add_labels or remove_labels:
                            self.provider.ensure_labels_exist(add_labels)
                            self.provider.update_labels(
                                message.id, add_labels=add_labels, remove_labels=remove_labels
                            )
                            labels_updated += 1

                    except Exception as e:
                        error_msg = f"Failed to update labels for {message.id}: {e}"
                        logger.error(error_msg)
                        errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Failed to reclassify message {db_message.id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            result = SyncResult(
                account_id=self.account_id,
                messages_fetched=0,
                messages_classified=messages_classified,
                labels_updated=labels_updated,
                errors=errors,
                duration_seconds=duration,
            )

            logger.info(f"Reclassification completed: {result}")
            return result

        except Exception as e:
            error_msg = f"Reclassification failed for account {self.account_id}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return SyncResult(
                account_id=self.account_id,
                messages_fetched=0,
                messages_classified=messages_classified,
                labels_updated=labels_updated,
                errors=errors,
                duration_seconds=duration,
            )
