"""Configuration file loader for Nix-generated configuration."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..db.database import Database
from .actions import ActionDefinition, merge_actions
from .tags import DEFAULT_TAGS, merge_tags, get_tag_color, CATEGORY_COLORS

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Load Nix-generated configuration and sync to database."""

    _cached_config: Optional[Dict] = None
    _cached_path: Optional[Path] = None

    @classmethod
    def load_config(cls, config_path: Optional[Path] = None) -> Dict:
        """
        Load config.yaml (JSON format) from XDG config directory.

        Args:
            config_path: Path to config file. Defaults to ~/.config/cairn-mail/config.yaml

        Returns:
            Configuration dictionary, or empty dict if file doesn't exist
        """
        if config_path is None:
            config_path = Path.home() / ".config" / "cairn-mail" / "config.yaml"

        # Return cached config if same path
        if cls._cached_config is not None and cls._cached_path == config_path:
            return cls._cached_config

        if not config_path.exists():
            logger.debug(f"Config file not found: {config_path}")
            return {}

        logger.info(f"Loading configuration from {config_path}")
        with open(config_path) as f:
            cls._cached_config = json.load(f)
            cls._cached_path = config_path
            return cls._cached_config

    @classmethod
    def get_ai_config(cls, config: Optional[Dict] = None) -> Dict:
        """
        Get AI configuration from loaded config.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            AI configuration dict with keys: model, endpoint, temperature, tags
        """
        if config is None:
            config = cls.load_config()

        ai_config = config.get("ai", {})
        return {
            "model": ai_config.get("model", "llama3.2"),
            "endpoint": ai_config.get("endpoint", "http://localhost:11434"),
            "temperature": ai_config.get("temperature", 0.3),
            "tags": ai_config.get("tags", []),
        }

    @classmethod
    def get_custom_tags(cls, config: Optional[Dict] = None) -> Optional[List[Dict[str, str]]]:
        """
        Get custom tags from config for AI classification.

        DEPRECATED: Use get_merged_tags() instead for the full tag list.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            List of tag dicts with 'name' and 'description', or None if not configured
        """
        ai_config = cls.get_ai_config(config)
        tags = ai_config.get("tags", [])

        if not tags:
            return None

        # Ensure tags have required fields
        validated_tags = []
        for tag in tags:
            if "name" in tag and "description" in tag:
                validated_tags.append({
                    "name": tag["name"],
                    "description": tag["description"],
                })
            else:
                logger.warning(f"Invalid tag config (missing name/description): {tag}")

        return validated_tags if validated_tags else None

    @classmethod
    def get_merged_tags(cls, config: Optional[Dict] = None) -> List[Dict[str, str]]:
        """
        Get the merged tag taxonomy based on configuration.

        Combines default tags (if enabled) with custom tags, minus exclusions.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            List of tag dicts with 'name', 'description', and 'category'
        """
        if config is None:
            config = cls.load_config()

        ai_config = config.get("ai", {})

        # Check if defaults should be used (default: True for new behavior)
        use_defaults = ai_config.get("useDefaultTags", True)

        # Get custom tags
        custom_tags = ai_config.get("tags", [])

        # Get exclusion list
        exclude_tags = ai_config.get("excludeTags", [])

        # Merge tags
        merged = merge_tags(
            use_defaults=use_defaults,
            custom_tags=custom_tags,
            exclude_tags=exclude_tags,
        )

        logger.debug(
            f"Merged tags: {len(merged)} total "
            f"(defaults={'yes' if use_defaults else 'no'}, "
            f"custom={len(custom_tags)}, excluded={len(exclude_tags)})"
        )

        return merged

    @classmethod
    def get_label_colors(cls, config: Optional[Dict] = None) -> Dict[str, str]:
        """
        Get label color mappings for all tags.

        Combines category-based defaults with explicit overrides.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            Dict mapping tag name to color string
        """
        if config is None:
            config = cls.load_config()

        ai_config = config.get("ai", {})
        overrides = ai_config.get("labelColors", {})

        # Get all merged tags
        tags = cls.get_merged_tags(config)

        # Build color mapping
        colors = {}
        for tag in tags:
            colors[tag["name"]] = get_tag_color(
                tag["name"],
                tag.get("category"),
                overrides,
            )

        return colors

    @classmethod
    def get_label_prefix(cls, config: Optional[Dict] = None) -> str:
        """
        Get the label prefix for AI-generated labels.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            Label prefix string (default: "AI")
        """
        if config is None:
            config = cls.load_config()

        ai_config = config.get("ai", {})
        return ai_config.get("labelPrefix", "AI")

    @classmethod
    def get_sync_config(cls, config: Optional[Dict] = None, account_id: Optional[str] = None) -> Dict:
        """
        Get sync configuration, with optional per-account override.

        Args:
            config: Configuration dict, or None to load from default path
            account_id: Account ID to check for overrides

        Returns:
            Sync configuration dict with frequency, maxMessagesPerSync, enableWebhooks
        """
        if config is None:
            config = cls.load_config()

        # Global defaults
        global_sync = config.get("sync", {})
        result = {
            "frequency": global_sync.get("frequency", "5m"),
            "maxMessagesPerSync": global_sync.get("maxMessagesPerSync", 100),
            "enableWebhooks": global_sync.get("enableWebhooks", False),
        }

        # Check for per-account override
        if account_id:
            accounts = config.get("accounts", {})
            account_config = accounts.get(account_id, {})
            account_sync = account_config.get("sync", {})

            # Override with account-specific settings
            if "frequency" in account_sync:
                result["frequency"] = account_sync["frequency"]
            if "maxMessagesPerSync" in account_sync:
                result["maxMessagesPerSync"] = account_sync["maxMessagesPerSync"]
            if "enableWebhooks" in account_sync:
                result["enableWebhooks"] = account_sync["enableWebhooks"]

        return result

    @classmethod
    def get_gateway_config(cls, config: Optional[Dict] = None) -> Dict:
        """Get mcp-gateway configuration.

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            Gateway configuration dict with url
        """
        if config is None:
            config = cls.load_config()

        gateway_config = config.get("gateway", {})
        return {
            "url": gateway_config.get("url", "http://localhost:8085"),
        }

    @classmethod
    def get_actions_config(cls, config: Optional[Dict] = None) -> Dict[str, ActionDefinition]:
        """Get merged action definitions (built-in + custom).

        Args:
            config: Configuration dict, or None to load from default path

        Returns:
            Dict of action name -> ActionDefinition
        """
        if config is None:
            config = cls.load_config()

        custom_actions = config.get("actions", {})
        return merge_actions(custom_actions if custom_actions else None)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the cached configuration."""
        cls._cached_config = None
        cls._cached_path = None

    @staticmethod
    def sync_to_database(db: Database, config: Dict) -> None:
        """
        Sync configuration accounts to database (create/update).

        This is idempotent - accounts are created if they don't exist,
        or updated if they do. Existing database state (messages, classifications)
        is preserved.

        Args:
            db: Database instance
            config: Configuration dictionary from load_config()
        """
        if not config:
            logger.debug("No configuration to sync")
            return

        config_accounts = config.get("accounts", {})
        if not config_accounts:
            logger.warning("No accounts in configuration")
            return

        logger.info(f"Syncing {len(config_accounts)} accounts to database")

        for account_id, account_config in config_accounts.items():
            try:
                # Merge credential_file and real_name into settings
                settings = account_config.get("settings", {}).copy()
                if "credential_file" in account_config:
                    settings["credential_file"] = account_config["credential_file"]
                if "real_name" in account_config:
                    settings["real_name"] = account_config["real_name"]

                db.create_or_update_account(
                    account_id=account_id,
                    name=account_config.get("name", account_id),
                    email=account_config["email"],
                    provider=account_config["provider"],
                    settings=settings,
                )
                logger.debug(f"Synced account: {account_id} ({account_config['provider']})")
            except Exception as e:
                logger.error(f"Failed to sync account {account_id}: {e}")
                raise

        # Prune ghost accounts: anything in the DB that isn't in the config
        # anymore gets removed, along with all of its messages, classifications,
        # feedback, drafts, pending ops, etc. (via FK cascade). Renames are
        # already handled inside create_or_update_account, so by this point the
        # renamed account is in `config_accounts` under its new ID.
        configured_ids = set(config_accounts.keys())
        for db_account in db.list_accounts():
            if db_account.id in configured_ids:
                continue
            logger.info(
                f"Removing ghost account {db_account.id!r} ({db_account.email}) — "
                "no longer present in configuration"
            )
            db.delete_account(db_account.id)
