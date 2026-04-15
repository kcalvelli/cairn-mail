"""Web Push notification service.

Sends push notifications to subscribed browsers when new emails arrive.
Uses pywebpush with VAPID authentication.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pywebpush import WebPushException, webpush

from .db.database import Database
from .db.models import PushSubscription

logger = logging.getLogger(__name__)

MAX_PUSH_PER_SYNC = 5  # Don't spam — limit notifications per sync cycle


class PushService:
    """Sends Web Push notifications to registered subscribers."""

    def __init__(
        self,
        database: Database,
        vapid_private_key_file: str,
        vapid_public_key: str,
        contact_email: str,
    ):
        """Initialize push service.

        Args:
            database: Database instance for subscription lookups
            vapid_private_key_file: Path to VAPID private key (PEM file)
            vapid_public_key: VAPID public key (base64url)
            contact_email: Contact email for VAPID claims
        """
        self.db = database
        self.vapid_public_key = vapid_public_key
        self.contact_email = contact_email

        # Read VAPID private key from file and convert to raw base64url format.
        # pywebpush's Vapid.from_string() doesn't handle PEM format, so we
        # extract the raw 32-byte private key scalar and base64url-encode it.
        key_path = Path(vapid_private_key_file)
        if key_path.exists():
            self.vapid_private_key = self._load_vapid_key(key_path)
            if self.vapid_private_key:
                logger.info("Push service initialized with VAPID keys")
            else:
                logger.warning("VAPID private key could not be parsed")
        else:
            self.vapid_private_key = ""
            logger.warning(f"VAPID private key not found at {vapid_private_key_file}")

    @staticmethod
    def _load_vapid_key(key_path: Path) -> str:
        """Load a VAPID private key and return it as a raw base64url string.

        Handles both PEM-encoded keys (SEC1 or PKCS8) and raw base64url keys.
        pywebpush's Vapid.from_string() only understands raw/DER format, so
        PEM keys must be converted to the 32-byte raw scalar form.

        Args:
            key_path: Path to the private key file

        Returns:
            Base64url-encoded raw private key string, or empty string on error
        """
        try:
            raw = key_path.read_text().strip()

            if raw.startswith("-----"):
                # PEM format — parse with cryptography, extract raw D value
                pem_key = load_pem_private_key(raw.encode("utf-8"), password=None)
                # Get the raw 32-byte private key integer
                private_numbers = pem_key.private_numbers()
                d_bytes = private_numbers.private_value.to_bytes(32, byteorder="big")
                # Base64url-encode (no padding) — the format Vapid.from_raw() expects
                return base64.urlsafe_b64encode(d_bytes).rstrip(b"=").decode("ascii")
            else:
                # Already raw base64url — pass through
                return raw
        except Exception as e:
            logger.error(f"Failed to load VAPID private key: {e}")
            return ""

    def _send_push(self, subscription: PushSubscription, payload: dict) -> bool:
        """Send a push notification to a single subscription.

        Args:
            subscription: Push subscription to send to
            payload: Notification payload dict

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.vapid_private_key:
            logger.warning("Cannot send push: VAPID private key not loaded")
            return False

        subscription_info = {
            "endpoint": subscription.endpoint,
            "keys": {
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
            },
        }

        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims={"sub": self.contact_email},
            )
            self.db.update_push_subscription_last_used(subscription.endpoint)
            return True

        except WebPushException as e:
            response = getattr(e, "response", None)
            # Use `is not None` — Response.__bool__() is False for status >= 400
            status_code = response.status_code if response is not None else None

            if status_code in (404, 410):
                # Subscription expired or invalid — clean up
                logger.info(
                    f"Removing expired push subscription (HTTP {status_code}): "
                    f"{subscription.endpoint[:50]}..."
                )
                self.db.delete_push_subscription(subscription.endpoint)
            else:
                logger.error(f"Push notification failed: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected push error: {e}")
            return False

    def notify_new_messages(self, messages: List[dict]) -> int:
        """Send push notifications for new messages.

        Args:
            messages: List of new message dicts with keys:
                      id, subject, from_email, snippet

        Returns:
            Number of notifications sent successfully
        """
        if not messages:
            return 0

        subscriptions = self.db.get_all_push_subscriptions()
        if not subscriptions:
            return 0

        # Limit to avoid spamming
        messages_to_notify = messages[:MAX_PUSH_PER_SYNC]
        sent_count = 0

        for msg in messages_to_notify:
            # Extract display name from "Name <email>" format
            from_email = msg.get("from_email", "Unknown")
            sender_name = from_email
            if "<" in from_email:
                sender_name = from_email.split("<")[0].strip().strip('"')
            if not sender_name:
                sender_name = from_email

            payload = {
                "title": f"New email from {sender_name}",
                "body": msg.get("subject", "(no subject)"),
                "url": f"/?message={msg.get('id', '')}",
                "tag": "new-email",
            }

            for sub in subscriptions:
                if self._send_push(sub, payload):
                    sent_count += 1

        if sent_count > 0:
            logger.info(
                f"Sent {sent_count} push notification(s) for "
                f"{len(messages_to_notify)} new message(s)"
            )

        return sent_count


def create_push_service(
    database: Database,
    config: Dict,
) -> Optional[PushService]:
    """Create a PushService from config, or None if push is not enabled.

    Args:
        database: Database instance
        config: Application config dict

    Returns:
        PushService instance, or None if push is disabled/unconfigured
    """
    push_config = config.get("push", {})
    if not push_config.get("enable"):
        return None

    private_key_file = push_config.get("vapidPrivateKeyFile", "")
    public_key = push_config.get("vapidPublicKey", "")
    contact_email = push_config.get("contactEmail", "")

    if not private_key_file or not public_key or not contact_email:
        logger.warning("Push config incomplete — push notifications disabled")
        return None

    return PushService(
        database=database,
        vapid_private_key_file=private_key_file,
        vapid_public_key=public_key,
        contact_email=contact_email,
    )
