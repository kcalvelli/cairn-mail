"""HTTP client wrapper for cairn-mail API.

This module provides a thin client that calls the localhost REST API,
decoupling MCP logic from API implementation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Error from the cairn-mail API."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class APIConnectionError(APIError):
    """Could not connect to the API."""

    def __init__(self, base_url: str) -> None:
        super().__init__(
            f"Could not connect to cairn-mail API at {base_url}. "
            "Make sure the web service is running: "
            "systemctl status cairn-mail-web.service",
            status_code=None,
        )
        self.base_url = base_url


@dataclass
class Account:
    """Email account."""

    id: str
    name: str
    email: str
    provider: str
    last_sync: datetime | None = None


@dataclass
class Message:
    """Email message."""

    id: str
    account_id: str
    subject: str
    from_email: str
    to_emails: list[str]
    date: datetime
    snippet: str
    is_unread: bool
    folder: str | None = None
    thread_id: str | None = None
    tags: list[str] | None = None
    has_attachments: bool = False


@dataclass
class MessageBody:
    """Full message body content."""

    id: str
    body_text: str | None
    body_html: str | None


@dataclass
class Draft:
    """Email draft."""

    id: str
    account_id: str
    subject: str
    to_emails: list[str]
    cc_emails: list[str] | None = None
    bcc_emails: list[str] | None = None
    body_text: str | None = None
    body_html: str | None = None
    thread_id: str | None = None
    in_reply_to: str | None = None


class CairnMailClient:
    """HTTP client for cairn-mail REST API."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        """Initialize the client.

        Args:
            base_url: Base URL of the cairn-mail API
        """
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/api/accounts")
            params: Query parameters
            json: JSON body for POST/PUT requests

        Returns:
            JSON response from the API

        Raises:
            APIConnectionError: If the API is unreachable
            APIError: If the API returns an error response
        """
        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json,
            )
        except httpx.ConnectError:
            raise APIConnectionError(self.base_url)
        except httpx.TimeoutException:
            raise APIError(f"Request to {path} timed out", status_code=None)

        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise APIError(f"API error: {detail}", status_code=response.status_code)

        if response.status_code == 204:
            return {}

        return response.json()

    # Account operations

    async def list_accounts(self) -> list[Account]:
        """List all configured email accounts.

        Returns:
            List of Account objects
        """
        data = await self._request("GET", "/api/accounts")
        return [
            Account(
                id=acc["id"],
                name=acc["name"],
                email=acc["email"],
                provider=acc["provider"],
                last_sync=datetime.fromisoformat(acc["last_sync"])
                if acc.get("last_sync")
                else None,
            )
            for acc in data
        ]

    # Message operations

    async def search_messages(
        self,
        account_id: str | None = None,
        folder: str | None = None,
        is_unread: bool | None = None,
        tag: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        """Search for messages with optional filters.

        Args:
            account_id: Filter by account ID
            folder: Filter by folder (inbox, sent, trash)
            is_unread: Filter by read status
            tag: Filter by classification tag
            search: Text search in subject/from/snippet
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Tuple of (list of Message objects, total count)
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if account_id:
            params["account_id"] = account_id
        if folder:
            params["folder"] = folder
        if is_unread is not None:
            params["is_unread"] = is_unread
        if tag:
            params["tag"] = tag
        if search:
            params["search"] = search

        data = await self._request("GET", "/api/messages", params=params)

        messages = [
            Message(
                id=msg["id"],
                account_id=msg["account_id"],
                subject=msg["subject"],
                from_email=msg["from_email"],
                to_emails=msg["to_emails"],
                date=datetime.fromisoformat(msg["date"]),
                snippet=msg["snippet"],
                is_unread=msg["is_unread"],
                thread_id=msg.get("thread_id"),
                tags=msg.get("tags", []),
                has_attachments=msg.get("has_attachments", False),
            )
            for msg in data.get("messages", [])
        ]

        return messages, data.get("total", len(messages))

    async def get_message(self, message_id: str) -> Message:
        """Get a single message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message object

        Raises:
            APIError: If message not found
        """
        data = await self._request("GET", f"/api/messages/{message_id}")
        return Message(
            id=data["id"],
            account_id=data["account_id"],
            subject=data["subject"],
            from_email=data["from_email"],
            to_emails=data["to_emails"],
            date=datetime.fromisoformat(data["date"]),
            snippet=data["snippet"],
            is_unread=data["is_unread"],
            thread_id=data.get("thread_id"),
            tags=data.get("tags", []),
            has_attachments=data.get("has_attachments", False),
        )

    async def get_message_body(self, message_id: str) -> MessageBody:
        """Get full message body content.

        Args:
            message_id: Message ID

        Returns:
            MessageBody object with text and HTML content

        Raises:
            APIError: If message not found
        """
        data = await self._request("GET", f"/api/messages/{message_id}/body")
        return MessageBody(
            id=data["id"],
            body_text=data.get("body_text"),
            body_html=data.get("body_html"),
        )

    async def mark_read(
        self,
        message_ids: list[str],
        is_unread: bool = False,
    ) -> dict[str, Any]:
        """Mark messages as read or unread.

        Args:
            message_ids: List of message IDs
            is_unread: If True, mark as unread; if False, mark as read

        Returns:
            Result dict with updated/errors counts
        """
        return await self._request(
            "POST",
            "/api/messages/bulk/read",
            json={"message_ids": message_ids, "is_unread": is_unread},
        )

    async def delete_messages(
        self,
        message_ids: list[str],
        permanent: bool = False,
    ) -> dict[str, Any]:
        """Delete messages (move to trash or permanently).

        Args:
            message_ids: List of message IDs
            permanent: If True, permanently delete; if False, move to trash

        Returns:
            Result dict with deleted/errors counts
        """
        if permanent:
            return await self._request(
                "POST",
                "/api/messages/bulk/permanent-delete",
                json={"message_ids": message_ids},
            )
        else:
            return await self._request(
                "POST",
                "/api/messages/bulk/delete",
                json={"message_ids": message_ids},
            )

    # Draft operations

    async def create_draft(
        self,
        account_id: str,
        to_emails: list[str],
        subject: str,
        body_text: str | None = None,
        body_html: str | None = None,
        cc_emails: list[str] | None = None,
        bcc_emails: list[str] | None = None,
        thread_id: str | None = None,
        in_reply_to: str | None = None,
    ) -> Draft:
        """Create a new draft.

        Args:
            account_id: Account to create draft in
            to_emails: List of recipient email addresses
            subject: Email subject
            body_text: Plain text body
            body_html: HTML body
            cc_emails: CC recipients
            bcc_emails: BCC recipients
            thread_id: Thread ID for replies
            in_reply_to: Message ID being replied to

        Returns:
            Created Draft object
        """
        data = await self._request(
            "POST",
            "/api/drafts",
            json={
                "account_id": account_id,
                "to_emails": to_emails,
                "subject": subject,
                "body_text": body_text,
                "body_html": body_html,
                "cc_emails": cc_emails,
                "bcc_emails": bcc_emails,
                "thread_id": thread_id,
                "in_reply_to": in_reply_to,
            },
        )
        return Draft(
            id=data["id"],
            account_id=data["account_id"],
            subject=data["subject"],
            to_emails=data["to_emails"],
            cc_emails=data.get("cc_emails"),
            bcc_emails=data.get("bcc_emails"),
            body_text=data.get("body_text"),
            body_html=data.get("body_html"),
            thread_id=data.get("thread_id"),
            in_reply_to=data.get("in_reply_to"),
        )

    async def get_draft(self, draft_id: str) -> Draft:
        """Get a draft by ID.

        Args:
            draft_id: Draft ID

        Returns:
            Draft object

        Raises:
            APIError: If draft not found
        """
        data = await self._request("GET", f"/api/drafts/{draft_id}")
        return Draft(
            id=data["id"],
            account_id=data["account_id"],
            subject=data["subject"],
            to_emails=data["to_emails"],
            cc_emails=data.get("cc_emails"),
            bcc_emails=data.get("bcc_emails"),
            body_text=data.get("body_text"),
            body_html=data.get("body_html"),
            thread_id=data.get("thread_id"),
            in_reply_to=data.get("in_reply_to"),
        )

    async def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Send a draft.

        Args:
            draft_id: Draft ID to send

        Returns:
            Result dict with message_id and status
        """
        return await self._request(
            "POST",
            "/api/send",
            json={"draft_id": draft_id},
        )

    async def delete_draft(self, draft_id: str) -> dict[str, Any]:
        """Delete a draft.

        Args:
            draft_id: Draft ID to delete

        Returns:
            Result dict with status
        """
        return await self._request("DELETE", f"/api/drafts/{draft_id}")

    # Tag operations

    async def update_tags(
        self,
        message_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        """Update tags on a single message.

        Args:
            message_id: Message ID
            tags: New list of tags

        Returns:
            Updated message dict
        """
        return await self._request(
            "PUT",
            f"/api/messages/{message_id}/tags",
            json={"tags": tags},
        )

    async def bulk_update_tags(
        self,
        message_ids: list[str],
        tags: list[str],
    ) -> dict[str, Any]:
        """Update tags on multiple messages at once.

        Args:
            message_ids: List of message IDs
            tags: Tags to apply to all messages

        Returns:
            Result dict with updated/errors counts
        """
        return await self._request(
            "PUT",
            "/api/messages/bulk/tags",
            json={"message_ids": message_ids, "tags": tags},
        )

    # Filter operations

    async def delete_by_filter(
        self,
        tag: str | None = None,
        folder: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete all messages matching filters (move to trash).

        Args:
            tag: Filter by tag
            folder: Filter by folder
            account_id: Filter by account ID

        Returns:
            Result dict with moved_to_trash count and errors
        """
        params: dict[str, Any] = {}
        if tag:
            params["tags"] = tag
        if folder:
            params["folder"] = folder
        if account_id:
            params["account_id"] = account_id
        return await self._request(
            "POST",
            "/api/messages/delete-all",
            params=params,
        )

    async def restore_messages(
        self,
        message_ids: list[str],
    ) -> dict[str, Any]:
        """Restore messages from trash.

        Args:
            message_ids: List of message IDs to restore

        Returns:
            Result dict with restored/errors counts
        """
        return await self._request(
            "POST",
            "/api/messages/bulk/restore",
            json={"message_ids": message_ids},
        )

    async def get_unread_count(
        self,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Get unread message count.

        Args:
            account_id: Optional account ID to filter by

        Returns:
            Dict with count field
        """
        params: dict[str, Any] = {}
        if account_id:
            params["account_id"] = account_id
        return await self._request(
            "GET",
            "/api/messages/unread-count",
            params=params,
        )

    async def list_tags(
        self,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """List all tags with counts.

        Args:
            account_id: Optional account ID to filter by

        Returns:
            Dict with tags list
        """
        params: dict[str, Any] = {}
        if account_id:
            params["account_id"] = account_id
        return await self._request(
            "GET",
            "/api/tags",
            params=params,
        )
