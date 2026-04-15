"""HTTP client for mcp-gateway REST API."""

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_GATEWAY_URL = "http://localhost:8085"


class GatewayError(Exception):
    """Error communicating with mcp-gateway."""

    pass


class GatewayClient:
    """HTTP client for calling MCP tools via mcp-gateway's REST API."""

    def __init__(self, base_url: str = DEFAULT_GATEWAY_URL, timeout: int = 30):
        """Initialize gateway client.

        Args:
            base_url: mcp-gateway base URL
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._available_tools: Optional[List[Dict[str, Any]]] = None

    def discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available tools from mcp-gateway.

        Returns:
            List of tool dicts with server, name, description, and schema

        Raises:
            GatewayError: If gateway is unreachable or returns an error
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/tools",
                timeout=self.timeout,
            )
            response.raise_for_status()
            self._available_tools = response.json()
            logger.info(f"Discovered {len(self._available_tools)} tools from mcp-gateway")
            return self._available_tools
        except requests.exceptions.ConnectionError:
            raise GatewayError(f"Cannot connect to mcp-gateway at {self.base_url}")
        except requests.exceptions.Timeout:
            raise GatewayError(f"Timeout connecting to mcp-gateway at {self.base_url}")
        except requests.exceptions.HTTPError as e:
            raise GatewayError(f"mcp-gateway returned error: {e}")
        except Exception as e:
            raise GatewayError(f"Unexpected error discovering tools: {e}")

    def has_tool(self, server: str, tool: str) -> bool:
        """Check if a specific tool is available.

        Args:
            server: MCP server ID (e.g., "dav")
            tool: Tool name (e.g., "create_contact")

        Returns:
            True if the tool is available
        """
        if self._available_tools is None:
            try:
                self.discover_tools()
            except GatewayError:
                return False

        for t in self._available_tools or []:
            if t.get("server_id") == server and t.get("name") == tool:
                return True
        return False

    def call_tool(self, server: str, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool via mcp-gateway.

        Args:
            server: MCP server ID (e.g., "dav")
            tool: Tool name (e.g., "create_contact")
            arguments: Tool arguments

        Returns:
            Tool result dict

        Raises:
            GatewayError: If the call fails
        """
        url = f"{self.base_url}/api/tools/{server}/{tool}"
        try:
            response = requests.post(
                url,
                json={"arguments": arguments},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()

            # Check for tool-level errors in the gateway response
            # Gateway returns HTTP 200 even when the MCP tool itself errors
            if isinstance(result, dict):
                # Check for explicit error field
                if result.get("error"):
                    raise GatewayError(
                        f"Tool {server}/{tool} returned error: {result['error']}"
                    )
                # Check result content for errors reported in tool output
                result_items = result.get("result", [])
                if isinstance(result_items, list):
                    for item in result_items:
                        text = item.get("text", "") if isinstance(item, dict) else ""
                        if not text:
                            continue
                        text_lower = text.lower()
                        # Detect validation errors, missing args, and tool-reported errors
                        if any(indicator in text_lower for indicator in [
                            "validation error",
                            "missing required",
                            '"error"',       # JSON error field in tool output
                            "'error'",       # Alternative quoting
                            "not found:",    # Resource not found errors
                        ]) or text_lower.startswith("error"):
                            raise GatewayError(
                                f"Tool {server}/{tool} error: {text}"
                            )

            return result
        except requests.exceptions.ConnectionError:
            raise GatewayError(f"Cannot connect to mcp-gateway at {self.base_url}")
        except requests.exceptions.Timeout:
            raise GatewayError(f"Timeout calling {server}/{tool}")
        except requests.exceptions.HTTPError as e:
            raise GatewayError(f"Tool call {server}/{tool} failed: {e}")
        except Exception as e:
            raise GatewayError(f"Unexpected error calling {server}/{tool}: {e}")
