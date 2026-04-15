"""Default tag taxonomy for AI email classification."""

from typing import Dict, List, Optional

# Default expanded tag taxonomy (35 tags)
# Each tag has a name, description, and category for color derivation
DEFAULT_TAGS: List[Dict[str, str]] = [
    # Priority
    {"name": "urgent", "description": "Time-sensitive, requires immediate attention", "category": "priority"},
    {"name": "important", "description": "High priority but not time-critical", "category": "priority"},
    {"name": "review", "description": "Needs review or decision", "category": "priority"},

    # Work
    {"name": "work", "description": "General work-related emails", "category": "work"},
    {"name": "project", "description": "Project updates and discussions", "category": "work"},
    {"name": "meeting", "description": "Meeting invites, agendas, notes", "category": "work"},
    {"name": "deadline", "description": "Tasks with deadlines", "category": "work"},

    # Personal
    {"name": "personal", "description": "Personal correspondence", "category": "personal"},
    {"name": "family", "description": "Family-related emails", "category": "personal"},
    {"name": "friends", "description": "Emails from friends", "category": "personal"},
    {"name": "hobby", "description": "Hobbies and personal interests", "category": "personal"},

    # Finance
    {"name": "finance", "description": "Financial matters", "category": "finance"},
    {"name": "invoice", "description": "Invoices and bills", "category": "finance"},
    {"name": "payment", "description": "Payment confirmations and receipts", "category": "finance"},
    {"name": "expense", "description": "Expense reports and reimbursements", "category": "finance"},

    # Shopping
    {"name": "shopping", "description": "Order confirmations, tracking", "category": "shopping"},
    {"name": "receipt", "description": "Purchase receipts", "category": "shopping"},
    {"name": "shipping", "description": "Shipping notifications", "category": "shopping"},

    # Travel
    {"name": "travel", "description": "General travel emails", "category": "travel"},
    {"name": "booking", "description": "Reservations and bookings", "category": "travel"},
    {"name": "itinerary", "description": "Trip itineraries", "category": "travel"},
    {"name": "flight", "description": "Flight confirmations and updates", "category": "travel"},

    # Developer
    {"name": "dev", "description": "Developer notifications", "category": "developer"},
    {"name": "github", "description": "GitHub notifications", "category": "developer"},
    {"name": "ci", "description": "CI/CD build notifications", "category": "developer"},
    {"name": "alert", "description": "System alerts and monitoring", "category": "developer"},

    # Marketing
    {"name": "marketing", "description": "Marketing emails", "category": "marketing"},
    {"name": "newsletter", "description": "Newsletter subscriptions", "category": "marketing"},
    {"name": "promotion", "description": "Promotional offers", "category": "marketing"},
    {"name": "announcement", "description": "Company/product announcements", "category": "marketing"},

    # Social
    {"name": "social", "description": "Social media notifications", "category": "social"},
    {"name": "notification", "description": "App and service notifications", "category": "social"},
    {"name": "update", "description": "Account and service updates", "category": "social"},
    {"name": "reminder", "description": "Reminders and follow-ups", "category": "social"},

    # System
    {"name": "junk", "description": "Spam and unwanted mail", "category": "system"},
]

# Category to color mapping for label derivation
CATEGORY_COLORS: Dict[str, str] = {
    "priority": "red",
    "work": "blue",
    "personal": "purple",
    "finance": "green",
    "shopping": "yellow",
    "travel": "cyan",
    "developer": "cyan",
    "marketing": "orange",
    "social": "teal",
    "system": "gray",
    "action": "amber",
}

# Color palette for hash-based color assignment (for custom tags)
COLOR_PALETTE = ["blue", "green", "purple", "orange", "cyan", "teal", "magenta", "brown"]


def get_tag_color(tag_name: str, category: Optional[str] = None, overrides: Optional[Dict[str, str]] = None) -> str:
    """
    Get the color for a tag.

    Priority:
    1. Explicit override from labelColors config
    2. Category-based color if category is known
    3. Hash-based color from palette

    Args:
        tag_name: Name of the tag
        category: Category of the tag (if known)
        overrides: Dict of tag_name -> color overrides

    Returns:
        Color string (e.g., "blue", "red")
    """
    # Check for explicit override
    if overrides and tag_name in overrides:
        return overrides[tag_name]

    # Use category color if available
    if category and category in CATEGORY_COLORS:
        return CATEGORY_COLORS[category]

    # Fall back to hash-based color
    hash_value = sum(ord(c) for c in tag_name)
    return COLOR_PALETTE[hash_value % len(COLOR_PALETTE)]


def merge_tags(
    use_defaults: bool = True,
    custom_tags: Optional[List[Dict[str, str]]] = None,
    exclude_tags: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """
    Merge default and custom tags, with exclusions.

    Args:
        use_defaults: Whether to include default tags
        custom_tags: Additional user-defined tags
        exclude_tags: Tag names to exclude from defaults

    Returns:
        Merged list of tags (name, description, category)
    """
    result = []
    seen_names = set()
    exclude_set = set(exclude_tags or [])

    # Start with defaults if enabled
    if use_defaults:
        for tag in DEFAULT_TAGS:
            if tag["name"] not in exclude_set:
                result.append(tag.copy())
                seen_names.add(tag["name"])

    # Add custom tags (can override default descriptions)
    if custom_tags:
        for tag in custom_tags:
            tag_name = tag.get("name", "")
            if not tag_name:
                continue

            # If tag exists in defaults, update description
            existing = next((t for t in result if t["name"] == tag_name), None)
            if existing:
                existing["description"] = tag.get("description", existing["description"])
            else:
                # Add new custom tag
                result.append({
                    "name": tag_name,
                    "description": tag.get("description", f"Custom tag: {tag_name}"),
                    "category": tag.get("category", "custom"),
                })
                seen_names.add(tag_name)

    return result


def get_tag_names(tags: List[Dict[str, str]]) -> List[str]:
    """Extract just the tag names from a tag list."""
    return [tag["name"] for tag in tags]


def get_tags_for_prompt(tags: List[Dict[str, str]]) -> str:
    """
    Format tags for inclusion in AI prompt.

    Only includes non-action tags (action tags are user-assigned only).

    Args:
        tags: List of tag dicts with name and description

    Returns:
        Formatted string for prompt
    """
    lines = []
    for tag in tags:
        # Exclude action tags from AI prompt
        if tag.get("category") == "action":
            continue
        lines.append(f"- {tag['name']}: {tag['description']}")
    return "\n".join(lines)


def action_tags_from_definitions(action_definitions: Dict) -> List[Dict[str, str]]:
    """Convert action definitions to tag format for the tag system.

    Action tags are a special category that the AI classifier does NOT use.
    They are only assigned manually by users and trigger MCP tool calls.

    Args:
        action_definitions: Dict of action name -> ActionDefinition

    Returns:
        List of tag dicts with name, description, and category="action"
    """
    tags = []
    for name, action in action_definitions.items():
        if action.enabled:
            tags.append({
                "name": name,
                "description": action.description,
                "category": "action",
            })
    return tags
