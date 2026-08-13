"""Tests for the send-path delivery envelope.

Covers the Bcc-delivery fix: the envelope that mail is actually delivered to is
built from the draft's structured To/Cc/Bcc fields, not re-parsed out of the
message headers (where Bcc is deliberately absent).
"""

from cairn_mail.api.routes.send import build_envelope_recipients


def test_bcc_recipient_included_in_envelope():
    envelope = build_envelope_recipients(
        ["to@example.com"], ["cc@example.com"], ["bcc@example.com"]
    )
    assert envelope == ["to@example.com", "cc@example.com", "bcc@example.com"]


def test_bcc_only_draft_still_has_an_envelope():
    # The regression: a Bcc-only send used to deliver to nobody.
    assert build_envelope_recipients([], None, ["bcc@example.com"]) == ["bcc@example.com"]


def test_none_cc_and_bcc_are_tolerated():
    assert build_envelope_recipients(["to@example.com"], None, None) == ["to@example.com"]


def test_empty_draft_yields_empty_envelope():
    # The route turns this into a 400 rather than handing SMTP no recipients.
    assert build_envelope_recipients([], None, None) == []


def test_display_name_with_comma_is_one_recipient():
    envelope = build_envelope_recipients(
        ['"Calvelli, Keith" <keith@example.com>'], None, None
    )
    assert envelope == ["keith@example.com"]
