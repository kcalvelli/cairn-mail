"""Action agent for processing action tags via mcp-gateway.

When users add action tags (e.g., "add-contact", "create-reminder") to emails,
this agent extracts relevant data using an OpenAI-compatible LLM API and executes
the corresponding MCP tool via mcp-gateway's REST API.
"""

import calendar
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from .config.actions import ActionDefinition
from .db.database import Database
from .db.models import Message
from .gateway_client import GatewayClient, GatewayError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class ActionAgent:
    """Processes action tags on emails by calling MCP tools via mcp-gateway."""

    def __init__(
        self,
        database: Database,
        gateway: GatewayClient,
        actions: Dict[str, ActionDefinition],
        ai_endpoint: str = "http://localhost:18789",
        ai_model: str = "claude-sonnet-4-20250514",
        ai_timeout: int = 60,
    ):
        """Initialize action agent.

        Args:
            database: Database instance
            gateway: GatewayClient instance for mcp-gateway communication
            actions: Dict of action name -> ActionDefinition
            ai_endpoint: OpenAI-compatible API endpoint
            ai_model: Model name for the API
            ai_timeout: Timeout for LLM requests
        """
        self.db = database
        self.gateway = gateway
        self.actions = actions
        self.ai_endpoint = ai_endpoint
        self.ai_model = ai_model
        self.ai_timeout = ai_timeout

    def get_action_tag_names(self) -> List[str]:
        """Get list of enabled action tag names.

        Returns:
            List of action tag names
        """
        return [name for name, action in self.actions.items() if action.enabled]

    def process_actions(
        self,
        account_id: str,
        max_actions: int = 10,
    ) -> Dict[str, int]:
        """Process pending action tags for an account.

        Finds messages with action tags, extracts data via LLM,
        and calls the corresponding MCP tool via mcp-gateway.

        Args:
            account_id: Account ID to process
            max_actions: Maximum actions to process per cycle

        Returns:
            Dict with counts: processed, succeeded, failed, skipped
        """
        stats = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0, "modified_messages": [], "action_results": []}

        action_tag_names = self.get_action_tag_names()
        if not action_tag_names:
            logger.debug("No action tags configured")
            return stats

        # Discover available tools from gateway
        try:
            self.gateway.discover_tools()
        except GatewayError as e:
            logger.warning(f"mcp-gateway unavailable, skipping action processing: {e}")
            return stats

        # Find messages with action tags
        messages = self.db.get_pending_action_messages(
            account_id=account_id,
            action_tag_names=action_tag_names,
            limit=max_actions,
        )

        if not messages:
            logger.debug("No messages with action tags to process")
            return stats

        logger.info(f"Processing action tags on {len(messages)} messages")

        for message in messages:
            # Get action tags on this message
            if not message.classification or not message.classification.tags:
                continue

            msg_action_tags = [
                t for t in message.classification.tags if t in action_tag_names
            ]

            for tag_name in msg_action_tags:
                action = self.actions.get(tag_name)
                if not action:
                    continue

                stats["processed"] += 1
                result = self._process_single_action(message, action, account_id)

                if result == "success":
                    stats["succeeded"] += 1
                    if message.id not in stats["modified_messages"]:
                        stats["modified_messages"].append(message.id)
                elif result == "failed":
                    stats["failed"] += 1
                elif result == "skipped":
                    stats["skipped"] += 1

                # Track per-action result for notifications
                stats["action_results"].append({
                    "action_name": action.name,
                    "status": result,
                    "message_subject": message.subject or "(no subject)",
                })

        logger.info(
            f"Action processing complete: {stats['succeeded']} succeeded, "
            f"{stats['failed']} failed, {stats['skipped']} skipped"
        )
        return stats

    def _process_single_action(
        self,
        message: Message,
        action: ActionDefinition,
        account_id: str,
    ) -> str:
        """Process a single action tag on a message.

        Args:
            message: Message with the action tag
            action: Action definition
            account_id: Account ID

        Returns:
            Status string: "success", "failed", or "skipped"
        """
        log_id = str(uuid.uuid4())

        # Check retry count
        attempt_count = self.db.get_action_attempt_count(message.id, action.name)
        if attempt_count >= MAX_RETRIES:
            logger.warning(
                f"Max retries ({MAX_RETRIES}) exceeded for {action.name} on {message.id}"
            )
            self.db.store_action_log(
                log_id=log_id,
                message_id=message.id,
                account_id=account_id,
                action_name=action.name,
                server=action.server,
                tool=action.tool,
                status="skipped",
                error=f"Max retries ({MAX_RETRIES}) exceeded",
                attempts=attempt_count,
            )
            return "skipped"

        # Check if the required tool is available
        if not self.gateway.has_tool(action.server, action.tool):
            logger.warning(
                f"Tool {action.server}/{action.tool} not available for action {action.name}"
            )
            self.db.store_action_log(
                log_id=log_id,
                message_id=message.id,
                account_id=account_id,
                action_name=action.name,
                server=action.server,
                tool=action.tool,
                status="skipped",
                error=f"Tool {action.server}/{action.tool} not available in mcp-gateway",
            )
            return "skipped"

        # Extract data from email using LLM
        extracted_data = None
        try:
            extracted_data = self._extract_data(message, action)
        except Exception as e:
            logger.error(f"Data extraction failed for {action.name} on {message.id}: {e}")
            self.db.store_action_log(
                log_id=log_id,
                message_id=message.id,
                account_id=account_id,
                action_name=action.name,
                server=action.server,
                tool=action.tool,
                status="failed",
                error=f"Extraction failed: {e}",
                attempts=attempt_count + 1,
            )
            return "failed"

        # Merge extracted data with default args (defaults don't override extracted)
        arguments = {**action.default_args, **extracted_data}

        # Ensure required fields for known actions
        if action.tool == "create_contact" and not arguments.get("formatted_name"):
            # Derive formatted_name from email or From header
            from_email = message.from_email or ""
            if "<" in from_email:
                # "Display Name <email>" format
                name_part = from_email.split("<")[0].strip().strip('"')
                if name_part:
                    arguments["formatted_name"] = name_part
            if not arguments.get("formatted_name"):
                # Fall back to email local part
                email = arguments.get("emails", [from_email])[0] if arguments.get("emails") else from_email
                arguments["formatted_name"] = email.split("@")[0].replace(".", " ").title()

        # Clean up null values and empty collections that can cause validation errors
        cleaned = {}
        for k, v in arguments.items():
            if v is None:
                continue
            # Remove phone entries with null numbers
            if k == "phones" and isinstance(v, list):
                v = [p for p in v if isinstance(p, dict) and p.get("number")]
                if not v:
                    continue
            cleaned[k] = v
        arguments = cleaned

        # Validate and fix date fields for calendar actions
        if action.tool == "create_event":
            for date_field in ("start", "end"):
                if date_field in arguments:
                    arguments[date_field] = self._fix_date(arguments[date_field])

        # Call the MCP tool via gateway
        try:
            tool_result = self.gateway.call_tool(action.server, action.tool, arguments)
            logger.info(f"Action {action.name} succeeded for message {message.id}")

            # Log success
            self.db.store_action_log(
                log_id=log_id,
                message_id=message.id,
                account_id=account_id,
                action_name=action.name,
                server=action.server,
                tool=action.tool,
                status="success",
                extracted_data=extracted_data,
                tool_result=tool_result,
                attempts=attempt_count + 1,
            )

            # Remove the action tag from the message
            self._remove_action_tag(message, action.name)

            return "success"

        except GatewayError as e:
            logger.error(f"Tool call failed for {action.name} on {message.id}: {e}")
            self.db.store_action_log(
                log_id=log_id,
                message_id=message.id,
                account_id=account_id,
                action_name=action.name,
                server=action.server,
                tool=action.tool,
                status="failed",
                extracted_data=extracted_data,
                error=f"Tool call failed: {e}",
                attempts=attempt_count + 1,
            )
            return "failed"

    def _extract_data(
        self,
        message: Message,
        action: ActionDefinition,
    ) -> Dict[str, Any]:
        """Extract structured data from an email using the LLM API.

        Uses the action's extraction prompt to instruct the LLM on what
        data to extract from the email content.

        Args:
            message: Email message to extract data from
            action: Action definition with extraction prompt

        Returns:
            Extracted data as a dictionary

        Raises:
            ValueError: If extraction returns invalid JSON
            requests.RequestException: If the LLM API is unreachable
        """
        if not action.extraction_prompt:
            # No extraction prompt = no data to extract, just use defaults
            return {}

        # Format the extraction prompt with email data
        body = message.body_text or message.snippet or ""
        to_emails = ", ".join(message.to_emails) if message.to_emails else ""
        now = datetime.now()

        prompt = action.extraction_prompt.format(
            subject=message.subject or "",
            from_email=message.from_email or "",
            to_emails=to_emails,
            date=str(message.date) if message.date else "",
            body=body[:3000],  # Limit body to avoid token overflow
            current_date=now.strftime("%Y-%m-%d %A"),  # e.g. "2026-01-29 Thursday"
        )

        response = requests.post(
            f"{self.ai_endpoint}/v1/chat/completions",
            json={
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,  # Low temperature for structured extraction
                "response_format": {"type": "json_object"},
            },
            timeout=self.ai_timeout,
        )
        response.raise_for_status()

        result = response.json()
        response_text = result["choices"][0]["message"]["content"] or ""
        # Strip markdown fences some backends add despite response_format
        stripped = response_text.strip()
        fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", stripped, re.DOTALL)
        if fence_match:
            response_text = fence_match.group(1).strip()

        try:
            extracted = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\nResponse: {response_text[:200]}")

        if not isinstance(extracted, dict):
            raise ValueError(f"Expected dict from extraction, got {type(extracted).__name__}")

        # Remove None values
        extracted = {k: v for k, v in extracted.items() if v is not None}

        logger.debug(f"Extracted {len(extracted)} fields for {action.name}: {list(extracted.keys())}")
        return extracted

    def _remove_action_tag(self, message: Message, tag_name: str) -> None:
        """Remove an action tag from a message's classification.

        Args:
            message: Message to update
            tag_name: Tag name to remove
        """
        if not message.classification or not message.classification.tags:
            return

        updated_tags = [t for t in message.classification.tags if t != tag_name]
        self.db.update_message_tags(message.id, updated_tags)
        logger.debug(f"Removed action tag '{tag_name}' from message {message.id}")

    @staticmethod
    def _fix_date(date_str: str) -> str:
        """Validate and fix a date string from LLM extraction.

        Clamps out-of-range days to the last valid day of the month
        (e.g., Feb 29 on a non-leap year becomes Feb 28).

        Args:
            date_str: ISO 8601 date string (e.g., "2026-02-29T09:00:00")

        Returns:
            Valid date string, fixed if necessary
        """
        try:
            # Try parsing as-is — if valid, return unchanged
            datetime.fromisoformat(date_str)
            return date_str
        except ValueError:
            pass

        # Try to fix invalid day-of-month
        try:
            # Split off time portion
            if "T" in date_str:
                date_part, time_part = date_str.split("T", 1)
            else:
                date_part = date_str
                time_part = None

            parts = date_part.split("-")
            if len(parts) == 3:
                year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                # Clamp day to last valid day of the month
                max_day = calendar.monthrange(year, month)[1]
                if day > max_day:
                    logger.warning(
                        f"Fixing invalid date {date_str}: day {day} clamped to {max_day}"
                    )
                    day = max_day
                fixed = f"{year:04d}-{month:02d}-{day:02d}"
                if time_part:
                    fixed = f"{fixed}T{time_part}"
                return fixed
        except (ValueError, IndexError):
            pass

        # Can't fix it — return original and let the gateway report the error
        logger.warning(f"Could not validate date: {date_str}")
        return date_str
