"""Gmail API provider implementation."""

import email.utils
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ...credentials import Credentials as CredLoader, CredentialError
from ..base import BaseEmailProvider, Message, ProviderConfig
from ..registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class GmailConfig(ProviderConfig):
    """Gmail-specific configuration."""

    label_prefix: str = "AI"
    label_colors: Dict[str, str] = None
    enable_webhooks: bool = False

    def __post_init__(self) -> None:
        """Initialize default label colors."""
        if self.label_colors is None:
            self.label_colors = {
                "AI/Work": "#4285f4",  # Blue
                "AI/Finance": "#0f9d58",  # Green
                "AI/Todo": "#f4b400",  # Orange
                "AI/Priority": "#db4437",  # Red
                "AI/Personal": "#ab47bc",  # Purple
                "AI/Dev": "#00acc1",  # Cyan
            }


class GmailProvider(BaseEmailProvider):
    """Gmail API provider implementation."""

    # Gmail API scopes
    # Note: Full mail access is required for permanent deletion
    SCOPES = [
        "https://mail.google.com/",  # Full access (required for permanent delete)
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]

    def __init__(self, config: GmailConfig):
        """Initialize Gmail provider.

        Args:
            config: Gmail configuration
        """
        super().__init__(config)
        self.config: GmailConfig = config
        self.service = None
        self.creds: Optional[Credentials] = None

    def authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2."""
        try:
            # Load OAuth token from credential file
            token_data = CredLoader.load_oauth_token(self.config.credential_file)

            # Create credentials object with expiry if available
            # This allows proactive refresh instead of waiting for 401
            self.creds = Credentials(
                token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=token_data["client_id"],
                client_secret=token_data["client_secret"],
                scopes=self.SCOPES,
                expiry=token_data.get("expiry"),  # datetime or None
            )

            # Refresh token if expired or will expire within 5 minutes
            # The google-auth library checks creds.expired but we also do a
            # proactive check with a 5-minute buffer to avoid 401s
            needs_refresh = False
            if self.creds.expired:
                needs_refresh = True
                logger.debug(f"Token expired for {self.email}")
            elif self.creds.expiry:
                # Check if token expires within 5 minutes
                buffer = timedelta(minutes=5)
                if self.creds.expiry <= datetime.now(timezone.utc) + buffer:
                    needs_refresh = True
                    logger.debug(f"Token for {self.email} expires soon, refreshing proactively")

            if needs_refresh and self.creds.refresh_token:
                logger.info(f"Refreshing OAuth token for {self.email}")
                self.creds.refresh(Request())

                # Save updated token with new expiry
                try:
                    updated_token = {
                        "access_token": self.creds.token,
                        "refresh_token": self.creds.refresh_token,
                        "client_id": token_data["client_id"],
                        "client_secret": token_data["client_secret"],
                        "expiry": self.creds.expiry,  # datetime object
                    }
                    CredLoader.save_oauth_token(self.config.credential_file, updated_token)
                    logger.debug(f"Saved refreshed token with expiry {self.creds.expiry}")
                except Exception as e:
                    logger.warning(f"Could not save refreshed token: {e}")

            # Build Gmail service
            self.service = build("gmail", "v1", credentials=self.creds)
            logger.info(f"Successfully authenticated with Gmail for {self.email}")

        except CredentialError as e:
            logger.error(f"Credential error for {self.email}: {e}")
            raise
        except Exception as e:
            logger.error(f"Authentication failed for {self.email}: {e}")
            raise

    def fetch_messages(
        self, since: Optional[datetime] = None, max_results: int = 100
    ) -> List[Message]:
        """Fetch messages from Gmail.

        Args:
            since: Only fetch messages newer than this timestamp
            max_results: Maximum number of messages to fetch

        Returns:
            List of Message objects
        """
        if not self.service:
            self.authenticate()

        try:
            messages = []

            # Build query - fetch from all mail (inbox, sent, trash)
            # Use "in:all" to search everywhere, then exclude drafts and spam
            query = "in:all -in:draft -in:spam"
            if since:
                # Gmail uses YYYY/MM/DD format
                date_str = since.strftime("%Y/%m/%d")
                query += f" after:{date_str}"

            # Fetch message list
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            message_items = results.get("messages", [])
            logger.info(f"Fetched {len(message_items)} messages from Gmail")

            # Fetch full message details
            for item in message_items:
                msg_id = item["id"]
                try:
                    msg_detail = (
                        self.service.users()
                        .messages()
                        .get(userId="me", id=msg_id, format="full")
                        .execute()
                    )
                    message = self._parse_gmail_message(msg_detail)
                    messages.append(message)
                except HttpError as e:
                    logger.warning(f"Failed to fetch message {msg_id}: {e}")
                    continue

            return messages

        except HttpError as e:
            logger.error(f"Gmail API error while fetching messages: {e}")
            raise

    def _parse_gmail_message(self, msg_detail: Dict) -> Message:
        """Parse Gmail API message into normalized Message object.

        Args:
            msg_detail: Gmail API message object

        Returns:
            Normalized Message object
        """
        headers = {h["name"]: h["value"] for h in msg_detail["payload"]["headers"]}

        # Extract email body (text and HTML)
        import base64
        body_text = None
        body_html = None

        has_attachments = False

        def extract_body_parts(payload):
            """Recursively extract body text and HTML from payload."""
            nonlocal body_text, body_html, has_attachments

            mime_type = payload.get("mimeType", "")

            # If this is a multipart, recurse into parts
            if "parts" in payload:
                for part in payload["parts"]:
                    extract_body_parts(part)
            else:
                # This is a leaf part - check if it's body content
                body_data = payload.get("body", {}).get("data", "")

                # Check for attachments (parts with filename or attachmentId)
                if payload.get("filename") or payload.get("body", {}).get("attachmentId"):
                    has_attachments = True
                    return

                if body_data:
                    try:
                        decoded = base64.urlsafe_b64decode(body_data).decode("utf-8")
                        if mime_type == "text/plain" and not body_text:
                            body_text = decoded
                        elif mime_type == "text/html" and not body_html:
                            body_html = decoded
                    except Exception:
                        pass

        extract_body_parts(msg_detail["payload"])

        # Extract labels
        label_ids = msg_detail.get("labelIds", [])
        labels = set(label_ids)  # Will map to human-readable names later

        # Detect folder from Gmail labels
        folder = "inbox"  # Default
        if "SENT" in label_ids:
            folder = "sent"
        elif "TRASH" in label_ids:
            folder = "trash"
        elif "DRAFT" in label_ids:
            folder = "drafts"
        elif "SPAM" in label_ids:
            folder = "spam"
        # INBOX is default

        # Parse date from email Date header
        # Convert to local time and store as naive datetime for correct display
        # (JS interprets naive datetime strings as local time)
        date_str = headers.get("Date", "")
        try:
            date = email.utils.parsedate_to_datetime(date_str)
            # Convert to local time and make naive for storage
            date = date.astimezone().replace(tzinfo=None)
        except Exception:
            # Fallback to internalDate if Date header parsing fails
            date = datetime.fromtimestamp(int(msg_detail["internalDate"]) / 1000)

        return Message(
            id=msg_detail["id"],
            thread_id=msg_detail["threadId"],
            subject=headers.get("Subject", "(No Subject)"),
            from_email=headers.get("From", ""),
            to_emails=[headers.get("To", "")],
            date=date,
            snippet=msg_detail.get("snippet", ""),
            body_text=body_text,
            body_html=body_html,
            labels=labels,
            is_unread="UNREAD" in label_ids,
            folder=folder,
            has_attachments=has_attachments,
        )

    def update_labels(
        self, message_id: str, add_labels: Set[str], remove_labels: Set[str]
    ) -> None:
        """Update labels on a Gmail message.

        Args:
            message_id: Gmail message ID
            add_labels: Label names to add
            remove_labels: Label names to remove
        """
        if not self.service:
            self.authenticate()

        try:
            # Map label names to IDs
            label_mapping = self.list_labels()

            add_label_ids = [
                label_mapping[name] for name in add_labels if name in label_mapping
            ]
            remove_label_ids = [
                label_mapping[name] for name in remove_labels if name in label_mapping
            ]

            if not add_label_ids and not remove_label_ids:
                logger.debug(f"No label changes for message {message_id}")
                return

            # Update labels
            body = {
                "addLabelIds": add_label_ids,
                "removeLabelIds": remove_label_ids,
            }

            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

            logger.info(
                f"Updated labels on message {message_id}: "
                f"+{len(add_label_ids)} -{len(remove_label_ids)}"
            )

        except HttpError as e:
            logger.error(f"Failed to update labels on message {message_id}: {e}")
            raise

    def create_label(self, name: str, color: Optional[str] = None) -> str:
        """Create a Gmail label if it doesn't exist.

        Args:
            name: Label name
            color: Optional hex color code

        Returns:
            Label ID
        """
        if not self.service:
            self.authenticate()

        try:
            # Check if label already exists
            existing_labels = self.list_labels()
            if name in existing_labels:
                logger.debug(f"Label '{name}' already exists")
                return existing_labels[name]

            # Create label
            label_body = {
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }

            if color:
                # Gmail color format is different - this is simplified
                label_body["color"] = {"backgroundColor": color}

            result = self.service.users().labels().create(userId="me", body=label_body).execute()
            label_id = result["id"]

            logger.info(f"Created Gmail label: {name} (ID: {label_id})")

            # Invalidate cache
            self._label_cache = None

            return label_id

        except HttpError as e:
            logger.error(f"Failed to create label '{name}': {e}")
            raise

    def list_labels(self) -> Dict[str, str]:
        """Get all Gmail labels.

        Returns:
            Dict mapping label name to label ID
        """
        if not self.service:
            self.authenticate()

        try:
            results = self.service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])

            label_mapping = {label["name"]: label["id"] for label in labels}
            logger.debug(f"Fetched {len(label_mapping)} labels from Gmail")

            return label_mapping

        except HttpError as e:
            logger.error(f"Failed to list labels: {e}")
            raise

    def move_to_trash(self, message_id: str) -> None:
        """Move a Gmail message to trash by adding TRASH label.

        Args:
            message_id: Gmail message ID

        Raises:
            RuntimeError: If the operation fails
        """
        if not self.service:
            self.authenticate()

        try:
            # Add TRASH label, remove INBOX label (Gmail-specific behavior)
            body = {
                "addLabelIds": ["TRASH"],
                "removeLabelIds": ["INBOX"],
            }

            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

            logger.info(f"Moved Gmail message {message_id} to trash")

        except HttpError as e:
            error_msg = f"Failed to move message {message_id} to trash: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def restore_from_trash(self, message_id: str) -> None:
        """Restore a Gmail message from trash to inbox.

        Args:
            message_id: Gmail message ID

        Raises:
            RuntimeError: If the operation fails
        """
        if not self.service:
            self.authenticate()

        try:
            # Remove TRASH label, add INBOX label
            # Note: In future, we could query database for original_folder
            # and restore to SENT or other folders accordingly
            body = {
                "addLabelIds": ["INBOX"],
                "removeLabelIds": ["TRASH"],
            }

            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

            logger.info(f"Restored Gmail message {message_id} from trash")

        except HttpError as e:
            error_msg = f"Failed to restore message {message_id} from trash: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def delete_message(self, message_id: str, permanent: bool = False) -> None:
        """Delete a Gmail message.

        Args:
            message_id: Gmail message ID
            permanent: If True, permanently delete. If False, move to trash.

        Raises:
            RuntimeError: If the operation fails
        """
        if not self.service:
            self.authenticate()

        if not permanent:
            # Soft delete - move to trash
            self.move_to_trash(message_id)
            return

        try:
            # Permanent delete using Gmail API
            self.service.users().messages().delete(
                userId="me", id=message_id
            ).execute()

            logger.info(f"Permanently deleted Gmail message {message_id}")

        except HttpError as e:
            if e.resp.status == 404:
                error_msg = f"Message {message_id} not found"
            else:
                error_msg = f"Failed to permanently delete message {message_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def send_message(self, mime_message: bytes, thread_id: Optional[str] = None) -> str:
        """Send a message via Gmail API.

        Args:
            mime_message: RFC822 MIME message as bytes
            thread_id: Optional thread ID for replies

        Returns:
            Sent message ID

        Raises:
            RuntimeError: If send fails or quota exceeded
        """
        import base64

        if not self.service:
            self.authenticate()

        try:
            # Validate size (Gmail limit is 25MB)
            size_mb = len(mime_message) / (1024 * 1024)
            if size_mb > 25:
                raise RuntimeError(f"Message exceeds 25MB limit ({size_mb:.2f}MB)")

            # Encode message as base64 URL-safe
            encoded_message = base64.urlsafe_b64encode(mime_message).decode("utf-8")

            # Build request body
            body = {"raw": encoded_message}
            if thread_id:
                body["threadId"] = thread_id

            # Send via Gmail API
            result = self.service.users().messages().send(
                userId="me", body=body
            ).execute()

            message_id = result["id"]
            logger.info(f"Sent Gmail message {message_id}")
            return message_id

        except HttpError as e:
            if e.resp.status == 429:
                error_msg = "Send quota exceeded"
            elif e.resp.status == 413:
                error_msg = f"Message too large ({size_mb:.2f}MB)"
            else:
                error_msg = f"Failed to send message: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def list_attachments(self, message_id: str) -> List[Dict[str, str]]:
        """List attachments for a Gmail message.

        Args:
            message_id: Gmail message ID

        Returns:
            List of attachment metadata dicts

        Raises:
            RuntimeError: If message not found or fetch fails
        """
        if not self.service:
            self.authenticate()

        try:
            # Fetch message with payload
            message = self.service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()

            attachments = []
            payload = message.get("payload", {})

            # Recursively find all parts with filenames
            def extract_attachments(part):
                if "filename" in part and part["filename"]:
                    attachment_id = part["body"].get("attachmentId")
                    if attachment_id:
                        # Headers is a list of {name, value} dicts, not a dict
                        headers = {h["name"]: h["value"] for h in part.get("headers", [])}
                        content_disposition = headers.get("Content-Disposition", "")
                        # Get Content-ID for inline images (used for cid: references)
                        content_id = headers.get("Content-ID", "")
                        # Strip angle brackets if present: <image001.jpg@...> -> image001.jpg@...
                        if content_id.startswith("<") and content_id.endswith(">"):
                            content_id = content_id[1:-1]

                        attachments.append({
                            "id": attachment_id,
                            "filename": part["filename"],
                            "content_type": part.get("mimeType", "application/octet-stream"),
                            "size": str(part["body"].get("size", 0)),
                            "is_inline": content_disposition.startswith("inline"),
                            "content_id": content_id,
                        })

                # Recurse into multipart parts
                if "parts" in part:
                    for subpart in part["parts"]:
                        extract_attachments(subpart)

            extract_attachments(payload)

            logger.debug(f"Found {len(attachments)} attachments in message {message_id}")
            return attachments

        except HttpError as e:
            if e.resp.status == 404:
                error_msg = f"Message {message_id} not found"
            else:
                error_msg = f"Failed to list attachments for {message_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment data from Gmail.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID from list_attachments

        Returns:
            Binary attachment data

        Raises:
            RuntimeError: If attachment not found or download fails
        """
        import base64

        if not self.service:
            self.authenticate()

        try:
            # Download attachment via Gmail API
            attachment = self.service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute()

            # Decode base64 data
            data = base64.urlsafe_b64decode(attachment["data"])

            logger.debug(f"Downloaded attachment {attachment_id} ({len(data)} bytes)")
            return data

        except HttpError as e:
            if e.resp.status == 404:
                error_msg = f"Attachment {attachment_id} not found"
            else:
                error_msg = f"Failed to download attachment {attachment_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def mark_as_read(self, message_id: str) -> None:
        """Mark a Gmail message as read by removing the UNREAD label.

        Args:
            message_id: Gmail message ID

        Raises:
            RuntimeError: If the operation fails
        """
        if not self.service:
            self.authenticate()

        try:
            # Remove UNREAD label to mark as read
            body = {
                "removeLabelIds": ["UNREAD"],
            }

            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

            logger.info(f"Marked Gmail message {message_id} as read")

        except HttpError as e:
            error_msg = f"Failed to mark message {message_id} as read: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def mark_as_unread(self, message_id: str) -> None:
        """Mark a Gmail message as unread by adding the UNREAD label.

        Args:
            message_id: Gmail message ID

        Raises:
            RuntimeError: If the operation fails
        """
        if not self.service:
            self.authenticate()

        try:
            # Add UNREAD label to mark as unread
            body = {
                "addLabelIds": ["UNREAD"],
            }

            self.service.users().messages().modify(
                userId="me", id=message_id, body=body
            ).execute()

            logger.info(f"Marked Gmail message {message_id} as unread")

        except HttpError as e:
            error_msg = f"Failed to mark message {message_id} as unread: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)


# Register Gmail provider
ProviderRegistry.register("gmail", GmailProvider)
