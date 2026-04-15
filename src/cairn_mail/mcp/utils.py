"""Utility functions for MCP server.

This module provides helper functions for account resolution and
other common operations needed by MCP tools.
"""

from .client import Account


class AccountResolutionError(Exception):
    """Error resolving an account name or ID."""

    def __init__(self, message: str, available_accounts: list[str] | None = None) -> None:
        super().__init__(message)
        self.available_accounts = available_accounts or []


def resolve_account(
    account_query: str | None,
    accounts: list[Account],
) -> Account:
    """Resolve a human-readable account name or ID to an Account.

    This function supports:
    - Exact match by ID
    - Exact match by name (case-insensitive)
    - Partial match by name (returns error with suggestions)
    - Default selection if only one account exists

    Args:
        account_query: Account name or ID, or None for default
        accounts: List of available accounts

    Returns:
        Resolved Account object

    Raises:
        AccountResolutionError: If account cannot be resolved
    """
    available_names = [f"{acc.name} ({acc.email})" for acc in accounts]

    if not accounts:
        raise AccountResolutionError(
            "No email accounts configured. Please configure an account in your "
            "cairn-mail settings.",
            available_accounts=[],
        )

    # If no account specified, check for default
    if account_query is None:
        if len(accounts) == 1:
            return accounts[0]
        raise AccountResolutionError(
            f"Multiple accounts configured. Please specify which account to use. "
            f"Available accounts: {', '.join(available_names)}",
            available_accounts=available_names,
        )

    # Try exact match by ID
    for acc in accounts:
        if acc.id == account_query:
            return acc

    # Try exact match by name (case-insensitive)
    query_lower = account_query.lower()
    for acc in accounts:
        if acc.name.lower() == query_lower:
            return acc

    # Try partial match by name
    partial_matches = [
        acc for acc in accounts
        if query_lower in acc.name.lower() or query_lower in acc.email.lower()
    ]

    if len(partial_matches) == 1:
        return partial_matches[0]

    if len(partial_matches) > 1:
        match_names = [f"{acc.name} ({acc.email})" for acc in partial_matches]
        raise AccountResolutionError(
            f"Ambiguous account '{account_query}'. Multiple accounts match: "
            f"{', '.join(match_names)}. Please be more specific.",
            available_accounts=match_names,
        )

    # No matches found
    raise AccountResolutionError(
        f"Account '{account_query}' not found. "
        f"Available accounts: {', '.join(available_names)}",
        available_accounts=available_names,
    )


def normalize_email_list(emails: str | list[str] | None) -> list[str]:
    """Normalize email input to a list of email addresses.

    Handles:
    - Single email string: "user@example.com"
    - Comma-separated string: "a@example.com, b@example.com"
    - List of emails: ["a@example.com", "b@example.com"]
    - None: returns empty list

    Args:
        emails: Email input in various formats

    Returns:
        List of email addresses
    """
    if emails is None:
        return []

    if isinstance(emails, str):
        # Split by comma and strip whitespace
        return [e.strip() for e in emails.split(",") if e.strip()]

    return list(emails)


def format_message_summary(
    message_id: str,
    subject: str,
    from_email: str,
    snippet: str,
    max_snippet_len: int = 100,
) -> str:
    """Format a message summary for display.

    Args:
        message_id: Message ID
        subject: Email subject
        from_email: Sender email
        snippet: Message snippet
        max_snippet_len: Maximum snippet length

    Returns:
        Formatted summary string
    """
    truncated_snippet = snippet[:max_snippet_len]
    if len(snippet) > max_snippet_len:
        truncated_snippet += "..."

    return f"[{message_id}] From: {from_email}\nSubject: {subject}\n{truncated_snippet}"
