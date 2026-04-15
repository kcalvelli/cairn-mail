"""Push notification API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class PushSubscriptionRequest(BaseModel):
    """Push subscription from the browser."""

    endpoint: str
    keys: dict  # { p256dh: str, auth: str }


class UnsubscribeRequest(BaseModel):
    """Unsubscribe request."""

    endpoint: str


@router.get("/push/vapid-key")
async def get_vapid_key(request: Request):
    """Return the VAPID public key for push subscription."""
    config = getattr(request.app.state, "config", {})
    push_config = config.get("push", {})

    if not push_config.get("enable"):
        raise HTTPException(status_code=404, detail="Push notifications not configured")

    public_key = push_config.get("vapidPublicKey", "")
    if not public_key:
        raise HTTPException(status_code=500, detail="VAPID public key not configured")

    return {"publicKey": public_key}


@router.post("/push/subscribe")
async def subscribe(request: Request, body: PushSubscriptionRequest):
    """Register a push subscription."""
    config = getattr(request.app.state, "config", {})
    push_config = config.get("push", {})

    if not push_config.get("enable"):
        raise HTTPException(status_code=404, detail="Push notifications not configured")

    db = request.app.state.db

    p256dh = body.keys.get("p256dh", "")
    auth = body.keys.get("auth", "")

    if not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing p256dh or auth keys")

    try:
        db.upsert_push_subscription(
            endpoint=body.endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        return {"status": "subscribed"}
    except Exception as e:
        logger.error(f"Failed to store push subscription: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/push/unsubscribe")
async def unsubscribe(request: Request, body: UnsubscribeRequest):
    """Remove a push subscription."""
    db = request.app.state.db

    try:
        deleted = db.delete_push_subscription(endpoint=body.endpoint)
        if not deleted:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "unsubscribed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove push subscription: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
