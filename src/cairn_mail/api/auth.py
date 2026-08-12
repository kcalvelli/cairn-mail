"""Bearer-token authentication for the cairn-mail API.

The whole API is single-user and sits behind a shared secret. The token is
loaded once at startup from a file (so it can come from an agenix/sops secret
via systemd LoadCredential) and compared in constant time on every request.
If the token can't be loaded, the service refuses to start — fail closed beats
serving the mailbox to anyone who can reach the port.

See openspec/changes/add-api-authentication/ for the why.
"""

import logging
import os
import secrets
from pathlib import Path
from typing import Iterable, List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Env var naming the file that holds the token. On NixOS this is wired to a
# systemd credential (LoadCredential), so it lands at $CREDENTIALS_DIRECTORY/token.
TOKEN_FILE_ENV = "CAIRN_MAIL_TOKEN_FILE"

# Comma-separated extra hostnames allowed through TrustedHostMiddleware. Loopback
# is always allowed. Unset/empty means "permit any host" (with a warning) — the
# bearer token is the real boundary; host-checking is defense-in-depth against
# DNS rebinding and is opt-in per deployment.
ALLOWED_HOSTS_ENV = "CAIRN_MAIL_ALLOWED_HOSTS"

# API paths reachable without a token: health probe, build-version poll (the PWA
# checks this before the user has logged in), and the service-worker recovery
# page. Everything else under /api requires the token. These are the real paths
# after the system router is mounted under the /api prefix.
EXEMPT_PATHS = frozenset({"/api/health", "/api/version", "/api/clear-sw"})


def load_token() -> str:
    """Read and return the API token from the configured file.

    Raises RuntimeError if the env var is unset, the file is missing/unreadable,
    or the token is empty. The caller is expected to let this propagate so the
    service fails to start rather than run unprotected.
    """
    path_str = os.environ.get(TOKEN_FILE_ENV)
    if not path_str:
        raise RuntimeError(
            f"{TOKEN_FILE_ENV} is not set. The API refuses to start without a "
            f"token — point it at a file containing the shared secret."
        )
    path = Path(path_str)
    try:
        token = path.read_text().strip()
    except OSError as e:
        raise RuntimeError(f"Could not read token file at {path}: {e}") from e
    if not token:
        raise RuntimeError(f"Token file at {path} is empty. Refusing to start unprotected.")
    return token


def extract_bearer(authorization: Optional[str]) -> Optional[str]:
    """Pull the token out of an `Authorization: Bearer <token>` header value."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    candidate = parts[1].strip()
    return candidate or None


def token_matches(authorization: Optional[str], expected: str) -> bool:
    """Constant-time check of an Authorization header against the expected token."""
    candidate = extract_bearer(authorization)
    if candidate is None:
        return False
    return secrets.compare_digest(candidate, expected)


def path_requires_auth(path: str) -> bool:
    """True if an HTTP path must carry a token.

    Only paths under /api are guarded (the static frontend shell and SPA routes
    load without a token so the token-entry prompt can render). The exempt set
    is carved out of /api. The WebSocket (/ws) is guarded in its own endpoint,
    not here — HTTP middleware never sees the websocket scope.
    """
    if path in EXEMPT_PATHS:
        return False
    return path == "/api" or path.startswith("/api/")


def resolve_allowed_hosts() -> Iterable[str]:
    """Build the TrustedHostMiddleware allow-list from the environment.

    Loopback is always included. If no hosts are configured we return ["*"]
    (permissive) and warn — an unconfigured deploy should still work over the
    tailnet, since the token carries the security load; operators opt into
    host-pinning by setting the env var.
    """
    raw = os.environ.get(ALLOWED_HOSTS_ENV, "").strip()
    configured = [h.strip() for h in raw.split(",") if h.strip()]
    if not configured:
        logger.warning(
            "%s is unset — allowing any Host header. Set it to your tailnet FQDN "
            "to harden against DNS rebinding.",
            ALLOWED_HOSTS_ENV,
        )
        return ["*"]
    return ["localhost", "127.0.0.1", *configured]


def install_security(app: FastAPI, *, cors_origins: List[str]) -> None:
    """Install the auth + trusted-host + CORS middleware and a generic 500 handler.

    Registration order matters: Starlette runs middleware in reverse order of
    registration, so the last added is outermost. We register auth first, CORS
    second, TrustedHost last, giving (outermost -> innermost):
        TrustedHost -> CORS -> auth -> routes.
    Keeping auth inner to CORS means a 401 still carries CORS headers, so the
    dev frontend on another origin can read it and show the token prompt.

    The auth middleware reads `app.state.api_token`, which is loaded at startup
    (or set directly by tests).
    """

    @app.middleware("http")
    async def require_bearer_token(request: Request, call_next):
        # CORS preflight carries no auth header and moves no data — let it pass.
        # The websocket is guarded in its own endpoint (HTTP middleware never
        # sees the websocket scope).
        if request.method == "OPTIONS" or not path_requires_auth(request.url.path):
            return await call_next(request)
        expected = getattr(request.app.state, "api_token", None)
        if not expected or not token_matches(request.headers.get("authorization"), expected):
            return JSONResponse(
                {"detail": "Missing or invalid authentication token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(resolve_allowed_hosts()),
    )

    @app.exception_handler(Exception)
    async def _generic_exception_handler(request: Request, exc: Exception):
        """Return a generic 500 while logging the detail — no reconnaissance surface."""
        logger.error(
            "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc
        )
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
