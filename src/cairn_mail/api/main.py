"""FastAPI application for cairn-mail web UI."""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..config.loader import ConfigLoader
from ..db.database import Database
from ..ai_classifier import AIClassifier, AIConfig
from ..providers.connection_pool import shutdown_connection_pool
from ..providers.imap_idle import get_idle_watcher, shutdown_idle_watcher, IdleConfig
from .routes.sync import _sync_executor
from .routes import accounts, actions, attachments, contacts, drafts, feedback, maintenance, messages, push, send, stats, sync, trusted_senders
from .websocket import router as websocket_router

# Configure logging for the entire cairn_mail package
# This ensures all our loggers output to stdout (for journalctl)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Set our package's logger level
logging.getLogger("cairn_mail").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="cairn-mail API",
    description="REST API for AI-enhanced email workflow",
    version="2.0.0",
)

# CORS middleware - Allow localhost origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Production
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database (shared with CLI)
db_path = Path.home() / ".local/share/cairn-mail/mail.db"
db = Database(db_path)
logger.info(f"Database initialized at {db_path}")

# Store database in app state for access in routes
app.state.db = db

# Include routers
app.include_router(messages.router, prefix="/api", tags=["messages"])
app.include_router(accounts.router, prefix="/api", tags=["accounts"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(actions.router, prefix="/api", tags=["actions"])
app.include_router(contacts.router, prefix="/api", tags=["contacts"])
app.include_router(sync.router, prefix="/api", tags=["sync"])
app.include_router(drafts.router, prefix="/api", tags=["drafts"])
app.include_router(attachments.router, prefix="/api", tags=["attachments"])
app.include_router(send.router, prefix="/api", tags=["send"])
app.include_router(maintenance.router, prefix="/api", tags=["maintenance"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(push.router, prefix="/api", tags=["push"])
app.include_router(trusted_senders.router, prefix="/api", tags=["trusted-senders"])
app.include_router(websocket_router, tags=["websocket"])

# Health and version endpoints (must be registered before static file mount)
_build_version: str = "dev"
_build_id_path = Path(__file__).parent.parent / "web_assets" / "build-id.json"
if not _build_id_path.exists():
    _build_id_path = Path(__file__).parent.parent.parent.parent / "web" / "dist" / "build-id.json"
if _build_id_path.exists():
    import json as _json
    try:
        _build_version = _json.loads(_build_id_path.read_text()).get("version", "dev")
    except Exception:
        pass

_system_router = APIRouter()


@_system_router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "database": str(db_path),
        "database_exists": db_path.exists(),
    }


@_system_router.get("/version")
async def get_version():
    """Return the current build version for cache invalidation."""
    return {"version": _build_version}


@_system_router.get("/clear-sw")
async def clear_service_worker():
    """Return a page that unregisters all service workers and clears caches."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""<!DOCTYPE html>
<html><body><h2>Clearing service worker...</h2><pre id="log"></pre>
<script>
const log = s => { document.getElementById('log').textContent += s + '\\n'; };
(async () => {
  const regs = await navigator.serviceWorker.getRegistrations();
  for (const r of regs) { await r.unregister(); log('Unregistered: ' + r.scope); }
  const keys = await caches.keys();
  for (const k of keys) { await caches.delete(k); log('Deleted cache: ' + k); }
  log('Done! Redirecting in 2s...');
  setTimeout(() => window.location.href = '/', 2000);
})();
</script></body></html>""")

app.include_router(_system_router, prefix="/api", tags=["system"])

# Serve static files (frontend build) if they exist
# Try installed package location first, then development location
# In installed package: cairn_mail/web_assets (one level up from api/)
static_dir = Path(__file__).parent.parent / "web_assets"
if not static_dir.exists():
    # Try development location
    static_dir = Path(__file__).parent.parent.parent.parent / "web" / "dist"

if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    logger.info(f"Serving static files from {static_dir}")
else:
    logger.warning(f"Static files not found at {static_dir}. Web UI will not be available.")


def _setup_idle_watchers(config: dict):
    """Setup IMAP IDLE watchers for configured IMAP accounts.

    Args:
        config: Loaded configuration dict
    """
    accounts = config.get("accounts", {})
    idle_watcher = get_idle_watcher()

    for account_id, account_config in accounts.items():
        # Only setup IDLE for IMAP accounts
        if account_config.get("provider") != "imap":
            continue

        # Get settings (IMAP config is stored flat in settings)
        settings = account_config.get("settings", {})

        # Check if IDLE is enabled for this account (default: True for IMAP)
        if not settings.get("enable_idle", True):
            logger.info(f"IDLE disabled for {account_id}")
            continue

        # IMAP settings are stored as imap_host, imap_port, etc.
        host = settings.get("imap_host")
        if not host:
            logger.warning(f"No IMAP host configured for {account_id}, skipping IDLE")
            continue

        try:
            idle_config = IdleConfig(
                account_id=account_id,
                email=account_config.get("email"),
                host=host,
                port=settings.get("imap_port", 993),
                credential_file=account_config.get("credential_file", settings.get("credential_file", "")),
                use_ssl=settings.get("imap_tls", True),
                folder="INBOX",  # IDLE typically watches INBOX
            )
            idle_watcher.add_account(idle_config, _on_idle_new_mail)
            logger.info(f"IDLE watcher configured for {account_id}")
        except Exception as e:
            logger.error(f"Failed to setup IDLE for {account_id}: {e}")

    # Start all watchers
    idle_watcher.start_all()
    watched = idle_watcher.get_watched_accounts()
    if watched:
        logger.info(f"IMAP IDLE watchers started for: {', '.join(watched)}")


# Track last IDLE-triggered sync time per account (debounce)
_idle_sync_times: dict = {}
IDLE_SYNC_DEBOUNCE_SECONDS = 30  # Don't sync same account more than once per 30s


def _on_idle_new_mail(account_id: str):
    """Callback when IMAP IDLE detects new mail.

    Sends a WebSocket notification and triggers a quick sync for the account.
    Includes debounce to prevent sync loops.
    """
    import asyncio
    import time
    from .websocket import send_new_mail_notification
    from .routes.sync import run_sync_task, get_sync_state

    logger.info(f"IDLE: New mail detected for {account_id}")

    # Get the running event loop from the main thread
    loop = getattr(app.state, 'event_loop', None)
    if not loop or not loop.is_running():
        logger.warning("No event loop available for IDLE notification")
        return

    try:
        # Send WebSocket notification immediately
        asyncio.run_coroutine_threadsafe(
            send_new_mail_notification(account_id),
            loop,
        )

        # Check debounce - don't sync same account too frequently
        now = time.time()
        last_sync = _idle_sync_times.get(account_id, 0)
        if now - last_sync < IDLE_SYNC_DEBOUNCE_SECONDS:
            logger.debug(
                f"Account {account_id} synced {now - last_sync:.1f}s ago, "
                f"skipping (debounce {IDLE_SYNC_DEBOUNCE_SECONDS}s)"
            )
            return

        # Check if this account is already syncing
        state = get_sync_state()
        if account_id in state.get("syncing_accounts", []):
            logger.debug(f"Account {account_id} already syncing, skipping IDLE-triggered sync")
            return

        # Update last sync time
        _idle_sync_times[account_id] = now

        # Trigger a quick sync for just this account (max 50 messages)
        logger.info(f"IDLE: Triggering sync for {account_id}")
        asyncio.run_coroutine_threadsafe(
            run_sync_task(app.state.db, account_id, max_messages=50),
            loop,
        )

    except Exception as e:
        logger.warning(f"Failed to handle IDLE notification: {e}")


@app.on_event("startup")
async def startup_event():
    """Load configuration and sync to database on startup."""
    import asyncio

    # Store event loop reference for use by IDLE threads
    app.state.event_loop = asyncio.get_running_loop()

    logger.info("Loading configuration on API startup")
    config = ConfigLoader.load_config()
    if config:
        # Store config in app state for access in routes
        app.state.config = config
        ConfigLoader.sync_to_database(app.state.db, config)
        logger.info("Configuration synced to database")

        # Initialize AI classifier from config
        ai_config = config.get("ai", {})
        if ai_config.get("enable", True):
            # Get merged tags from config
            merged_tags = ConfigLoader.get_merged_tags(config)
            classifier_config = AIConfig(
                model=ai_config.get("model", "claude-sonnet-4-20250514"),
                endpoint=ai_config.get("endpoint", "http://localhost:18789"),
                temperature=ai_config.get("temperature", 0.3),
                custom_tags=merged_tags,
            )
            app.state.classifier = AIClassifier(classifier_config)
            logger.info(f"AI classifier initialized with model {classifier_config.model}")

        # Initialize IMAP IDLE watchers for IMAP accounts
        _setup_idle_watchers(config)


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown."""
    logger.info("Shutting down API server")
    # Shutdown IMAP IDLE watchers first
    shutdown_idle_watcher()
    # Shutdown sync thread pool
    _sync_executor.shutdown(wait=True)
    # Shutdown IMAP connection pool
    shutdown_connection_pool()
    db.close()
