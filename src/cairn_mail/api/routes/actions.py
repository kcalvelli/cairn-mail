"""Action tag API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    ActionDefinitionResponse,
    ActionLogEntryResponse,
    ActionLogResponse,
    ActionsListResponse,
)
from ...config.actions import merge_actions
from ...gateway_client import GatewayClient, GatewayError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("/available", response_model=ActionsListResponse)
async def list_available_actions(request: Request):
    """List all configured action tags with availability status.

    Returns all action definitions (built-in + custom) and indicates
    whether each action's MCP tool is available in mcp-gateway.
    """
    try:
        # Check if gateway integration is enabled
        config = getattr(request.app.state, 'config', None) or {}
        if not (isinstance(config, dict) and config.get("gateway", {}).get("enable", False)):
            return ActionsListResponse(actions=[])

        # Get actions from config
        gateway_config = config.get("gateway", {})
        custom_actions = config.get("actions", {})
        actions = merge_actions(
            custom_actions if custom_actions else None,
            gateway_config=gateway_config,
        )

        # Check tool availability via gateway
        gateway_url = gateway_config.get("url", "http://localhost:8085")
        gateway = GatewayClient(base_url=gateway_url, timeout=5)

        try:
            gateway.discover_tools()
        except GatewayError:
            logger.warning("mcp-gateway unavailable for tool availability check")

        # Build response
        action_list = []
        for name, action in actions.items():
            available = gateway.has_tool(action.server, action.tool)
            action_list.append(ActionDefinitionResponse(
                name=name,
                description=action.description,
                server=action.server,
                tool=action.tool,
                enabled=action.enabled,
                available=available,
            ))

        return ActionsListResponse(actions=action_list)

    except Exception as e:
        logger.error(f"Error listing actions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log", response_model=ActionLogResponse)
async def get_action_log(
    request: Request,
    account_id: Optional[str] = None,
    message_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Query the action execution log.

    Returns action log entries sorted by most recent first.
    """
    db = request.app.state.db

    try:
        entries = db.get_action_log(
            account_id=account_id,
            message_id=message_id,
            limit=limit,
            offset=offset,
        )

        return ActionLogResponse(
            entries=[
                ActionLogEntryResponse(
                    id=entry.id,
                    message_id=entry.message_id,
                    account_id=entry.account_id,
                    action_name=entry.action_name,
                    server=entry.server,
                    tool=entry.tool,
                    status=entry.status,
                    error=entry.error,
                    extracted_data=entry.extracted_data,
                    tool_result=entry.tool_result,
                    attempts=entry.attempts,
                    processed_at=entry.processed_at.isoformat(),
                )
                for entry in entries
            ],
            total=len(entries),
        )

    except Exception as e:
        logger.error(f"Error getting action log: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/{log_id}")
async def retry_action(request: Request, log_id: str):
    """Retry a failed action by re-adding its tag to the message.

    Looks up the action log entry, re-adds the action tag to the message,
    and resets the retry counter so it will be processed on the next sync.
    """
    db = request.app.state.db

    try:
        # Find the log entry
        entries = db.get_action_log(limit=1000)
        entry = next((e for e in entries if e.id == log_id), None)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Action log entry {log_id} not found")

        # Re-add the action tag to the message classification
        message = db.get_message(entry.message_id)
        if not message:
            raise HTTPException(status_code=404, detail=f"Message {entry.message_id} not found")

        classification = db.get_classification(entry.message_id)
        if not classification:
            raise HTTPException(status_code=404, detail=f"No classification for message {entry.message_id}")

        # Add tag back if not already present
        if entry.action_name not in classification.tags:
            updated_tags = classification.tags + [entry.action_name]
            db.update_message_tags(entry.message_id, updated_tags)

        # Delete old log entries for this action+message to reset attempt counter
        db.delete_action_log(entry.message_id, entry.action_name)

        return {
            "status": "queued",
            "message": f"Action '{entry.action_name}' will be retried on next sync",
            "message_id": entry.message_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
