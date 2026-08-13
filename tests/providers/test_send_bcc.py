"""Tests for Bcc delivery through the provider send paths.

The build step strips Bcc from the message body (so it stays hidden from other
recipients); each provider is responsible for still *delivering* to Bcc via the
explicit envelope. IMAP feeds the envelope straight to SMTP's RCPT list; Gmail
has no envelope parameter so it re-adds a strip-on-send Bcc header.
"""

import email as email_module
from unittest.mock import MagicMock, patch

from cairn_mail.providers.implementations.gmail import GmailProvider
from cairn_mail.providers.implementations.imap import IMAPConfig, IMAPProvider


def _sample_mime(to="to@example.com", cc=None):
    """A minimal built message — note it carries NO Bcc header, by design."""
    msg = email_module.message.EmailMessage()
    msg["From"] = "me@example.com"
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = "hi"
    msg.set_content("body")
    return msg.as_bytes()


# --- IMAP / SMTP ---------------------------------------------------------


def _imap_provider():
    config = IMAPConfig(
        account_id="test",
        email="me@example.com",
        credential_file="/dev/null",
        host="imap.example.com",
        smtp_host="smtp.example.com",
        smtp_password_file="/dev/null",
    )
    provider = IMAPProvider(config)
    provider.connection = MagicMock()
    # Skip the Sent-folder append machinery; we only care about the SMTP send here.
    provider.list_folders = MagicMock(return_value=["Sent"])
    provider._ensure_folder_mapping = MagicMock(return_value={"sent": "Sent"})
    provider._select_folder = MagicMock()
    return provider


@patch("cairn_mail.email.smtp_client.SMTPClient")
@patch("cairn_mail.credentials.Credentials.load_password", return_value="pw")
def test_imap_delivers_to_full_envelope_including_bcc(_pw, smtp_cls):
    smtp = smtp_cls.return_value
    smtp.send_message.return_value = "<mid>"
    provider = _imap_provider()

    provider.send_message(
        _sample_mime(),
        envelope_recipients=["to@example.com", "bcc@example.com"],
    )

    _msg, _from, to_addrs = smtp.send_message.call_args.args
    assert to_addrs == ["to@example.com", "bcc@example.com"]


@patch("cairn_mail.email.smtp_client.SMTPClient")
@patch("cairn_mail.credentials.Credentials.load_password", return_value="pw")
def test_imap_wire_message_has_no_bcc_header(_pw, smtp_cls):
    smtp = smtp_cls.return_value
    smtp.send_message.return_value = "<mid>"
    provider = _imap_provider()

    provider.send_message(
        _sample_mime(),
        envelope_recipients=["to@example.com", "bcc@example.com"],
    )

    transmitted_msg = smtp.send_message.call_args.args[0]
    assert transmitted_msg.get("Bcc") is None


# --- Gmail ---------------------------------------------------------------


def test_gmail_injects_bcc_header_for_hidden_recipient():
    result = GmailProvider._inject_bcc_header(
        _sample_mime(to="to@example.com"),
        ["to@example.com", "bcc@example.com"],
    )
    parsed = email_module.message_from_bytes(result)
    assert parsed.get("Bcc") == "bcc@example.com"


def test_gmail_no_bcc_header_when_all_recipients_visible():
    original = _sample_mime(to="to@example.com", cc="cc@example.com")
    result = GmailProvider._inject_bcc_header(
        original, ["to@example.com", "cc@example.com"]
    )
    # Unchanged, no wasted re-serialization.
    assert result is original
    assert email_module.message_from_bytes(result).get("Bcc") is None


def test_gmail_bcc_detection_ignores_display_name_commas():
    result = GmailProvider._inject_bcc_header(
        _sample_mime(to='"Doe, John" <john@example.com>'),
        ['"Doe, John" <john@example.com>', "secret@example.com"],
    )
    parsed = email_module.message_from_bytes(result)
    # John is visible in To and must NOT be duplicated into Bcc.
    assert parsed.get("Bcc") == "secret@example.com"
