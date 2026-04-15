"""MCP tool implementations for cairn-mail.

This module contains all the MCP tools that expose email operations
to AI assistants.
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import APIConnectionError, APIError, CairnMailClient
from .utils import (
    AccountResolutionError,
    normalize_email_list,
    resolve_account,
)

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP, client: CairnMailClient) -> None:
    """Register all MCP tools with the server.

    Args:
        mcp: FastMCP server instance
        client: CairnMailClient instance for API calls
    """

    @mcp.tool()
    async def list_accounts() -> list[dict[str, Any]]:
        """List all configured email accounts.

        Returns account names, emails, and providers.
        Use the account name or ID in other tools to specify which account to use.

        Returns:
            List of accounts with id, name, email, and provider fields.
        """
        try:
            accounts = await client.list_accounts()
            return [
                {
                    "id": acc.id,
                    "name": acc.name,
                    "email": acc.email,
                    "provider": acc.provider,
                    "last_sync": acc.last_sync.isoformat() if acc.last_sync else None,
                }
                for acc in accounts
            ]
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def search_emails(
        query: str | None = None,
        account: str | None = None,
        folder: str = "inbox",
        unread_only: bool = False,
        tag: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search for emails with optional filters.

        Args:
            query: Text to search in subject, sender, and body.
            account: Account name or ID. If omitted, searches all accounts.
            folder: Folder to search (inbox, sent, trash). Default: inbox.
            unread_only: Only return unread messages. Default: False.
            tag: Filter by classification tag (e.g., "important", "newsletter").
            limit: Maximum results to return. Default: 20.

        Returns:
            Dict with 'messages' list and 'total' count.
            Each message has id, subject, from_email, date, snippet, is_unread.
        """
        try:
            # Resolve account if specified
            account_id = None
            if account:
                accounts = await client.list_accounts()
                try:
                    resolved = resolve_account(account, accounts)
                    account_id = resolved.id
                except AccountResolutionError as e:
                    return {"error": str(e), "available_accounts": e.available_accounts}

            messages, total = await client.search_messages(
                account_id=account_id,
                folder=folder,
                is_unread=unread_only if unread_only else None,
                tag=tag,
                search=query,
                limit=limit,
            )

            return {
                "messages": [
                    {
                        "id": msg.id,
                        "account_id": msg.account_id,
                        "subject": msg.subject,
                        "from_email": msg.from_email,
                        "date": msg.date.isoformat(),
                        "snippet": msg.snippet,
                        "is_unread": msg.is_unread,
                        "tags": msg.tags,
                        "has_attachments": msg.has_attachments,
                    }
                    for msg in messages
                ],
                "total": total,
                "limit": limit,
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def read_email(message_id: str) -> dict[str, Any]:
        """Get the full content of an email by ID.

        Args:
            message_id: The ID of the email to read (from search_emails results).

        Returns:
            Full email content including subject, sender, recipients, date,
            body text, and attachment info.
        """
        try:
            # Get message metadata
            message = await client.get_message(message_id)

            # Get full body
            body = await client.get_message_body(message_id)

            return {
                "id": message.id,
                "account_id": message.account_id,
                "subject": message.subject,
                "from_email": message.from_email,
                "to_emails": message.to_emails,
                "date": message.date.isoformat(),
                "is_unread": message.is_unread,
                "thread_id": message.thread_id,
                "tags": message.tags,
                "has_attachments": message.has_attachments,
                "body_text": body.body_text,
                "body_html": body.body_html,
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def compose_email(
        to: str | list[str],
        subject: str,
        body: str,
        account: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a draft email (does not send).

        Use send_email with the returned draft_id to actually send the email.

        Args:
            to: Recipient email(s). Can be a single email or comma-separated list.
            subject: Email subject line.
            body: Email body text.
            account: Account name or ID to send from. Required if multiple accounts.
            cc: CC recipient(s). Optional.
            bcc: BCC recipient(s). Optional.

        Returns:
            Dict with draft_id for use with send_email.
        """
        try:
            # Resolve account
            accounts = await client.list_accounts()
            try:
                resolved = resolve_account(account, accounts)
            except AccountResolutionError as e:
                return {"error": str(e), "available_accounts": e.available_accounts}

            # Normalize email lists
            to_emails = normalize_email_list(to)
            cc_emails = normalize_email_list(cc)
            bcc_emails = normalize_email_list(bcc)

            if not to_emails:
                return {"error": "At least one recipient (to) is required."}

            # Create draft
            draft = await client.create_draft(
                account_id=resolved.id,
                to_emails=to_emails,
                subject=subject,
                body_text=body,
                cc_emails=cc_emails if cc_emails else None,
                bcc_emails=bcc_emails if bcc_emails else None,
            )

            return {
                "draft_id": draft.id,
                "account": resolved.name,
                "to": to_emails,
                "subject": subject,
                "status": "draft_created",
                "message": f"Draft created. Use send_email(draft_id='{draft.id}') to send.",
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def send_email(
        draft_id: str | None = None,
        to: str | list[str] | None = None,
        subject: str | None = None,
        body: str | None = None,
        account: str | None = None,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """Send an email.

        Either provide a draft_id to send an existing draft,
        or provide to/subject/body to compose and send in one step.

        Args:
            draft_id: ID of an existing draft to send.
            to: Recipient email(s) for compose-and-send.
            subject: Subject for compose-and-send.
            body: Body text for compose-and-send.
            account: Account name/ID for compose-and-send.
            cc: CC recipients for compose-and-send.
            bcc: BCC recipients for compose-and-send.

        Returns:
            Dict with message_id, status, and full content of sent email
            (to, cc, bcc, subject, body, account) so the AI can report
            what was sent without needing to query the message.
        """
        try:
            # If draft_id provided, send the existing draft
            if draft_id:
                # Fetch draft content BEFORE sending (draft is deleted after send)
                draft = await client.get_draft(draft_id)

                # Resolve account name for display
                accounts = await client.list_accounts()
                account_name = next(
                    (acc.name for acc in accounts if acc.id == draft.account_id),
                    draft.account_id,
                )

                result = await client.send_draft(draft_id)
                return {
                    "message_id": result.get("message_id"),
                    "status": "sent",
                    "draft_id": draft_id,
                    "account": account_name,
                    "to": draft.to_emails,
                    "cc": draft.cc_emails,
                    "bcc": draft.bcc_emails,
                    "subject": draft.subject,
                    "body": draft.body_text,
                }

            # Otherwise, compose and send in one step
            if not to or not subject or not body:
                return {
                    "error": "Either provide draft_id, or provide to, subject, and body "
                    "to compose and send in one step."
                }

            # Create draft first
            compose_result = await compose_email(
                to=to,
                subject=subject,
                body=body,
                account=account,
                cc=cc,
                bcc=bcc,
            )

            if "error" in compose_result:
                return compose_result

            # Send the draft
            new_draft_id = compose_result["draft_id"]
            result = await client.send_draft(new_draft_id)

            # Normalize cc/bcc for response
            cc_emails = normalize_email_list(cc)
            bcc_emails = normalize_email_list(bcc)

            return {
                "message_id": result.get("message_id"),
                "status": "sent",
                "account": compose_result["account"],
                "to": compose_result["to"],
                "cc": cc_emails if cc_emails else None,
                "bcc": bcc_emails if bcc_emails else None,
                "subject": subject,
                "body": body,
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            # If send failed, try to clean up draft
            if draft_id is None and "new_draft_id" in dir():
                try:
                    await client.delete_draft(new_draft_id)
                except Exception:
                    pass
            return {"error": str(e)}

    @mcp.tool()
    async def reply_to_email(
        message_id: str,
        body: str,
        reply_all: bool = False,
    ) -> dict[str, Any]:
        """Create a reply draft for an email.

        Args:
            message_id: ID of the email to reply to.
            body: Reply body text.
            reply_all: If True, reply to all recipients. Default: False.

        Returns:
            Dict with draft_id. Use send_email to send the reply.
        """
        try:
            # Get original message
            original = await client.get_message(message_id)

            # Build reply subject
            subject = original.subject
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            # Determine recipients
            to_emails = [original.from_email]

            if reply_all:
                # Add original TO recipients (excluding our own email)
                accounts = await client.list_accounts()
                our_emails = {acc.email.lower() for acc in accounts}

                for email in original.to_emails:
                    if email.lower() not in our_emails and email not in to_emails:
                        to_emails.append(email)

            # Find the account that received this message
            accounts = await client.list_accounts()
            account_id = original.account_id

            # Create reply draft
            draft = await client.create_draft(
                account_id=account_id,
                to_emails=to_emails,
                subject=subject,
                body_text=body,
                thread_id=original.thread_id,
                in_reply_to=message_id,
            )

            return {
                "draft_id": draft.id,
                "to": to_emails,
                "subject": subject,
                "reply_all": reply_all,
                "status": "draft_created",
                "message": f"Reply draft created. Use send_email(draft_id='{draft.id}') to send.",
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def mark_read(
        message_ids: str | list[str],
        unread: bool = False,
    ) -> dict[str, Any]:
        """Mark messages as read or unread.

        Args:
            message_ids: Single message ID or list of IDs.
            unread: If True, mark as unread. Default: False (mark as read).

        Returns:
            Dict with count of updated messages.
        """
        try:
            # Normalize to list
            if isinstance(message_ids, str):
                ids = [message_ids]
            else:
                ids = list(message_ids)

            result = await client.mark_read(ids, is_unread=unread)

            action = "unread" if unread else "read"
            return {
                "updated": result.get("updated", 0),
                "total": result.get("total", len(ids)),
                "action": f"marked_as_{action}",
                "errors": result.get("errors", []),
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_email(
        message_ids: str | list[str],
        permanent: bool = False,
    ) -> dict[str, Any]:
        """Delete emails (move to trash or permanently delete).

        Args:
            message_ids: Single message ID or list of IDs.
            permanent: If True, permanently delete. Default: False (move to trash).

        Returns:
            Dict with count of deleted messages.
        """
        try:
            # Normalize to list
            if isinstance(message_ids, str):
                ids = [message_ids]
            else:
                ids = list(message_ids)

            result = await client.delete_messages(ids, permanent=permanent)

            if permanent:
                return {
                    "deleted": result.get("deleted", 0),
                    "total": result.get("total", len(ids)),
                    "action": "permanently_deleted",
                    "errors": result.get("errors", []),
                }
            else:
                return {
                    "moved_to_trash": result.get("moved_to_trash", 0),
                    "total": result.get("total", len(ids)),
                    "action": "moved_to_trash",
                    "errors": result.get("errors", []),
                }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def update_tags(
        message_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        """Set classification tags on a message.

        Updates the message's tags and records the change as DFSL feedback
        so the classification system learns from corrections.

        Args:
            message_id: The ID of the message to tag.
            tags: List of tags to set (e.g., ["newsletter", "low-priority"]).
                  Replaces all existing tags on the message.

        Returns:
            Updated message with new tags.
        """
        try:
            result = await client.update_tags(message_id, tags)
            return {
                "id": result.get("id", message_id),
                "tags": result.get("tags", tags),
                "status": "tags_updated",
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def bulk_update_tags(
        message_ids: list[str],
        tags: list[str],
    ) -> dict[str, Any]:
        """Set the same classification tags on multiple messages at once.

        Useful for batch operations like tagging all newsletters or marking
        a group of messages with the same category. Records DFSL feedback
        for each update.

        Args:
            message_ids: List of message IDs to tag.
            tags: List of tags to apply to all messages.

        Returns:
            Dict with count of updated messages and any errors.
        """
        try:
            result = await client.bulk_update_tags(message_ids, tags)
            return {
                "updated": result.get("updated", 0),
                "total": result.get("total", len(message_ids)),
                "tags": tags,
                "action": "tags_updated",
                "errors": result.get("errors", []),
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def delete_by_filter(
        tag: str | None = None,
        folder: str | None = None,
        account: str | None = None,
    ) -> dict[str, Any]:
        """Delete all messages matching the given filters (moves to trash).

        At least one filter must be provided to prevent accidental deletion
        of all messages.

        Args:
            tag: Filter by classification tag (e.g., "spam", "newsletter").
            folder: Filter by folder (e.g., "inbox", "sent").
            account: Account name or ID to filter by.

        Returns:
            Dict with count of messages moved to trash.
        """
        try:
            if not tag and not folder and not account:
                return {
                    "error": "At least one filter (tag, folder, or account) is required "
                    "to prevent accidental deletion of all messages."
                }

            # Resolve account if specified
            account_id = None
            if account:
                accounts = await client.list_accounts()
                try:
                    resolved = resolve_account(account, accounts)
                    account_id = resolved.id
                except AccountResolutionError as e:
                    return {"error": str(e), "available_accounts": e.available_accounts}

            result = await client.delete_by_filter(
                tag=tag,
                folder=folder,
                account_id=account_id,
            )
            return {
                "moved_to_trash": result.get("moved_to_trash", 0),
                "total": result.get("total", 0),
                "action": "moved_to_trash",
                "errors": result.get("errors", []),
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def restore_email(
        message_ids: str | list[str],
    ) -> dict[str, Any]:
        """Restore messages from trash back to inbox.

        Args:
            message_ids: Single message ID or list of IDs to restore.

        Returns:
            Dict with count of restored messages.
        """
        try:
            if isinstance(message_ids, str):
                ids = [message_ids]
            else:
                ids = list(message_ids)

            result = await client.restore_messages(ids)
            return {
                "restored": result.get("restored", 0),
                "total": result.get("total", len(ids)),
                "action": "restored_from_trash",
                "errors": result.get("errors", []),
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_unread_count(
        account: str | None = None,
    ) -> dict[str, Any]:
        """Get the count of unread messages without fetching message details.

        Useful for quick "do I have mail?" checks.

        Args:
            account: Account name or ID. If omitted, returns total across all accounts.

        Returns:
            Dict with unread message count.
        """
        try:
            account_id = None
            if account:
                accounts = await client.list_accounts()
                try:
                    resolved = resolve_account(account, accounts)
                    account_id = resolved.id
                except AccountResolutionError as e:
                    return {"error": str(e), "available_accounts": e.available_accounts}

            result = await client.get_unread_count(account_id)
            return {
                "unread_count": result.get("count", 0),
                "account": account or "all",
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}

    @mcp.tool()
    async def list_tags() -> dict[str, Any]:
        """List all available tags with message counts.

        Shows which classification tags exist and how many messages have each tag.
        Useful for discovering what tags are available before filtering or tagging.

        Returns:
            Dict with list of tags, each having name and count.
        """
        try:
            result = await client.list_tags()
            return {
                "tags": result.get("tags", []),
                "total_tags": len(result.get("tags", [])),
            }
        except APIConnectionError as e:
            return {"error": str(e)}
        except APIError as e:
            return {"error": str(e)}
