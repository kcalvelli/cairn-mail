## Context

See `proposal.md` — Why. Constraints that shape the approach, from the current
code:

- The FastAPI app is a module-level object (`src/cairn_mail/api/main.py`,
  `app = FastAPI(...)`) launched by uvicorn via string import
  (`cli/web.py` → `uvicorn.run("cairn_mail.api.main:app", ...)`). Configuration
  is therefore read at import/startup time from the environment, not passed as
  arguments. A failure raised during import/startup prevents the server from
  serving at all — the desired fail-closed behavior.
- Routes are plain `APIRouter`s included under `/api`, plus a system router
  (`/health`, `/version`, `/clear-sw`) registered before a `StaticFiles` mount
  that serves the built frontend at `/`.
- The WebSocket endpoint (`api/websocket.py` `/ws`) calls
  `await manager.connect(websocket)` (which accepts) as its first line — there
  is no pre-accept check today.
- Services run hardened (`modules/nixos/default.nix`): `ProtectHome=read-only`
  with `ReadWritePaths` limited to `~/.local/share/cairn-mail`. A secret placed
  elsewhere in `$HOME` would be unreadable, so secret delivery must not depend
  on a home path.
- `access_log=False` is already set in `cli/web.py`, which matters for keeping a
  token that rides in the WebSocket URL out of logs.
- Single user (the owner). The only API clients are the owner's frontend and the
  MCP server.

## Goals / Non-Goals

**Goals:**

- One enforcement layer that covers every HTTP route and the WebSocket with a
  single shared secret, with the smallest possible exempt set.
- Secret delivery compatible with agenix/sops and the existing systemd
  hardening, with no secret on a command line or in `$HOME`.
- Keep the owner's two real clients (frontend, MCP) working with minimal
  ceremony.

**Non-Goals (design-level boundaries beyond the proposal):**

- No per-user identity, roles, sessions, cookies, or token rotation/expiry. One
  static token, rotated by editing the secret and restarting.
- No rate-limiting or brute-force lockout on failed auth. The token has ~256
  bits of entropy; online guessing is not the threat model. Revisit only if the
  service is ever exposed beyond the tailnet.
- No change to how mail providers authenticate (IMAP/Gmail) — unrelated.

## Decisions

### D1: HTTP auth as ASGI middleware; WebSocket auth inline in the endpoint

HTTP requests are guarded by a single middleware that runs before routing and
rejects any request lacking a valid bearer token. WebSocket auth **cannot** live
in HTTP middleware — a WS connection is a separate ASGI scope and the browser
cannot send an `Authorization` header on the handshake — so it is enforced
inline in the `/ws` endpoint, reading `websocket.query_params["token"]` and
calling `websocket.close(code=4401)` before `manager.connect()` on failure.

- Alternative considered: a FastAPI `Depends` on every router. Rejected — it's
  easy to forget on a new router (that class of omission is exactly how the API
  ended up unauthenticated), and it doesn't cover the `StaticFiles` mount or
  system routes uniformly. Middleware is the fail-safe default: everything is
  protected unless explicitly exempted.

### D2: Exempt set = `/health`, `/version`, `/clear-sw`, and static assets

The frontend must load and poll for updates *before* the user has entered a
token so it can render the token-entry prompt and recover from a bad service
worker. So the static app, `/health` (probes), `/version` (SW update poll), and
`/clear-sw` (SW recovery page) are exempt. All of these expose only a build
string or static files — no mail data. Everything under `/api` and `/ws`
requires the token.

- Alternative: exempt only `/health`. Rejected — the frontend's version poll and
  SW-recovery page would 401 before login, breaking bootstrap and update
  recovery.

### D3: Token from a file via env, delivered by `LoadCredential`

The service reads `CAIRN_MAIL_TOKEN_FILE` at startup, reads and strips the file,
and refuses to start (raise) if it is missing or empty. The NixOS module gets a
`tokenFile` option and wires the secret with
`LoadCredential = "token:${cfg.tokenFile}"`, setting
`CAIRN_MAIL_TOKEN_FILE=%d/token` (the systemd credentials dir). This keeps the
secret outside `$HOME`, so `ProtectHome=read-only` and the existing
`ReadWritePaths` need no change, and the file is exposed only to this unit.

