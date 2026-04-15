"""Secure credential storage and loading."""

import json
import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CredentialError(Exception):
    """Raised when credential loading fails."""

    pass


class Credentials:
    """Secure credential loader supporting multiple secret management systems."""

    @staticmethod
    def check_file_permissions(file_path: Path) -> None:
        """Verify that credential file has restricted permissions.

        Args:
            file_path: Path to credential file

        Raises:
            CredentialError: If file permissions are too permissive
        """
        if not file_path.exists():
            raise CredentialError(f"Credential file not found: {file_path}")

        file_stat = file_path.stat()
        file_mode = stat.S_IMODE(file_stat.st_mode)

        # Check if file is world-readable or group-readable
        if file_mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH):
            logger.warning(
                f"Credential file {file_path} has permissive permissions ({oct(file_mode)}). "
                f"Recommended: 0600 (owner read/write only)"
            )

    @staticmethod
    def load_oauth_token(file_path: str | Path) -> Dict:
        """Load OAuth2 token from file.

        Supports JSON format with keys: access_token, refresh_token, client_id, client_secret.
        Optional key: token_expiry (ISO format timestamp or Unix timestamp)

        Args:
            file_path: Path to OAuth token file (decrypted by sops-nix/agenix/systemd-creds)

        Returns:
            Dict containing OAuth token data. If token_expiry is present, it will be
            converted to a datetime object in the 'expiry' key.

        Raises:
            CredentialError: If file cannot be read or parsed
        """
        file_path = Path(file_path).expanduser().resolve()

        try:
            Credentials.check_file_permissions(file_path)
        except CredentialError as e:
            logger.error(f"Permission check failed for {file_path}: {e}")
            raise

        try:
            with open(file_path, "r") as f:
                token_data = json.load(f)

            required_keys = ["access_token", "refresh_token", "client_id", "client_secret"]
            missing_keys = [key for key in required_keys if key not in token_data]

            if missing_keys:
                raise CredentialError(
                    f"OAuth token missing required keys: {', '.join(missing_keys)}"
                )

            # Parse token_expiry if present
            if "token_expiry" in token_data:
                expiry_value = token_data["token_expiry"]
                try:
                    if isinstance(expiry_value, (int, float)):
                        # Unix timestamp
                        token_data["expiry"] = datetime.fromtimestamp(
                            expiry_value, tz=timezone.utc
                        )
                    elif isinstance(expiry_value, str):
                        # ISO format string
                        # Handle both with and without timezone
                        if expiry_value.endswith("Z"):
                            expiry_value = expiry_value[:-1] + "+00:00"
                        token_data["expiry"] = datetime.fromisoformat(expiry_value)
                        # Ensure it's timezone-aware
                        if token_data["expiry"].tzinfo is None:
                            token_data["expiry"] = token_data["expiry"].replace(
                                tzinfo=timezone.utc
                            )
                    logger.debug(f"Token expiry: {token_data['expiry']}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not parse token_expiry '{expiry_value}': {e}")
                    # Don't fail - just won't have expiry info

            logger.debug(f"Successfully loaded OAuth token from {file_path}")
            return token_data

        except json.JSONDecodeError as e:
            raise CredentialError(f"Invalid JSON in OAuth token file {file_path}: {e}")
        except OSError as e:
            raise CredentialError(f"Failed to read OAuth token file {file_path}: {e}")

    @staticmethod
    def save_oauth_token(file_path: str | Path, token_data: Dict) -> None:
        """Save OAuth2 token to file (for token refresh).

        Args:
            file_path: Path to OAuth token file
            token_data: Updated token data. May contain 'expiry' as datetime object,
                       which will be serialized as 'token_expiry' ISO string.

        Raises:
            CredentialError: If file cannot be written
        """
        file_path = Path(file_path).expanduser().resolve()

        try:
            # Prepare data for JSON serialization
            save_data = token_data.copy()

            # Convert expiry datetime to ISO string for storage
            if "expiry" in save_data and isinstance(save_data["expiry"], datetime):
                save_data["token_expiry"] = save_data["expiry"].isoformat()
                del save_data["expiry"]  # Remove datetime object

            # Write with restricted permissions
            with open(file_path, "w") as f:
                json.dump(save_data, f, indent=2)

            # Ensure file has 0600 permissions
            os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
            logger.debug(f"Successfully saved OAuth token to {file_path}")

        except OSError as e:
            logger.warning(
                f"Failed to write updated OAuth token to {file_path}: {e}. "
                f"Token will need to be refreshed on next restart."
            )
            # Don't raise - this is not fatal, token will work until next restart

    @staticmethod
    def load_password(file_path: str | Path) -> str:
        """Load password from file (for IMAP/SMTP).

        Args:
            file_path: Path to password file (decrypted by sops-nix/agenix/systemd-creds)

        Returns:
            Password string

        Raises:
            CredentialError: If file cannot be read
        """
        file_path = Path(file_path).expanduser().resolve()

        try:
            Credentials.check_file_permissions(file_path)
        except CredentialError as e:
            logger.error(f"Permission check failed for {file_path}: {e}")
            raise

        try:
            with open(file_path, "r") as f:
                password = f.read().strip()

            if not password:
                raise CredentialError(f"Password file {file_path} is empty")

            logger.debug(f"Successfully loaded password from {file_path}")
            return password

        except OSError as e:
            raise CredentialError(f"Failed to read password file {file_path}: {e}")

    @staticmethod
    def detect_secret_manager(file_path: Path) -> Optional[str]:
        """Detect which secret manager is being used based on file path.

        Args:
            file_path: Path to credential file

        Returns:
            Secret manager name: "sops-nix", "agenix", "systemd-creds", or None
        """
        path_str = str(file_path)

        if "/run/credentials/" in path_str:
            return "systemd-creds"
        elif "/run/agenix/" in path_str or ".age" in path_str:
            return "agenix"
        elif "/run/secrets/" in path_str:
            return "sops-nix"

        return None

    @staticmethod
    def validate_credential_file(file_path: str | Path, account_name: str) -> None:
        """Validate that a credential file exists and is readable.

        Args:
            file_path: Path to credential file
            account_name: Name of account (for error messages)

        Raises:
            CredentialError: If file is not accessible
        """
        file_path = Path(file_path).expanduser().resolve()

        if not file_path.exists():
            secret_manager = Credentials.detect_secret_manager(file_path)
            hint = ""
            if secret_manager == "sops-nix":
                hint = " (Ensure sops-nix has decrypted secrets to /run/secrets/)"
            elif secret_manager == "agenix":
                hint = " (Ensure agenix has decrypted secrets to /run/agenix/)"
            elif secret_manager == "systemd-creds":
                hint = " (Ensure systemd LoadCredential is configured)"

            raise CredentialError(
                f"Credential file for account '{account_name}' not found: {file_path}{hint}"
            )

        if not os.access(file_path, os.R_OK):
            raise CredentialError(
                f"Credential file for account '{account_name}' is not readable: {file_path}"
            )

        logger.debug(f"Credential file validation passed for account '{account_name}'")
