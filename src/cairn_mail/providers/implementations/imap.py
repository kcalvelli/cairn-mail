"""IMAP email provider with KEYWORD extension support."""

import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Dict, List, Optional, Set

from ..base import BaseEmailProvider, Message, ProviderConfig
from ..connection_pool import get_connection_pool
from ...credentials import Credentials

logger = logging.getLogger(__name__)


@dataclass
class IMAPConfig(ProviderConfig):
    """IMAP-specific configuration."""

    host: str
    port: int = 993
    use_ssl: bool = True
    folder: str = "INBOX"
    keyword_prefix: str = "$"  # Prefix for IMAP keywords (e.g., $work, $finance)

    # SMTP settings for sending
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_username: Optional[str] = None
    smtp_password_file: Optional[str] = None


class IMAPProvider(BaseEmailProvider):
    """IMAP email provider with KEYWORD extension support for tag synchronization."""

    def __init__(self, config: IMAPConfig):
        super().__init__(config)
        self.connection: Optional[imaplib.IMAP4_SSL] = None
        self._supports_keywords: Optional[bool] = None
        self._current_folder: Optional[str] = None
        self._folder_mapping: Optional[Dict[str, str]] = None  # Cache discovered folder mapping
        self._using_pool: bool = False  # Track if we got connection from pool

    def _create_connection(self) -> imaplib.IMAP4_SSL:
        """Create a new IMAP connection (used by pool)."""
        logger.info(f"Authenticating IMAP: {self.config.email}@{self.config.host}")

        # Load password from credential file
        password = Credentials.load_password(self.config.credential_file)

        # Connect to IMAP server (timeout prevents indefinite hang on flaky servers)
        if self.config.use_ssl:
            conn = imaplib.IMAP4_SSL(self.config.host, self.config.port, timeout=30)
        else:
            conn = imaplib.IMAP4(self.config.host, self.config.port, timeout=30)

        # Login
        conn.login(self.config.email, password)
        logger.info(f"IMAP authentication successful for {self.config.email}")

        return conn

    def authenticate(self) -> None:
        """Authenticate with IMAP server using connection pool."""
        pool = get_connection_pool()

        # Get or create connection from pool
        self.connection = pool.get_connection(
            account_id=self.config.account_id,
            create_fn=self._create_connection,
        )
        self._using_pool = True

        # Check for KEYWORD capability (only on first connect or reconnect)
        if self._supports_keywords is None:
            typ, capabilities = self.connection.capability()
            if typ == "OK":
                capabilities_str = capabilities[0].decode("utf-8", errors="ignore")
                self._supports_keywords = "KEYWORD" in capabilities_str
                logger.info(
                    f"IMAP KEYWORD extension: {'supported' if self._supports_keywords else 'not supported'}"
                )

    def release(self) -> None:
        """Release connection back to pool (keep alive for reuse)."""
        if self._using_pool and self.connection:
            pool = get_connection_pool()
            pool.release_connection(self.config.account_id)
            logger.debug(f"Released IMAP connection for {self.config.account_id} to pool")
        self.connection = None
        self._using_pool = False

    def close(self) -> None:
        """Close connection (remove from pool)."""
        if self._using_pool:
            pool = get_connection_pool()
            pool.close_connection(self.config.account_id)
            logger.debug(f"Closed IMAP connection for {self.config.account_id}")
        elif self.connection:
            try:
                self.connection.logout()
            except Exception:
                pass
        self.connection = None
        self._using_pool = False
        # Clear folder cache on close
        self._folder_mapping = None

    def _parse_message_id(self, message_id: str) -> tuple[str, str]:
        """
        Parse message ID to extract IMAP folder and UID.

        Message ID format: account_id:folder:uid
        Example: calvelli_dev:INBOX.Sent:123

        Args:
            message_id: Full message ID

        Returns:
            Tuple of (folder, uid)
        """
        parts = message_id.split(":", 2)
        if len(parts) == 3:
            # New format: account_id:folder:uid
            return parts[1], parts[2]
        elif len(parts) == 2:
            # Old format: account_id:uid (assume INBOX for backwards compatibility)
            logger.warning(f"Message ID in old format (missing folder): {message_id}")
            return "INBOX", parts[1]
        else:
            raise ValueError(f"Invalid message ID format: {message_id}")

    def _ensure_folder_mapping(self) -> Dict[str, str]:
        """
        Ensure folder mapping is cached and return it.

        Returns:
            Dictionary mapping logical names to actual folder names
        """
        if self._folder_mapping is None:
            available_folders = self.list_folders()
            self._folder_mapping = self._discover_folder_mapping(available_folders)
        return self._folder_mapping

    def fetch_body(self, message_id: str) -> tuple[Optional[str], Optional[str]]:
        """
        Fetch full body (text and HTML) for a specific message.

        Useful for lazy loading message bodies on demand.

        Args:
            message_id: Message ID (format: account_id:folder:uid)

        Returns:
            Tuple of (body_text, body_html)
        """
        if not self.connection:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        try:
            # Select the correct folder
            if not self._select_folder(folder):
                logger.error(f"Failed to select folder {folder} for message {message_id}")
                return None, None

            # Fetch message
            typ, msg_data = self.connection.uid("FETCH", uid, "(RFC822)")

            if typ != "OK" or not msg_data or not msg_data[0]:
                logger.warning(f"Failed to fetch body for message {uid} in {folder}")
                return None, None

            # Parse email
            raw_email = msg_data[0][1]
            email_message = email.message_from_bytes(raw_email)

            # Extract bodies
            body_text, body_html = self._extract_body(email_message)
            return body_text, body_html

        except Exception as e:
            logger.error(f"Error fetching body for message {uid} in {folder}: {e}")
            return None, None

    def list_folders(self) -> List[str]:
        """
        List all available IMAP folders.

        Returns:
            List of folder names
        """
        if not self.connection:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        try:
            typ, folders_data = self.connection.list()
            if typ != "OK":
                logger.error("IMAP LIST command failed")
                return []

            folders = []
            for folder_info in folders_data:
                if not folder_info:
                    continue

                # Parse IMAP LIST response
                # Standard format: (\Flags) "delimiter" "folder_name"
                # But some servers use: (\Flags) "/" folder_name (no quotes)
                # Or: (\Flags) NIL folder_name
                folder_str = folder_info.decode("utf-8", errors="ignore")
                logger.debug(f"Raw folder line: {folder_str}")

                folder_name = self._parse_list_response(folder_str)
                if folder_name:
                    folders.append(folder_name)
                else:
                    logger.warning(f"Failed to parse folder from: {folder_str}")

            logger.info(f"Found {len(folders)} folders: {folders}")
            return folders

        except Exception as e:
            logger.error(f"Failed to list folders: {e}")
            return []

    def _parse_list_response(self, list_line: str) -> Optional[str]:
        """
        Parse IMAP LIST response line to extract folder name.

        IMAP LIST response formats:
        - (\Flags) "delimiter" "folder_name"       (standard, quoted)
        - (\Flags) "/" folder_name                  (unquoted folder)
        - (\Flags) NIL folder_name                  (no delimiter)
        - (\Flags) "." INBOX.Sent                   (hierarchical, mixed)

        Args:
            list_line: Raw IMAP LIST response line

        Returns:
            Folder name or None if parsing failed
        """
        # Strategy 1: Match last quoted string (most common)
        # Example: '(\HasNoChildren) "/" "INBOX.Sent"'
        match = re.search(r'"([^"]+)"$', list_line)
        if match:
            return match.group(1)

        # Strategy 2: Match everything after delimiter (quoted or NIL)
        # Example: '(\HasNoChildren) "/" INBOX.Sent'
        # Example: '(\HasNoChildren) NIL INBOX'
        match = re.search(r'\)\s+(?:"[^"]*"|NIL)\s+(.+)$', list_line)
        if match:
            folder_name = match.group(1).strip().strip('"\'')
            return folder_name

        # Strategy 3: Split and take last component
        # Last resort for non-standard formats
        parts = list_line.split()
        if len(parts) >= 3:
            # Skip flags (first part) and delimiter (second part)
            # Take everything after as folder name
            folder_name = " ".join(parts[2:]).strip().strip('"\'')
            if folder_name:
                logger.debug(f"Fallback parsing used for: {list_line}")
                return folder_name

        return None

    def _discover_folder_mapping(self, available_folders: List[str]) -> Dict[str, str]:
        """
        Discover which actual IMAP folders map to logical folders.

        Maps logical folder names (inbox, sent, trash) to actual IMAP folder names.

        Args:
            available_folders: List of actual IMAP folder names

        Returns:
            Dictionary mapping logical names to actual folder names
        """
        mapping = {}

        # INBOX always exists and is standard
        if "INBOX" in available_folders:
            mapping["inbox"] = "INBOX"

        # Search for Sent folder (various common names)
        sent_patterns = [
            r"^INBOX\.Sent$",
            r"^Sent$",
            r"^Sent Items$",
            r"^Sent Mail$",
            r"^Sent Messages$",
            r"\[Gmail\]/Sent Mail",
        ]
        for folder in available_folders:
            for pattern in sent_patterns:
                if re.match(pattern, folder, re.IGNORECASE):
                    mapping["sent"] = folder
                    break
            if "sent" in mapping:
                break

        # Search for Trash folder (various common names)
        trash_patterns = [
            r"^INBOX\.Trash$",
            r"^Trash$",
            r"^Deleted Items$",
            r"^Deleted Messages$",
            r"^Deleted$",
            r"\[Gmail\]/Trash",
        ]
        for folder in available_folders:
            for pattern in trash_patterns:
                if re.match(pattern, folder, re.IGNORECASE):
                    mapping["trash"] = folder
                    break
            if "trash" in mapping:
                break

        logger.info(f"Discovered folder mapping: {mapping}")
        return mapping

    def _select_folder(self, folder: str) -> bool:
        """
        Select a specific IMAP folder.

        Args:
            folder: Folder name to select

        Returns:
            True if successful, False otherwise
        """
        if not self.connection:
            raise RuntimeError("Not authenticated")

        try:
            # Only select if we're not already in this folder
            if self._current_folder != folder:
                typ, data = self.connection.select(folder)
                if typ != "OK":
                    logger.error(f"Failed to select folder: {folder}")
                    return False
                self._current_folder = folder
                logger.debug(f"Selected folder: {folder}")
            return True

        except Exception as e:
            logger.error(f"Error selecting folder {folder}: {e}")
            return False

    def _normalize_folder_name(self, imap_folder: str) -> str:
        """
        Normalize IMAP folder name to logical folder name.

        Maps common IMAP folder names to standard logical names:
        - INBOX -> inbox
        - Sent/Sent Items/Sent Mail/INBOX.Sent -> sent
        - Drafts/INBOX.Drafts -> drafts
        - Trash/Deleted Items/INBOX.Trash -> trash
        - Archive/All Mail -> archive

        Args:
            imap_folder: IMAP folder name

        Returns:
            Normalized logical folder name
        """
        # Case-insensitive matching with regex patterns
        folder_lower = imap_folder.lower()

        # INBOX patterns
        if re.match(r"^inbox$", folder_lower):
            return "inbox"

        # Sent patterns (including hierarchical like INBOX.Sent)
        if re.match(r"^(inbox\.)?sent", folder_lower) or folder_lower in ("sent items", "sent mail", "sent messages"):
            return "sent"

        # Drafts patterns
        if re.match(r"^(inbox\.)?drafts?$", folder_lower):
            return "drafts"

        # Trash/Deleted patterns (including hierarchical like INBOX.Trash)
        if re.match(r"^(inbox\.)?trash$", folder_lower) or folder_lower in ("deleted items", "deleted messages", "deleted"):
            return "trash"

        # Archive patterns
        if folder_lower in ("archive", "all mail"):
            return "archive"

        # Keep original for custom folders
        logger.debug(f"No normalization for folder: {imap_folder}, using as-is")
        return imap_folder

    def fetch_messages(
        self,
        since: Optional[datetime] = None,
        max_results: int = 100,
        folder: Optional[str] = None,
    ) -> List[Message]:
        """
        Fetch messages via IMAP SEARCH.

        Args:
            since: Only fetch messages after this date
            max_results: Maximum number of messages to fetch
            folder: Folder to fetch from. If None, fetches from all common folders (INBOX, Sent, Trash)

        Returns:
            List of normalized Message objects
        """
        if not self.connection:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        # If specific folder requested, fetch from that folder only
        if folder:
            return self._fetch_from_folder(folder, since, max_results)

        # Otherwise, fetch from multiple common folders (like Gmail's "in:all")
        logger.info("Fetching messages from all folders (INBOX, Sent, Trash)")

        # Get available folders and discover mapping
        available_folders = self.list_folders()
        if not available_folders:
            logger.warning("No folders found on IMAP server")
            return []

        folder_mapping = self._discover_folder_mapping(available_folders)

        # Build list of actual folder names to fetch from
        folders_to_fetch = []
        for logical_name in ["inbox", "sent", "trash"]:
            if logical_name in folder_mapping:
                folders_to_fetch.append(folder_mapping[logical_name])

        logger.info(f"Fetching from folders: {folders_to_fetch}")

        # Fetch from each folder and combine results
        all_messages = []
        per_folder_limit = max(10, max_results // len(folders_to_fetch)) if folders_to_fetch else max_results

        for folder_name in folders_to_fetch:
            try:
                messages = self._fetch_from_folder(folder_name, since, per_folder_limit)
                all_messages.extend(messages)
                logger.info(f"Fetched {len(messages)} messages from {folder_name}")
            except Exception as e:
                logger.error(f"Failed to fetch from folder {folder_name}: {e}")
                continue

        # Sort by date (most recent first) and limit total results
        all_messages.sort(key=lambda m: m.date, reverse=True)
        if len(all_messages) > max_results:
            all_messages = all_messages[:max_results]

        logger.info(f"Total fetched: {len(all_messages)} messages across {len(folders_to_fetch)} folders")
        return all_messages

    def _fetch_from_folder(
        self,
        folder: str,
        since: Optional[datetime] = None,
        max_results: int = 100,
    ) -> List[Message]:
        """
        Fetch messages from a specific IMAP folder.

        Args:
            folder: IMAP folder name
            since: Only fetch messages after this date
            max_results: Maximum number of messages to fetch

        Returns:
            List of normalized Message objects
        """
        # Select the folder
        if not self._select_folder(folder):
            logger.error(f"Failed to select folder {folder}, skipping fetch")
            return []

        logger.debug(f"Fetching messages from IMAP folder '{folder}' (max: {max_results})")

        # Build IMAP search query
        if since:
            # IMAP date format: DD-Mon-YYYY (e.g., "01-Jan-2024")
            date_str = since.strftime("%d-%b-%Y")
            search_criteria = f"SINCE {date_str}"
        else:
            search_criteria = "ALL"

        # Search for message UIDs (use UID SEARCH to get stable UIDs, not sequence numbers)
        typ, msg_ids_data = self.connection.uid("SEARCH", None, search_criteria)
        if typ != "OK":
            logger.error("IMAP UID SEARCH failed")
            return []

        msg_ids = msg_ids_data[0].split()

        # Limit results (take most recent)
        if len(msg_ids) > max_results:
            msg_ids = msg_ids[-max_results:]

        logger.debug(f"Found {len(msg_ids)} messages in {folder}")

        messages = []
        for msg_id in msg_ids:
            try:
                # Fetch message using UID (RFC822 = full message, FLAGS = keywords/flags)
                typ, msg_data = self.connection.uid("FETCH", msg_id, "(RFC822 FLAGS)")

                if typ != "OK" or not msg_data or not msg_data[0]:
                    logger.warning(f"Failed to fetch message {msg_id}")
                    continue

                # Parse message data
                raw_email = msg_data[0][1]
                email_message = email.message_from_bytes(raw_email)

                # Extract flags from response
                flags_str = msg_data[0][0].decode("utf-8", errors="ignore")
                flags = self._parse_flags(flags_str)

                # Parse into normalized Message object
                message = self._parse_message(msg_id.decode(), email_message, flags, folder)
                messages.append(message)

            except Exception as e:
                logger.error(f"Error parsing message {msg_id}: {e}")
                continue

        return messages

    def mark_as_read(self, message_id: str) -> None:
        """
        Mark a message as read by setting the \Seen flag.

        Args:
            message_id: Message ID (format: account_id:folder:uid)
        """
        if not self.connection:
            raise RuntimeError("Not authenticated")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        try:
            # Select the correct folder
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            typ, data = self.connection.uid("STORE", uid, "+FLAGS", "\\Seen")
            if typ != "OK":
                raise RuntimeError(f"IMAP UID STORE failed: {data}")
            logger.debug(f"Marked message UID {uid} in {folder} as read")

        except Exception as e:
            logger.error(f"Failed to mark message {uid} in {folder} as read: {e}")
            raise

    def mark_as_unread(self, message_id: str) -> None:
        """
        Mark a message as unread by removing the \Seen flag.

        Args:
            message_id: Message ID (format: account_id:folder:uid)
        """
        if not self.connection:
            raise RuntimeError("Not authenticated")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        try:
            # Select the correct folder
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            typ, data = self.connection.uid("STORE", uid, "-FLAGS", "\\Seen")
            if typ != "OK":
                raise RuntimeError(f"IMAP UID STORE failed: {data}")
            logger.debug(f"Marked message UID {uid} in {folder} as unread")

        except Exception as e:
            logger.error(f"Failed to mark message {uid} in {folder} as unread: {e}")
            raise

    def delete_message(self, message_id: str, permanent: bool = False) -> None:
        """
        Delete a message by moving to Trash or permanently deleting.

        Args:
            message_id: Message ID (format: account_id:folder:uid)
            permanent: If True, permanently delete. If False, move to Trash folder.
        """
        if not self.connection:
            raise RuntimeError("Not authenticated")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        try:
            # Select the correct folder first
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            if permanent:
                # Permanent delete: mark as deleted and expunge
                typ, data = self.connection.uid("STORE", uid, "+FLAGS", "\\Deleted")
                if typ != "OK":
                    raise RuntimeError(f"IMAP UID STORE failed: {data}")

                # Expunge to permanently remove deleted messages
                self.connection.expunge()
                logger.info(f"Permanently deleted message UID {uid} from {folder}")

            else:
                # Move to Trash folder using discovered folder mapping
                folder_mapping = self._ensure_folder_mapping()
                trash_folder = folder_mapping.get("trash")

                if not trash_folder:
                    # If no trash folder found, fall back to permanent delete
                    logger.warning("No Trash folder found, performing permanent delete")
                    self.delete_message(message_id, permanent=True)
                    return

                # Copy message to Trash folder using UID
                typ, data = self.connection.uid("COPY", uid, trash_folder)
                if typ != "OK":
                    raise RuntimeError(f"IMAP UID COPY to {trash_folder} failed: {data}")

                # Mark original as deleted
                typ, data = self.connection.uid("STORE", uid, "+FLAGS", "\\Deleted")
                if typ != "OK":
                    raise RuntimeError(f"IMAP UID STORE failed: {data}")

                # Expunge to remove from current folder
                self.connection.expunge()
                logger.info(f"Moved message UID {uid} from {folder} to {trash_folder}")

        except Exception as e:
            logger.error(f"Failed to delete message {uid} from {folder}: {e}")
            raise

    def move_to_trash(self, message_id: str) -> None:
        """Move a message to the trash folder.

        This is a convenience wrapper around delete_message(permanent=False).

        Args:
            message_id: Message ID (format: account_id:folder:uid)

        Raises:
            RuntimeError: If the operation fails
        """
        self.delete_message(message_id, permanent=False)

    def restore_from_trash(self, message_id: str) -> None:
        """Restore a message from Trash to its original folder.

        Args:
            message_id: Message ID (format: account_id:folder:uid)
                       Should be in Trash folder

        Raises:
            RuntimeError: If the operation fails or folders don't exist
        """
        if not self.connection:
            raise RuntimeError("Not authenticated")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        # Get folder mapping
        folder_mapping = self._ensure_folder_mapping()
        trash_folder = folder_mapping.get("trash")

        if not trash_folder:
            raise RuntimeError("No Trash folder found on server")

        # For restore, we need to know the original folder
        # This should be stored in the database - default to INBOX for now
        # TODO: Query database for Message.original_folder
        original_folder = folder_mapping.get("inbox", "INBOX")

        try:
            # Select Trash folder
            if not self._select_folder(trash_folder):
                raise RuntimeError(f"Failed to select folder {trash_folder}")

            # Copy message to original folder using UID
            typ, data = self.connection.uid("COPY", uid, original_folder)
            if typ != "OK":
                raise RuntimeError(f"IMAP UID COPY to {original_folder} failed: {data}")

            # Mark message in Trash as deleted
            typ, data = self.connection.uid("STORE", uid, "+FLAGS", "\\Deleted")
            if typ != "OK":
                raise RuntimeError(f"IMAP UID STORE failed: {data}")

            # Expunge to remove from Trash
            self.connection.expunge()
            logger.info(f"Restored message UID {uid} from {trash_folder} to {original_folder}")

        except Exception as e:
            logger.error(f"Failed to restore message {uid} from trash: {e}")
            raise

    def update_labels(
        self, message_id: str, add_labels: Set[str], remove_labels: Set[str]
    ) -> None:
        """
        Update IMAP keywords for a message.

        Args:
            message_id: Message ID (format: account_id:folder:uid)
            add_labels: Labels to add
            remove_labels: Labels to remove
        """
        if not self._supports_keywords:
            logger.debug(
                "IMAP KEYWORD extension not supported - running in read-only mode"
            )
            return

        if not self.connection:
            raise RuntimeError("Not authenticated")

        # Parse message ID to extract folder and UID
        folder, uid = self._parse_message_id(message_id)

        try:
            # Select the correct folder
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            # Add keywords using UID
            if add_labels:
                keywords = " ".join(
                    f"{self.config.keyword_prefix}{label}" for label in add_labels
                )
                self.connection.uid("STORE", uid, "+FLAGS", f"({keywords})")
                logger.debug(f"Added keywords to message UID {uid} in {folder}: {keywords}")

            # Remove keywords using UID
            if remove_labels:
                keywords = " ".join(
                    f"{self.config.keyword_prefix}{label}" for label in remove_labels
                )
                self.connection.uid("STORE", uid, "-FLAGS", f"({keywords})")
                logger.debug(f"Removed keywords from message UID {uid} in {folder}: {keywords}")

        except Exception as e:
            logger.error(f"Failed to update labels for message {uid} in {folder}: {e}")
            raise

    def create_label(self, name: str, color: Optional[str] = None) -> str:
        """
        IMAP doesn't require label creation (keywords are ad-hoc).

        Args:
            name: Label name
            color: Ignored for IMAP

        Returns:
            Keyword name with prefix
        """
        return f"{self.config.keyword_prefix}{name}"

    def list_labels(self) -> Dict[str, str]:
        """
        List all keywords in use.

        Note: IMAP doesn't have a built-in way to list all keywords.
        This returns an empty dict; keywords are discovered during message fetch.

        Returns:
            Empty dict (keywords are discovered dynamically)
        """
        return {}

    def get_label_mapping(self) -> Dict[str, str]:
        """
        Map tag names to IMAP keywords.

        For IMAP, this is a simple 1:1 mapping with prefix.

        Returns:
            Empty dict (not needed for IMAP simple mapping)
        """
        return {}

    def _parse_message(
        self, msg_id: str, email_message, flags: Set[str], imap_folder: str
    ) -> Message:
        """
        Parse IMAP message into normalized Message object.

        Args:
            msg_id: IMAP UID
            email_message: Parsed email.message object
            flags: Set of IMAP flags/keywords
            imap_folder: IMAP folder name the message was fetched from

        Returns:
            Normalized Message object
        """
        # Decode subject
        subject = self._decode_header(email_message.get("Subject", "(No Subject)"))

        # Get from/to
        from_email = self._decode_header(email_message.get("From", ""))
        to_header = email_message.get("To", "")
        to_emails = [addr.strip() for addr in to_header.split(",")]

        # Get date - convert to local time for correct display
        # (JS interprets naive datetime strings as local time)
        date_str = email_message.get("Date", "")
        try:
            date = email.utils.parsedate_to_datetime(date_str)
            # Convert to local time and make naive for storage
            date = date.astimezone().replace(tzinfo=None)
        except Exception:
            date = datetime.now()

        # Get body text and HTML
        body_text, body_html = self._extract_body(email_message)

        # Check for attachments
        has_attachments = self._check_for_attachments(email_message)

        # Extract snippet (first 200 chars)
        snippet = (body_text[:200] + "...") if len(body_text) > 200 else body_text

        # Check unread status (\Seen flag)
        is_unread = "\\Seen" not in flags

        # Extract keywords (AI tags)
        keywords = [
            f.replace(self.config.keyword_prefix, "")
            for f in flags
            if f.startswith(self.config.keyword_prefix)
        ]

        # Get thread ID from Message-ID header
        thread_id = email_message.get("Message-ID", f"thread-{msg_id}")

        # Normalize folder name to logical name
        logical_folder = self._normalize_folder_name(imap_folder)

        return Message(
            id=f"{self.config.account_id}:{imap_folder}:{msg_id}",  # Include folder in message ID
            thread_id=thread_id,
            subject=subject,
            from_email=from_email,
            to_emails=to_emails,
            date=date,
            snippet=snippet,
            body_text=body_text,
            body_html=body_html,
            labels=keywords,
            is_unread=is_unread,
            folder=logical_folder,
            imap_folder=imap_folder,  # Store actual IMAP folder name
            has_attachments=has_attachments,
        )

    def _decode_header(self, header: str) -> str:
        """
        Decode MIME-encoded email headers.

        Args:
            header: Raw header string

        Returns:
            Decoded string
        """
        if not header:
            return ""

        decoded_parts = decode_header(header)
        decoded_str = ""

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_str += part.decode(encoding or "utf-8", errors="ignore")
                except Exception:
                    decoded_str += part.decode("utf-8", errors="ignore")
            else:
                decoded_str += str(part)

        return decoded_str.strip()

    def _extract_body(self, email_message) -> tuple[str, Optional[str]]:
        """
        Extract plain text and HTML body from email message.

        Args:
            email_message: Parsed email.message object

        Returns:
            Tuple of (body_text, body_html)
        """
        body_text = ""
        body_html = None

        if email_message.is_multipart():
            # Extract from multipart message
            for part in email_message.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))

                # Skip attachments
                if "attachment" in disposition:
                    continue

                # Extract text/plain
                if content_type == "text/plain" and not body_text:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Try different encodings
                            for encoding in ["utf-8", "iso-8859-1", "windows-1252"]:
                                try:
                                    body_text = payload.decode(encoding)
                                    break
                                except (UnicodeDecodeError, AttributeError):
                                    continue
                            else:
                                body_text = payload.decode("utf-8", errors="ignore")
                    except Exception as e:
                        logger.warning(f"Failed to decode text/plain part: {e}")
                        continue

                # Extract text/html
                if content_type == "text/html" and not body_html:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # Try different encodings
                            for encoding in ["utf-8", "iso-8859-1", "windows-1252"]:
                                try:
                                    body_html = payload.decode(encoding)
                                    break
                                except (UnicodeDecodeError, AttributeError):
                                    continue
                            else:
                                body_html = payload.decode("utf-8", errors="ignore")
                    except Exception as e:
                        logger.warning(f"Failed to decode text/html part: {e}")
                        continue
        else:
            # Non-multipart message
            try:
                payload = email_message.get_payload(decode=True)
                if payload:
                    content_type = email_message.get_content_type()
                    # Try different encodings
                    for encoding in ["utf-8", "iso-8859-1", "windows-1252"]:
                        try:
                            decoded = payload.decode(encoding)
                            break
                        except (UnicodeDecodeError, AttributeError):
                            continue
                    else:
                        decoded = payload.decode("utf-8", errors="ignore")

                    if content_type == "text/html":
                        body_html = decoded
                    else:
                        body_text = decoded
            except Exception as e:
                logger.warning(f"Failed to decode message body: {e}")

        # If no plain text but have HTML, create plain text version
        if not body_text and body_html:
            # Simple HTML stripping (basic, not perfect)
            body_text = re.sub(r"<[^>]+>", "", body_html)

        return body_text.strip() if body_text else "", body_html

    def _parse_flags(self, flags_str: str) -> Set[str]:
        """
        Parse IMAP FLAGS response.

        Args:
            flags_str: FLAGS response string (e.g., "1 (FLAGS (\\Seen $work $priority))")

        Returns:
            Set of flags/keywords
        """
        # Example: "1 (FLAGS (\\Seen $work $priority))"
        match = re.search(r"\(FLAGS \((.*?)\)\)", flags_str)
        if match:
            flags_part = match.group(1)
            return set(flags_part.split())
        return set()

    def _check_for_attachments(self, email_message) -> bool:
        """
        Check if an email has attachments.

        Args:
            email_message: Parsed email.message object

        Returns:
            True if message has attachments, False otherwise
        """
        if not email_message.is_multipart():
            return False

        for part in email_message.walk():
            # Skip multipart containers
            if part.get_content_maintype() == "multipart":
                continue

            # Check for filename or attachment disposition
            filename = part.get_filename()
            disposition = str(part.get("Content-Disposition", ""))

            if filename or "attachment" in disposition:
                logger.debug(f"Attachment detected: filename={filename}, disposition={disposition}")
                return True

        return False

    def send_message(self, mime_message: bytes, thread_id: Optional[str] = None) -> str:
        """Send a message via SMTP and store in Sent folder.

        Args:
            mime_message: RFC822 MIME message as bytes
            thread_id: Optional thread ID (not used for IMAP)

        Returns:
            Message ID (UID in Sent folder)

        Raises:
            RuntimeError: If send fails or SMTP not configured
        """
        from ...email.smtp_client import SMTPClient, SMTPConfig

        # Validate SMTP configuration
        if not self.config.smtp_host:
            raise RuntimeError("SMTP host not configured for IMAP account")

        # Get SMTP credentials
        smtp_username = self.config.smtp_username or self.config.email
        if self.config.smtp_password_file:
            smtp_password = Credentials.load_password(self.config.smtp_password_file)
        else:
            # Fall back to IMAP password
            smtp_password = Credentials.load_password(self.config.credential_file)

        # Create SMTP config
        smtp_config = SMTPConfig(
            host=self.config.smtp_host,
            port=self.config.smtp_port,
            username=smtp_username,
            password=smtp_password,
            use_tls=self.config.smtp_tls,
        )

        # Parse MIME message to get From and To addresses
        parsed_message = email.message_from_bytes(mime_message)
        from_addr = parsed_message.get("From", self.config.email)
        to_addrs = []

        # Extract all recipients (To, Cc, Bcc)
        for header in ["To", "Cc", "Bcc"]:
            if parsed_message.get(header):
                to_addrs.extend([addr.strip() for addr in parsed_message.get(header).split(",")])

        # Send via SMTP
        logger.info(f"Sending message via SMTP to {len(to_addrs)} recipients")
        smtp_client = SMTPClient(smtp_config)
        message_id = smtp_client.send_message(parsed_message, from_addr, to_addrs)

        # Store in Sent folder
        try:
            folder_mapping = self._ensure_folder_mapping()
            sent_folder = folder_mapping.get("sent", "Sent")

            # Ensure Sent folder exists
            if sent_folder not in self.list_folders():
                logger.info(f"Creating Sent folder: {sent_folder}")
                self.connection.create(sent_folder)

            # Select Sent folder
            self._select_folder(sent_folder)

            # Append message to Sent folder with \Seen flag
            result = self.connection.append(
                sent_folder,
                "\\Seen",
                None,  # Internal date (server will set)
                mime_message,
            )

            if result[0] == "OK":
                logger.info(f"Stored sent message in {sent_folder}")
                # Return a message ID in our format
                # Extract UID from APPEND response if possible
                return f"{self.account_id}:{sent_folder}:{message_id}"
            else:
                logger.warning(f"Failed to store message in Sent folder: {result}")
                return message_id

        except Exception as e:
            logger.warning(f"Failed to store sent message in IMAP: {e}")
            # Return message ID even if storage failed
            return message_id

    def list_attachments(self, message_id: str) -> List[Dict[str, str]]:
        """List attachments for an IMAP message.

        Args:
            message_id: IMAP message ID (format: account_id:folder:uid)

        Returns:
            List of attachment metadata dicts

        Raises:
            RuntimeError: If message not found or fetch fails
        """
        if not self.connection:
            self.authenticate()

        try:
            # Parse message ID to get folder and UID
            folder, uid = self._parse_message_id(message_id)

            # Select folder and fetch message (use fetch() like fetch_body does)
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            typ, data = self.connection.uid("FETCH", uid, "(RFC822)")

            if typ != "OK" or not data or not data[0]:
                raise RuntimeError(f"Message {message_id} not found")

            # Parse email
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)

            # Extract attachments
            attachments = []
            attachment_index = 0

            for part in email_message.walk():
                # Skip multipart containers
                if part.get_content_maintype() == "multipart":
                    continue

                # Check for filename (attachment indicator)
                filename = part.get_filename()
                if not filename:
                    continue

                # Decode filename if needed
                if filename:
                    decoded_parts = decode_header(filename)
                    filename = "".join(
                        [
                            text.decode(encoding or "utf-8") if isinstance(text, bytes) else text
                            for text, encoding in decoded_parts
                        ]
                    )

                # Get content type
                content_type = part.get_content_type()

                # Check if inline
                disposition = part.get("Content-Disposition", "")
                is_inline = disposition.startswith("inline")

                # Calculate size
                payload = part.get_payload(decode=False)
                size = len(payload.encode() if isinstance(payload, str) else payload)

                # Use part index as attachment ID
                attachment_id = f"part_{attachment_index}"

                attachments.append({
                    "id": attachment_id,
                    "filename": filename,
                    "content_type": content_type,
                    "size": str(size),
                    "is_inline": is_inline,
                })

                attachment_index += 1

            logger.debug(f"Found {len(attachments)} attachments in message {message_id}")
            return attachments

        except Exception as e:
            error_msg = f"Failed to list attachments for {message_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download attachment data from IMAP message.

        Args:
            message_id: IMAP message ID (format: account_id:folder:uid)
            attachment_id: Attachment ID from list_attachments (e.g., "part_0")

        Returns:
            Binary attachment data

        Raises:
            RuntimeError: If attachment not found or download fails
        """
        if not self.connection:
            self.authenticate()

        try:
            # Parse message ID to get folder and UID
            folder, uid = self._parse_message_id(message_id)

            # Select folder and fetch message (use fetch() like fetch_body does)
            if not self._select_folder(folder):
                raise RuntimeError(f"Failed to select folder {folder}")

            typ, data = self.connection.uid("FETCH", uid, "(RFC822)")

            if typ != "OK" or not data or not data[0]:
                raise RuntimeError(f"Message {message_id} not found")

            # Parse email
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)

            # Extract attachment by index
            attachment_index = int(attachment_id.split("_")[1])
            current_index = 0

            for part in email_message.walk():
                # Skip multipart containers
                if part.get_content_maintype() == "multipart":
                    continue

                # Check for filename
                filename = part.get_filename()
                if not filename:
                    continue

                # Check if this is the requested attachment
                if current_index == attachment_index:
                    # Get payload and decode
                    payload = part.get_payload(decode=True)
                    if payload:
                        logger.debug(f"Downloaded attachment {attachment_id} ({len(payload)} bytes)")
                        return payload
                    else:
                        raise RuntimeError(f"Attachment {attachment_id} has no data")

                current_index += 1

            raise RuntimeError(f"Attachment {attachment_id} not found in message")

        except Exception as e:
            error_msg = f"Failed to download attachment {attachment_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
