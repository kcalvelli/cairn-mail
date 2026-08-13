"""Tests for IMAP custom-keyword write-back.

Covers the fix where keyword support was gated on a bogus ``KEYWORD`` token in
the CAPABILITY response instead of the ``\\*`` flag in a mailbox's
PERMANENTFLAGS — which made AI tag write-back a silent no-op on every real
server.
"""

from unittest.mock import MagicMock

import pytest

from cairn_mail.providers.implementations.imap import IMAPConfig, IMAPProvider


def make_provider(permanentflags=b"(\\Answered \\Flagged \\Deleted \\Seen \\*)"):
    """Build an IMAPProvider with a mocked connection.

    ``permanentflags`` is what ``connection.response("PERMANENTFLAGS")`` returns
    for the payload; pass None to simulate a server that omits the line.
    """
    config = IMAPConfig(
        account_id="test",
        email="user@example.com",
        credential_file="/dev/null",
        host="imap.example.com",
        keyword_prefix="$",
    )
    provider = IMAPProvider(config)
    conn = MagicMock()
    conn.select.return_value = ("OK", [b"3"])
    # imaplib's response() echoes the requested code back as the first tuple
    # element ("PERMANENTFLAGS"), never "OK" — mirror that exactly so the mock
    # can't paper over a wrong assumption in the detection code.
    conn.response.return_value = ("PERMANENTFLAGS", [permanentflags])
    conn.uid.return_value = ("OK", [b"1 (UID 42)"])
    provider.connection = conn
    return provider, conn


def test_permanentflags_with_star_marks_supported():
    provider, _ = make_provider()
    assert provider._select_folder("INBOX") is True
    assert provider._keyword_support["INBOX"] is True


def test_permanentflags_without_star_marks_unsupported():
    provider, _ = make_provider(permanentflags=b"(\\Answered \\Flagged \\Seen)")
    provider._select_folder("INBOX")
    assert provider._keyword_support["INBOX"] is False


def test_missing_permanentflags_marks_unsupported():
    provider, conn = make_provider()
    conn.response.return_value = ("PERMANENTFLAGS", [None])
    provider._select_folder("INBOX")
    assert provider._keyword_support["INBOX"] is False


def test_capability_without_keyword_still_writes_back():
    """The regression this change fixes: a server whose CAPABILITY lacks the
    (non-existent) KEYWORD token still gets write-back when PERMANENTFLAGS has
    \\*. We never call capability() at all anymore."""
    provider, conn = make_provider()
    conn.capability.side_effect = AssertionError("capability() must not be used")

    provider.update_labels("test:INBOX:42", add_labels=["work"], remove_labels=[])

    conn.uid.assert_called_once_with("STORE", "42", "+FLAGS", "($work)")


def test_update_labels_issues_add_and_remove_stores():
    provider, conn = make_provider()

    provider.update_labels(
        "test:INBOX:42", add_labels=["work", "finance"], remove_labels=["spam"]
    )

    conn.uid.assert_any_call("STORE", "42", "+FLAGS", "($work $finance)")
    conn.uid.assert_any_call("STORE", "42", "-FLAGS", "($spam)")


def test_failed_store_raises():
    provider, conn = make_provider()
    conn.uid.return_value = ("NO", [b"permission denied"])

    with pytest.raises(RuntimeError, match="UID STORE"):
        provider.update_labels("test:INBOX:42", add_labels=["work"], remove_labels=[])


def test_unsupported_folder_skips_without_raising_and_logs_once(caplog):
    import logging

    caplog.set_level(logging.INFO)
    provider, conn = make_provider(permanentflags=b"(\\Answered \\Seen)")

    provider.update_labels("test:INBOX:42", add_labels=["work"], remove_labels=[])
    provider.update_labels("test:INBOX:43", add_labels=["finance"], remove_labels=[])

    # No STORE ever issued on an unsupported mailbox.
    conn.uid.assert_not_called()
    # Logged exactly once for the folder despite two calls.
    warnings = [
        r for r in caplog.records if "does not accept custom keywords" in r.message
    ]
    assert len(warnings) == 1
