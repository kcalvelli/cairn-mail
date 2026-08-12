## Why

The FastAPI backend has no authentication of any kind — no token, session, or
guard on any HTTP route, the WebSocket, or the static app. Every endpoint is
fully open to anyone who can reach the port, including irreversible ones
(`bulk/permanent-delete`, `delete-all`, `clear-trash`). The service is exposed
over Tailscale Serve, so "reachable" means any device on the tailnet — a
family laptop, a compromised phone, or an ACL mistake — and, because there is
no `Host`/origin check, any browser on any tailnet host can be turned into an
attacker via DNS rebinding. A single unauthenticated request can read all mail,
send as the owner, or permanently destroy the mailbox. This is the highest-risk
gap in the codebase and blocks treating the tailnet as anything less than fully
trusted.

## What Changes

- Add a bearer-token authentication gate covering **all** HTTP routes and the
  WebSocket. `GET /health` and the static frontend assets remain open.
- Authenticate the WebSocket handshake via a `?token=` query parameter (browsers
  cannot set headers on WebSocket connects); reject unauthenticated connects
  before accepting.
- Add `TrustedHostMiddleware` to reject requests with an unexpected `Host`
  header, closing the DNS-rebinding vector.
- Source the token from a file (path via `CAIRN_MAIL_TOKEN_FILE`), wired into
  the NixOS units via a new `tokenFile` module option and `LoadCredential=` so
  the hardened services can read an agenix/sops secret.
- Plumb the token through the MCP server's HTTP client so it can keep calling
  the API.
- Frontend: prompt for and store the token, attach it to API requests and the
  WebSocket URL, and re-prompt on `401`.
- Stop returning raw exception strings in `500` responses (log the detail,
  return a generic message) so an authenticated-but-hostile or pre-auth client
  gets no reconnaissance surface. **BREAKING**: clients now require a valid
  token; unauthenticated requests receive `401`.

## Capabilities

### New Capabilities

- `api-authentication`: Bearer-token authentication and trusted-host
  enforcement for the HTTP API and WebSocket, token provisioning via a
  file-based secret, MCP client token propagation, and generic error responses.

### Modified Capabilities

<!-- None. The auth gate is a new layer in front of existing routes; it does
     not change the behavioral requirements of any existing spec (sync-engine,
     mcp-tool-expansion, action-tags, contact-lookup, documentation). The MCP
     tools behave identically once the token is attached to their HTTP client —
     an implementation detail, not a spec-level change. -->

## Impact

- **Code**: `src/cairn_mail/api/main.py` (middleware wiring), a new auth module,
  `api/websocket.py` (handshake auth), all route error handlers (generic 500s),
  `mcp/server.py` (token on HTTP client), `web/src/api/client.ts` and the
  WebSocket hook (token attach + 401 handling), a token-entry UI.
- **Config/Deploy**: new `tokenFile` option and `LoadCredential=` in
  `modules/nixos/default.nix`; new env vars `CAIRN_MAIL_TOKEN_FILE` (service,
  MCP) and `CAIRN_MAIL_API_TOKEN` (MCP literal fallback); a new `allowedHosts`
  option feeding `TrustedHostMiddleware`. Operator must provision a token
  secret before/at deploy.
- **Behavior**: all API and WebSocket clients must present the token; this is a
  breaking change for any existing client, but the only clients are the owner's
  own frontend and MCP server.
- **Dependencies**: none new; uses stdlib `secrets` and existing Starlette
  middleware.
