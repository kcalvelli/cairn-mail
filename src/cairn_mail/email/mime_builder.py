"""MIME message builder for email composition."""

import logging
from datetime import datetime
from email import encoders
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from typing import List, Optional, Tuple

from ..db.models import Attachment, Draft

logger = logging.getLogger(__name__)


class MIMEBuilder:
    """Build RFC-compliant MIME messages for email sending."""

    @staticmethod
    def build_from_draft(
        draft: Draft,
        attachments: Optional[List[Attachment]] = None,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> EmailMessage:
        """Build a MIME message from a draft.

        Args:
            draft: Draft to build message from
            attachments: List of attachments to include
            from_name: Display name for From header (uses email if not provided)
            from_email: Email address for From header (required to avoid lazy loading)

        Returns:
            EmailMessage ready to send
        """
        # Determine message structure based on content
        has_html = draft.body_html is not None
        has_text = draft.body_text is not None
        has_attachments = attachments and len(attachments) > 0

        # Create appropriate MIME structure
        if has_attachments:
            # multipart/mixed with body and attachments
            msg = MIMEMultipart("mixed")
            body_part = MIMEBuilder._build_body(draft.body_text, draft.body_html)
            msg.attach(body_part)

            # Add attachments
            logger.info(f"Building message with {len(attachments)} attachment(s)")
            for attachment in attachments:
                logger.debug(f"Adding attachment: {attachment.filename} ({attachment.size} bytes, type: {attachment.content_type})")
                attachment_part = MIMEBuilder._build_attachment(attachment)
                if attachment_part:
                    msg.attach(attachment_part)
                else:
                    logger.warning(f"Skipped attachment {attachment.filename} - no data")

        elif has_html and has_text:
            # multipart/alternative with text and HTML
            msg = MIMEBuilder._build_body(draft.body_text, draft.body_html)

        elif has_html:
            # HTML only
            msg = MIMEText(draft.body_html, "html", "utf-8")

        else:
            # Plain text only
            msg = MIMEText(draft.body_text or "", "plain", "utf-8")

        # Set headers
        MIMEBuilder._set_headers(msg, draft, from_name, from_email)

        return msg

    @staticmethod
    def _build_body(body_text: Optional[str], body_html: Optional[str]) -> MIMEMultipart:
        """Build multipart/alternative body with text and HTML parts.

        Args:
            body_text: Plain text body
            body_html: HTML body

        Returns:
            MIMEMultipart with text and HTML alternatives
        """
        body = MIMEMultipart("alternative")

        # Add text part first (fallback)
        if body_text:
            text_part = MIMEText(body_text, "plain", "utf-8")
            body.attach(text_part)

        # Add HTML part second (preferred)
        if body_html:
            html_part = MIMEText(body_html, "html", "utf-8")
            body.attach(html_part)

        return body

    @staticmethod
    def _build_attachment(attachment: Attachment) -> Optional[MIMEBase]:
        """Build MIME attachment part.

        Args:
            attachment: Attachment to encode

        Returns:
            MIMEBase attachment part, or None if attachment has no data
        """
        # Validate attachment data exists
        if attachment.data is None:
            logger.error(f"Attachment {attachment.filename} has no data (None)")
            return None

        if len(attachment.data) == 0:
            logger.error(f"Attachment {attachment.filename} has empty data (0 bytes)")
            return None

        logger.debug(f"Building attachment: {attachment.filename}, actual data size: {len(attachment.data)} bytes")

        # Parse content type
        maintype, subtype = attachment.content_type.split("/", 1) if "/" in attachment.content_type else ("application", "octet-stream")

        # Create MIME part
        part = MIMEBase(maintype, subtype)
        part.set_payload(attachment.data)

        # Encode as base64
        encoders.encode_base64(part)

        # Set Content-Disposition header with filename
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment.filename,
        )

        # Log the part size after encoding
        part_bytes = part.as_bytes()
        logger.debug(f"Attachment MIME part size: {len(part_bytes)} bytes")

        return part

    @staticmethod
    def _set_headers(
        msg: EmailMessage, draft: Draft, from_name: Optional[str] = None, from_email: Optional[str] = None
    ) -> None:
        """Set email headers on message.

        Args:
            msg: Message to set headers on
            draft: Draft with header information
            from_name: Display name for From header
            from_email: Email address for From header
        """
        # Use provided email or raise error
        if not from_email:
            raise ValueError("from_email is required to avoid lazy loading issues")

        # From header with optional display name
        if from_name:
            msg["From"] = formataddr((from_name, from_email))
        else:
            msg["From"] = from_email

        # To header
        msg["To"] = ", ".join(draft.to_emails)

        # Cc header
        if draft.cc_emails:
            msg["Cc"] = ", ".join(draft.cc_emails)

        # Bcc header (note: omitted from final message, handled separately in SMTP)
        # BCC recipients are added via RCPT TO in SMTP, not in headers

        # Subject
        msg["Subject"] = draft.subject

        # Date
        msg["Date"] = formatdate(localtime=True)

        # Message-ID
        msg["Message-ID"] = make_msgid(domain=from_email.split("@")[1])

        # Reply headers
        if draft.in_reply_to:
            msg["In-Reply-To"] = draft.in_reply_to

            # References header (includes In-Reply-To)
            msg["References"] = draft.in_reply_to

    @staticmethod
    def calculate_size(msg: EmailMessage) -> int:
        """Calculate total message size in bytes.

        Args:
            msg: Message to calculate size for

        Returns:
            Size in bytes
        """
        return len(msg.as_bytes())

    @staticmethod
    def validate_size(msg: EmailMessage, max_size_mb: int = 25) -> Tuple[bool, int]:
        """Validate message size against limit.

        Args:
            msg: Message to validate
            max_size_mb: Maximum size in megabytes

        Returns:
            Tuple of (is_valid, size_in_bytes)
        """
        size = MIMEBuilder.calculate_size(msg)
        max_size = max_size_mb * 1024 * 1024
        is_valid = size <= max_size

        if not is_valid:
            logger.warning(f"Message size {size / (1024 * 1024):.2f}MB exceeds {max_size_mb}MB limit")

        return is_valid, size

    @staticmethod
    def to_base64_url_safe(msg: EmailMessage) -> str:
        """Encode message as base64 URL-safe string for Gmail API.

        Args:
            msg: Message to encode

        Returns:
            Base64 URL-safe encoded string
        """
        import base64

        return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
