## 1. Backend: token loading and auth core

- [x] 1.1 Add an auth module (e.g. `src/cairn_mail/api/auth.py`) that reads the token at startup from `CAIRN_MAIL_TOKEN_FILE`, strips whitespace, and exposes it to the app; raise a clear `RuntimeError` if the env var is unset, the file is missing, or the token is empty (fail-closed per spec "Token provisioning from a file-based secret" / design D3).
- [x] 1.2 Implement a constant-time verify helper using `secrets.compare_digest` that extracts the bearer token from an `Authorization` header value and returns pass/fail (design D4).
- [x] 1.3 Wire the startup load into `api/main.py` so a bad/missing secret prevents the app from serving (import- or startup-time raise; verify uvicorn exits non-zero).

## 2. Backend: HTTP enforcement

- [x] 2.1 Add an ASGI auth middleware in `api/main.py` that requires a valid bearer token on every request, returning `401` with a `WWW-Authenticate: Bearer` header and no route execution on failure (spec "Bearer token required for API access", design D1/D4).
- [x] 2.2 Implement the exempt set — `/health`, `/version`, `/clear-sw`, and static frontend asset paths pass without a token; everything under `/api` requires it (spec exemption scenario, design D2).
- [x] 2.3 Add `TrustedHostMiddleware` ahead of the auth middleware, allowing `localhost`, `127.0.0.1`, plus hosts supplied by config; verify an unexpected `Host` is rejected before routing (spec "Trusted host enforcement", design D7).
- [x] 2.4 Confirm middleware ordering: trusted-host check runs before auth, both before routing; document the ordering with a short comment.

## 3. Backend: WebSocket enforcement

- [x] 3.1 In `api/websocket.py`, read `token` from `websocket.query_params` and reject with `websocket.close(code=4401)` before `manager.connect()` when missing/incorrect, using the same constant-time verify (spec "WebSocket handshake authentication", design D1).
- [x] 3.2 Verify a rejected handshake receives no `connected` welcome and no broadcasts.

## 4. Backend: error hygiene

- [x] 4.1 Add a generic exception handler (or adjust the per-route `raise HTTPException(500, detail=str(e))` sites) so `500` responses return a generic body while the detail is logged server-side (spec "Generic error responses"). Grep for `detail=str(e)` to find the sites.

## 5. MCP client

- [x] 5.1 In `mcp/server.py`, resolve the token from `CAIRN_MAIL_API_TOKEN` (literal) or `CAIRN_MAIL_TOKEN_FILE` (path) and attach `Authorization: Bearer <token>` to every API request (spec "MCP client token propagation", design D6).
- [x] 5.2 When no token is available, make API-calling tools return a descriptive error instead of sending an unauthenticated request; verify with an env-unset run.

## 6. NixOS module

- [x] 6.1 Add a `tokenFile` option and wire `LoadCredential = "token:${cfg.tokenFile}"` with `Environment` `CAIRN_MAIL_TOKEN_FILE=%d/token` on the web service (and any unit that needs it), leaving `ProtectHome`/`ReadWritePaths` unchanged (design D3).
- [x] 6.2 Add an `allowedHosts` option (list) feeding the trusted-host allow-list; default sensibly and document adding the Tailscale FQDN (design D7).
- [x] 6.3 Add an assertion that `tokenFile` is set when `services.cairn-mail.enable` is true, so a misconfigured deploy fails at build time rather than at runtime.

## 7. Frontend

- [x] 7.1 Add token storage in `localStorage` and an axios request interceptor in `web/src/api/client.ts` that attaches `Authorization: Bearer <token>` (spec "Frontend token handling", design D5).
- [x] 7.2 Add an axios response interceptor that, on `401`, triggers a token-entry prompt and persists the entered token for subsequent requests.
- [x] 7.3 Append `?token=<token>` to the WebSocket URL in the WS hook.
- [x] 7.4 Add a minimal token-entry UI (single field) shown on `401`/no-token; no multi-user login.

## 8. Tests

- [x] 8.1 API auth tests (FastAPI TestClient): valid token passes; missing and incorrect tokens `401` with no side effect; `/health`, `/version`, `/clear-sw`, and a static asset are reachable without a token.
- [x] 8.2 Trusted-host tests: allowed `Host` served; unexpected `Host` rejected.
- [x] 8.3 WebSocket tests: valid token connects and receives updates; missing/incorrect token is rejected before accept with no data sent.
- [x] 8.4 Startup fail-closed test: missing/empty token file prevents startup.
- [x] 8.5 Generic-500 test: a route raising an exception returns a generic body with no exception text; detail is logged.
- [x] 8.6 MCP token tests: token attached when present; descriptive error when absent.

## 9. Docs and rollout

- [x] 9.1 Document the `tokenFile` and `allowedHosts` options and the secret-provisioning step in `docs/CONFIGURATION.md`; note the MCP env vars.
- [x] 9.2 Note the breaking change and the migration sequence (secret → deploy/re-prompt → MCP env) in `CHANGELOG.md`.
- [x] 9.3 Run `openspec validate --changes add-api-authentication --strict` and verify each spec scenario maps to a passing test.