- Alternative: read the token directly from an env var. Rejected — secrets in
  env are visible in `/proc/<pid>/environ` and more likely to leak into logs or
  crash dumps than a `LoadCredential` file.
- Alternative: put the token file under `~/.local/share/cairn-mail`. Rejected —
  works, but couples the secret to a writable data dir and to agenix ownership
  matching `cfg.user`; `LoadCredential` is the cleaner boundary.

### D4: Constant-time comparison, `401` with `WWW-Authenticate: Bearer`

Compare with `secrets.compare_digest`. Reject with `401` (not `403`) plus
`WWW-Authenticate: Bearer` so the semantics are standard and the frontend can
key its re-prompt on `401`.

### D5: Frontend stores the token in `localStorage`; axios + WS attach it

An axios request interceptor attaches `Authorization: Bearer <token>`; a
response interceptor catches `401` and triggers the token-entry prompt. The WS
hook appends `?token=<token>` to the URL. `localStorage` (not in-memory) so the
installed PWA survives reloads without re-prompting.

- Trade-off: `localStorage` is readable by any XSS in the app origin. Accepted
  for a single-user client — the token grants exactly what the user already has,
  and the separate XSS fixes (ROADMAP 0.7 print window, 2.7 `EmailContent`
  sanitization) shrink that surface. Not worth httpOnly-cookie machinery for one
  user with no CSRF story.

### D6: MCP reads `CAIRN_MAIL_API_TOKEN` or `CAIRN_MAIL_TOKEN_FILE`

The MCP server (`mcp/server.py`, HTTP client to `localhost:8080`) attaches the
same bearer token, resolving it from `CAIRN_MAIL_API_TOKEN` (literal) or
`CAIRN_MAIL_TOKEN_FILE` (path, same as the service). If neither yields a token,
API-calling tools return a descriptive error instead of sending an
unauthenticated request. The literal env var exists because the MCP server may
run in a context (e.g. an agent host) that doesn't share the service's
`LoadCredential` mount.

### D7: TrustedHostMiddleware with a configurable allow-list

Add `TrustedHostMiddleware` (Starlette built-in) ahead of routing. Default
allowed hosts: `localhost`, `127.0.0.1`, plus a new `allowedHosts` module option
for the machine's Tailscale FQDN. This runs before the auth middleware so a
rebinding request is rejected regardless of token state. The existing CORS
middleware is now moot (no cookie auth) and can be left as-is or simplified;
it is not the security boundary.

## Risks / Trade-offs

- **WS token could appear in logs/proxies** → `access_log=False` is already set;
  Tailscale Serve terminates TLS so the URL isn't on the wire in clear. Accept
  the residual risk over a header-based scheme the browser can't produce.
- **Misconfigured `allowedHosts` blocks legitimate requests (400)** → default
  includes loopback so local/CLI access always works; document that the
  Tailscale FQDN must be added. Provide it as an explicit option, not
  auto-magic.
- **Breaking change: every client must present the token at once** → only two
  clients exist, both the owner's; the migration plan sequences secret →
  frontend re-prompt → MCP env so there's no window where a client is
  permanently broken.
- **`localStorage` token exfil via XSS** → see D5; mitigated by the paired XSS
  fixes, accepted for single-user scope.
- **Fail-closed on missing token file could take the service down on a botched
  secret rollout** → this is intended; a down service is safer than an
  unauthenticated one, and `Restart=on-failure` plus a clear startup error make
  the cause obvious in the journal.

## Migration Plan

1. Provision the token secret (agenix/sops), readable per `LoadCredential`.
2. Deploy the module with `tokenFile` and `allowedHosts` set. Service starts
   protected; the frontend loads (static assets exempt) and 401s on its first
   `/api` call, showing the token prompt. Owner enters the token once.
3. Set the MCP server's `CAIRN_MAIL_API_TOKEN`/`CAIRN_MAIL_TOKEN_FILE` in its
   environment so its tools keep working.
4. Rollback: revert the package + module to the prior revision. (There is no
   partial rollback — auth is all-or-nothing by design.)
