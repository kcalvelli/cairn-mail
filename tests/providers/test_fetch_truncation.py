"""Tests for the last_fetch_complete truncation signal on both providers.

A truncated window must report last_fetch_complete = False so the sync engine
holds the cursor. Gmail additionally paginates so it drains the full window
instead of silently dropping everything past the first page.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from cairn_mail.providers.implementations.gmail import GmailProvider
from cairn_mail.providers.implementations.imap import IMAPProvider


# --- Gmail pagination ----------------------------------------------------


def _gmail_with_pages(pages):
    """A GmailProvider whose messages.list() yields the given pages in order.

    Each page is a dict like {"messages": [...], "nextPageToken": "..."}.
    """
    provider = GmailProvider.__new__(GmailProvider)
    provider._parse_gmail_message = lambda detail: SimpleNamespace(id=detail["id"])

    messages_api = MagicMock()

    def list_call(userId, q, maxResults, pageToken=None):
        # Map the token to a page: None -> page 0, "t1" -> page 1, ...
        idx = 0 if pageToken is None else int(pageToken[1:])
        return SimpleNamespace(execute=lambda: pages[idx])

    messages_api.list.side_effect = list_call
    messages_api.get.side_effect = lambda userId, id, format: SimpleNamespace(
        execute=lambda: {"id": id}
    )

    service = MagicMock()
    service.users.return_value.messages.return_value = messages_api
    provider.service = service
    return provider


def test_gmail_accumulates_all_pages_when_complete():
    pages = [
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t1"},
        {"messages": [{"id": "c"}]},  # no token -> last page
    ]
    provider = _gmail_with_pages(pages)

    messages = provider.fetch_messages(max_results=100)

    assert [m.id for m in messages] == ["a", "b", "c"]
    assert provider.last_fetch_complete is True


def test_gmail_truncates_and_flags_incomplete_at_ceiling():
    pages = [
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "t1"},
        {"messages": [{"id": "c"}, {"id": "d"}], "nextPageToken": "t2"},
    ]
    provider = _gmail_with_pages(pages)

    messages = provider.fetch_messages(max_results=2)

    # Hit the cap with a token still outstanding: take newest cap, flag incomplete.
    assert len(messages) == 2
    assert provider.last_fetch_complete is False


# --- IMAP combined-cap truncation ---------------------------------------


def test_imap_combined_cap_flags_incomplete():
    provider = IMAPProvider.__new__(IMAPProvider)
    provider.connection = MagicMock()
    provider.list_folders = MagicMock(return_value=["INBOX"])
    provider._discover_folder_mapping = MagicMock(return_value={"inbox": "INBOX"})

    # Return more messages than the cap so the combined trim triggers.
    fake_msgs = [SimpleNamespace(date=i) for i in range(10)]
    provider._fetch_from_folder = MagicMock(return_value=fake_msgs)

    result = provider.fetch_messages(since=None, max_results=5)

    assert len(result) == 5
    assert provider.last_fetch_complete is False


def test_imap_complete_fetch_resets_flag_after_a_truncated_one():
    # Flag hygiene: the reset-at-top must clear a stale False from a prior
    # truncated fetch, or the cursor would stay pinned forever.
    provider = IMAPProvider.__new__(IMAPProvider)
    provider.connection = MagicMock()
    provider.list_folders = MagicMock(return_value=["INBOX"])
    provider._discover_folder_mapping = MagicMock(return_value={"inbox": "INBOX"})

    # First: a truncated fetch flips the flag to False.
    provider._fetch_from_folder = MagicMock(
        return_value=[SimpleNamespace(date=i) for i in range(10)]
    )
    provider.fetch_messages(since=None, max_results=5)
    assert provider.last_fetch_complete is False

    # Then: a complete fetch on the same instance must report True again.
    provider._fetch_from_folder = MagicMock(
        return_value=[SimpleNamespace(date=i) for i in range(3)]
    )
    result = provider.fetch_messages(since=None, max_results=5)

    assert len(result) == 3
    assert provider.last_fetch_complete is True
