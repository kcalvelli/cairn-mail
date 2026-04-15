"""WebSocket support for real-time updates."""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self.lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self.lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific client."""
        try:
            # Check if websocket is still in active connections before sending
            if websocket not in self.active_connections:
                return
            await websocket.send_text(json.dumps(message))
        except RuntimeError as e:
            # WebSocket already disconnected - this is normal during shutdown
            if "not connected" in str(e).lower() or "close" in str(e).lower():
                logger.debug(f"WebSocket already disconnected: {e}")
            else:
                logger.error(f"Error sending message to client: {e}")
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        async with self.lock:
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(message))
                except RuntimeError as e:
                    # WebSocket already disconnected - this is normal
                    if "not connected" in str(e).lower() or "close" in str(e).lower():
                        logger.debug(f"WebSocket already disconnected during broadcast: {e}")
                    else:
                        logger.error(f"Error broadcasting to client: {e}")
                    disconnected.append(connection)
                except Exception as e:
                    logger.error(f"Error broadcasting to client: {e}")
                    disconnected.append(connection)

            # Remove failed connections
            for conn in disconnected:
                if conn in self.active_connections:
                    self.active_connections.remove(conn)


# Global connection manager
manager = ConnectionManager()


async def send_sync_started(account_id: str):
    """Send sync started event to all clients."""
    await manager.broadcast({
        "type": "sync_started",
        "account_id": account_id,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_sync_completed(account_id: str, stats: dict):
    """Send sync completed event to all clients."""
    await manager.broadcast({
        "type": "sync_completed",
        "account_id": account_id,
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_message_classified(message_id: str, tags: List[str]):
    """Send message classified event to all clients."""
    await manager.broadcast({
        "type": "message_classified",
        "message_id": message_id,
        "tags": tags,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_error(message: str, details: str = ""):
    """Send error event to all clients."""
    await manager.broadcast({
        "type": "error",
        "message": message,
        "details": details,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_new_messages(messages: List[dict]):
    """Send new messages event for notifications.

    Args:
        messages: List of message dicts with id, subject, from_email, snippet
    """
    if not messages:
        return

    await manager.broadcast({
        "type": "new_messages",
        "messages": messages,
        "count": len(messages),
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_action_completed(action_name: str, status: str, message_subject: str):
    """Send action completed event for toast notifications.

    Args:
        action_name: Action tag name (e.g., "add-contact", "create-reminder")
        status: Result status ("success", "failed", "skipped")
        message_subject: Subject of the email the action was performed on
    """
    await manager.broadcast({
        "type": "action_completed",
        "action_name": action_name,
        "status": status,
        "message_subject": message_subject,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_messages_updated(message_ids: List[str], action: str):
    """Send message updated event to all clients.

    Args:
        message_ids: List of message IDs that were updated
        action: The action performed (read, unread, tags_updated)
    """
    await manager.broadcast({
        "type": "messages_updated",
        "message_ids": message_ids,
        "action": action,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_messages_deleted(message_ids: List[str], permanent: bool = False):
    """Send message deleted event to all clients.

    Args:
        message_ids: List of message IDs that were deleted
        permanent: Whether the deletion was permanent
    """
    await manager.broadcast({
        "type": "messages_deleted",
        "message_ids": message_ids,
        "permanent": permanent,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_messages_restored(message_ids: List[str]):
    """Send message restored event to all clients.

    Args:
        message_ids: List of message IDs that were restored from trash
    """
    await manager.broadcast({
        "type": "messages_restored",
        "message_ids": message_ids,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def send_new_mail_notification(account_id: str):
    """Send new mail notification from IMAP IDLE.

    This is triggered when IDLE detects new mail, before sync runs.
    The client can use this to show a notification or trigger a refresh.

    Args:
        account_id: Account that received new mail
    """
    await manager.broadcast({
        "type": "new_mail_notification",
        "account_id": account_id,
        "message": f"New mail detected for {account_id}",
        "timestamp": datetime.utcnow().isoformat(),
    })


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)

    try:
        # Send welcome message
        await manager.send_personal_message({
            "type": "connected",
            "message": "Connected to cairn-mail WebSocket",
            "timestamp": datetime.utcnow().isoformat(),
        }, websocket)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle client messages (e.g., subscribe to topics)
                if message.get("type") == "subscribe":
                    topics = message.get("topics", [])
                    logger.info(f"Client subscribed to topics: {topics}")
                    await manager.send_personal_message({
                        "type": "subscribed",
                        "topics": topics,
                        "timestamp": datetime.utcnow().isoformat(),
                    }, websocket)

                elif message.get("type") == "ping":
                    # Respond to ping with pong
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    }, websocket)

            except json.JSONDecodeError:
                logger.error("Invalid JSON received from client")
                await manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON format",
                }, websocket)

    except WebSocketDisconnect:
        await manager.disconnect(websocket)
        logger.info("WebSocket disconnected normally")

    except RuntimeError as e:
        # Handle "WebSocket is not connected" errors gracefully
        if "not connected" in str(e).lower():
            logger.debug(f"WebSocket disconnected: {e}")
        else:
            logger.error(f"WebSocket runtime error: {e}")
        await manager.disconnect(websocket)

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await manager.disconnect(websocket)
