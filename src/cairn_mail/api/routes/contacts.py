"""Contact search API endpoints for recipient autocomplete."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...gateway_client import GatewayClient, GatewayError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/contacts", tags=["contacts"])


class Contact(BaseModel):
    """Contact information for autocomplete."""

    name: str
    email: str
    organization: str | None = None


class ContactSearchResponse(BaseModel):
    """Response model for contact search."""

    contacts: list[Contact]


def _parse_contacts_result(result: dict[str, Any]) -> list[Contact]:
    """Parse contacts from mcp-gateway tool result.

    The gateway returns results in MCP format:
    {"result": [{"type": "text", "text": "...json..."}]}

    Args:
        result: Raw gateway response

    Returns:
        List of Contact objects
    """
    contacts = []
    result_items = result.get("result", [])

    if not isinstance(result_items, list):
        return contacts

    for item in result_items:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue

        text = item.get("text", "")
        if not text:
            continue

        try:
            data = json.loads(text)
            # Handle both list and dict responses
            contact_list = data if isinstance(data, list) else data.get("contacts", [])

            for c in contact_list:
                # mcp-dav returns formatted_name, emails array
                name = c.get("formatted_name") or c.get("name", "")
                emails = c.get("emails", [])
                email = emails[0] if emails else c.get("email", "")
                org = c.get("organization") or c.get("org")

                if email:  # Only include contacts with emails
                    contacts.append(Contact(
                        name=name or email,
                        email=email,
                        organization=org,
                    ))
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.debug(f"Failed to parse contact result: {e}")
            continue

    return contacts


@router.get("/search", response_model=ContactSearchResponse)
async def search_contacts(request: Request, q: str = ""):
    """Search contacts for recipient autocomplete.

    Proxies search to mcp-gateway's dav/search_contacts tool.
    Returns empty results (not an error) when gateway unavailable.

    Args:
        request: FastAPI request
        q: Search query (name or email)

    Returns:
        ContactSearchResponse with matching contacts
    """
    # Minimum query length
    if len(q) < 2:
        return ContactSearchResponse(contacts=[])

    # Check if gateway integration is enabled
    config = getattr(request.app.state, "config", None) or {}
    gateway_config = config.get("gateway", {})

    if not gateway_config.get("enable", False):
        logger.debug("Gateway not enabled, returning empty contacts")
        return ContactSearchResponse(contacts=[])

    # Create gateway client
    gateway_url = gateway_config.get("url", "http://localhost:8085")
    gateway = GatewayClient(base_url=gateway_url, timeout=2)

    try:
        # Call mcp-dav's search_contacts tool
        result = gateway.call_tool("mcp-dav", "search_contacts", {"query": q})
        contacts = _parse_contacts_result(result)
        return ContactSearchResponse(contacts=contacts)

    except GatewayError as e:
        logger.warning(f"Contact search failed: {e}")
        return ContactSearchResponse(contacts=[])
    except Exception as e:
        logger.error(f"Unexpected error in contact search: {e}", exc_info=True)
        return ContactSearchResponse(contacts=[])
