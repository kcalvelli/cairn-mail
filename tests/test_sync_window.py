"""Tests for incremental sync window slack and cursor-advance discipline.

Covers the data-loss fix: the fetch window is widened by a slack margin so
day-boundary messages aren't excluded, and the last_sync cursor advances only
when the window was fetched completely and stored without error — otherwise mail
that was truncated or failed would be leapfrogged and (on Gmail) lost forever.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from cairn_mail.sync_engine import SYNC_WINDOW_SLACK, SyncEngine


def make_engine(last_sync, fetch_complete=True, fetched=None):
    """A SyncEngine wired to mocks, with an empty pending-ops queue.

    An empty fetch keeps the store/classify loop out of the picture so the test
    isolates window + cursor behavior.
    """
    provider = MagicMock()
    provider.account_id = "acct"
    provider.uses_imap_folders = False
    provider.last_fetch_complete = fetch_complete
    provider.fetch_messages.return_value = fetched or []

    db = MagicMock()
    db.get_pending_operations.return_value = []
    db.get_last_sync_time.return_value = last_sync

    engine = SyncEngine(provider=provider, database=db, ai_classifier=MagicMock())
    return engine, provider, db


def test_fetch_window_is_widened_by_slack():
    cursor = datetime(2026, 8, 13, 6, 0, tzinfo=timezone.utc)
    engine, provider, _ = make_engine(cursor)

    engine.sync()

    since_arg = provider.fetch_messages.call_args.kwargs["since"]
    assert since_arg == cursor - SYNC_WINDOW_SLACK


def test_first_sync_passes_none_window():
    engine, provider, _ = make_engine(last_sync=None)

    engine.sync()

    assert provider.fetch_messages.call_args.kwargs["since"] is None


def test_cursor_advances_on_clean_complete_sync():
    engine, _, db = make_engine(last_sync=None, fetch_complete=True)

    engine.sync()

    db.update_last_sync.assert_called_once()


def test_cursor_holds_when_fetch_incomplete():
    engine, _, db = make_engine(last_sync=None, fetch_complete=False)

    engine.sync()

    db.update_last_sync.assert_not_called()


def test_cursor_holds_on_store_failure_even_when_fetch_complete():
    # A complete fetch whose messages fail to store must NOT advance the cursor —
    # the failed messages need to be retried, not leapfrogged.
    bad_message = MagicMock()
    bad_message.id = "m1"
    bad_message.folder = "inbox"
    engine, _, db = make_engine(
        last_sync=None, fetch_complete=True, fetched=[bad_message]
    )
    db.get_message.return_value = None
    db.create_or_update_message.side_effect = RuntimeError("disk full")

    engine.sync()

    db.update_last_sync.assert_not_called()


def test_cursor_advances_to_start_time_not_now():
    # The advance value must be the pre-fetch timestamp, not a post-fetch now(),
    # or mail arriving mid-sync gets skipped by the next window.
    engine, _, db = make_engine(last_sync=None, fetch_complete=True)

    before = datetime.now(timezone.utc)
    engine.sync()
    after = datetime.now(timezone.utc)

    advanced_to = db.update_last_sync.call_args.args[1]
    assert before <= advanced_to <= after
