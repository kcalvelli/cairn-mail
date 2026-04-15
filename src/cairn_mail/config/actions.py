"""Action tag registry and built-in action definitions."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ActionDefinition:
    """Definition of an action tag that maps to an MCP tool call."""

    name: str
    description: str
    server: str
    tool: str
    extraction_prompt: str = ""
    default_args: Dict = field(default_factory=dict)
    enabled: bool = True


# Built-in extraction prompts
_CONTACT_EXTRACTION_PROMPT = """
Analyze this email and extract contact information for the SENDER.

EMAIL CONTENT:
Subject: {subject}
From: {from_email}
To: {to_emails}
Date: {date}
Body:
{body}

Extract the sender's contact details from the email content, signature, and headers.
Return ONLY a JSON object with these fields (omit OPTIONAL fields you cannot determine):

{{
  "formatted_name": "Full Name",
  "first_name": "First",
  "last_name": "Last",
  "emails": ["email@example.com"],
  "organization": "Company Name",
  "title": "Job Title",
  "phones": [{{"type": "WORK", "number": "+1-555-1234"}}],
  "notes": "Met via email about [topic]"
}}

RULES:
1. "formatted_name" and "emails" are REQUIRED - always include them
2. The email address MUST come from the From header
3. For formatted_name: use the display name from the From header, or derive from the email address
4. Look for organization, title, and phone in the email signature
5. If no signature, use what you can determine from the email address and content
6. Do NOT include phone entries with null numbers - omit phones entirely if unknown
7. Return ONLY valid JSON, no markdown or explanation
"""

_REMINDER_EXTRACTION_PROMPT = """
Analyze this email and extract details for creating a calendar reminder.

TODAY'S DATE: {current_date}

EMAIL CONTENT:
Subject: {subject}
From: {from_email}
To: {to_emails}
Date: {date}
Body:
{body}

Create a calendar reminder based on any dates, deadlines, or events mentioned.
Return ONLY a JSON object with these fields:

{{
  "summary": "Brief description of what to remember",
  "start": "2026-02-15T09:00:00",
  "end": "2026-02-15T09:30:00",
  "description": "Details from the email",
  "location": "Location if mentioned"
}}

RULES:
1. The summary should be concise but descriptive (e.g., "Payment due - Invoice #1234")
2. Today's date is {current_date}. Use this as reference for all date calculations
3. If a specific date is mentioned, use it for start. If only a deadline, set reminder for that date at 9:00 AM
4. If no end time, set it 30 minutes after start
5. Include relevant context from the email in the description
6. Use ISO 8601 format for dates (YYYY-MM-DDTHH:MM:SS)
7. Dates MUST be valid calendar dates. Check that the day exists in that month (e.g., February has 28 days, or 29 in leap years)
8. If no date can be determined, set start to tomorrow at 9:00 AM
9. Return ONLY valid JSON, no markdown or explanation
"""


DEFAULT_ACTIONS: Dict[str, ActionDefinition] = {
    "add-contact": ActionDefinition(
        name="add-contact",
        description="Create a contact from this email's sender",
        server="mcp-dav",
        tool="create_contact",
        extraction_prompt=_CONTACT_EXTRACTION_PROMPT,
        default_args={},
    ),
    "create-reminder": ActionDefinition(
        name="create-reminder",
        description="Create a calendar reminder from this email",
        server="mcp-dav",
        tool="create_event",
        extraction_prompt=_REMINDER_EXTRACTION_PROMPT,
        default_args={},
    ),
}

# Maps gateway config keys to the built-in action + tool arg they inject into
_GATEWAY_DEFAULTS_MAP = {
    "addressbook": ("add-contact", "addressbook"),
    "calendar": ("create-reminder", "calendar"),
}


def merge_actions(
    custom_actions: Optional[Dict[str, Dict]] = None,
    gateway_config: Optional[Dict] = None,
) -> Dict[str, ActionDefinition]:
    """Merge built-in actions with gateway defaults and user-defined custom actions.

    Priority (lowest to highest):
    1. Built-in defaults (empty default_args)
    2. Gateway config (addressbook, calendar injected into built-in actions)
    3. Custom action overrides from user config

    Args:
        custom_actions: Dict of action name -> config dict from user config
        gateway_config: Gateway config dict with addressbook/calendar names

    Returns:
        Merged dict of action name -> ActionDefinition
    """
    result = dict(DEFAULT_ACTIONS)

    # Inject gateway-level defaults into built-in actions
    if gateway_config:
        for gw_key, (action_name, arg_name) in _GATEWAY_DEFAULTS_MAP.items():
            value = gateway_config.get(gw_key)
            if value and action_name in result:
                action = result[action_name]
                merged_args = {**action.default_args, arg_name: value}
                result[action_name] = ActionDefinition(
                    name=action.name,
                    description=action.description,
                    server=action.server,
                    tool=action.tool,
                    extraction_prompt=action.extraction_prompt,
                    default_args=merged_args,
                    enabled=action.enabled,
                )

    if not custom_actions:
        return result

    for name, config in custom_actions.items():
        if name in result:
            # Override built-in: merge fields, custom takes precedence
            builtin = result[name]
            result[name] = ActionDefinition(
                name=name,
                description=config.get("description", builtin.description),
                server=config.get("server", builtin.server),
                tool=config.get("tool", builtin.tool),
                extraction_prompt=config.get("extractionPrompt", builtin.extraction_prompt),
                default_args=config.get("defaultArgs", builtin.default_args),
                enabled=config.get("enabled", builtin.enabled),
            )
        else:
            # New custom action
            result[name] = ActionDefinition(
                name=name,
                description=config.get("description", f"Custom action: {name}"),
                server=config["server"],
                tool=config["tool"],
                extraction_prompt=config.get("extractionPrompt", ""),
                default_args=config.get("defaultArgs", {}),
                enabled=config.get("enabled", True),
            )

    return result


def get_action_tag_names(actions: Dict[str, ActionDefinition]) -> List[str]:
    """Get list of action tag names from action definitions.

    Args:
        actions: Action definitions dict

    Returns:
        List of action tag names
    """
    return [name for name, action in actions.items() if action.enabled]
