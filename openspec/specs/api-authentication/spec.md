# api-authentication Specification

## Purpose

Ensures that only clients holding a shared secret token can reach the mail API
and its real-time WebSocket, and that the service cannot be coerced into serving
a request for an unexpected host, so that exposure over a semi-trusted network
(Tailscale) does not grant any reachable device read/send/delete access to the
mailbox.

## Requirements

### Requirement: Bearer token required for API access

Every HTTP route SHALL require a valid bearer token in the `Authorization`
header, except `GET /health` and the static frontend assets, which SHALL remain
accessible without a token. Token comparison MUST be constant-time. A request
with a missing, malformed, or incorrect token SHALL receive `401 Unauthorized`
and SHALL NOT execute any route logic or side effect.

#### Scenario: Valid token is accepted

- **WHEN** a client sends a request to a protected route with
  `Authorization: Bearer <correct-token>`
- **THEN** the request is processed normally

#### Scenario: Missing token is rejected

- **WHEN** a client sends a request to a protected route with no
  `Authorization` header
- **THEN** the response is `401 Unauthorized` and no route side effect occurs

#### Scenario: Incorrect token is rejected

- **WHEN** a client sends a request to a protected route with an
  `Authorization` header whose token does not match the configured token
- **THEN** the response is `401 Unauthorized` and no route side effect occurs

#### Scenario: Health and static assets are exempt

- **WHEN** a client sends `GET /health` or requests a static frontend asset
  with no token
- **THEN** the response is served normally without authentication

### Requirement: WebSocket handshake authentication

The real-time WebSocket endpoint SHALL authenticate the connection during the
handshake using a `token` query parameter, because browsers cannot set request
headers on WebSocket connects. A connection presenting a missing or incorrect
token SHALL be rejected before the connection is accepted, and SHALL receive no
broadcast messages.

#### Scenario: Valid token connects

- **WHEN** a client opens the WebSocket with `?token=<correct-token>`
- **THEN** the handshake is accepted and the client receives live updates

#### Scenario: Missing or incorrect token is rejected

- **WHEN** a client opens the WebSocket with no `token` parameter or an
  incorrect one
- **THEN** the connection is rejected before being accepted and no mail data is
  transmitted

### Requirement: Trusted host enforcement

The service SHALL reject any HTTP request whose `Host` header is not in a
configured allow-list of trusted hostnames, in order to close the DNS-rebinding
vector. The allow-list SHALL always include loopback names (`localhost`,
`127.0.0.1`) and SHALL be extensible with additional hostnames (e.g. the
machine's Tailscale FQDN) via configuration.

#### Scenario: Allowed host is served

- **WHEN** a request arrives with a `Host` header present in the allow-list
- **THEN** the request proceeds to authentication and routing

#### Scenario: Unexpected host is rejected

- **WHEN** a request arrives with a `Host` header not in the allow-list
- **THEN** the request is rejected without reaching route logic

### Requirement: Token provisioning from a file-based secret

The service SHALL read its authentication token from a file whose path is
supplied by configuration, so the secret can be managed by an external secret
manager (agenix/sops) and never committed or passed on a command line. If the
token file is absent or empty at startup, the service SHALL fail to start with a
clear error rather than start unprotected.

#### Scenario: Token loaded from file

- **WHEN** the service starts with a configured token-file path pointing at a
  readable file containing a token
- **THEN** the service uses that token to authenticate requests

#### Scenario: Missing token file fails closed

- **WHEN** the service starts and the configured token file is absent or empty
- **THEN** the service fails to start with a clear error and does not serve
  unauthenticated requests

### Requirement: MCP client token propagation

The MCP server, which calls the mail API over HTTP on behalf of an agent, SHALL
attach the authentication token to every API request it makes. It SHALL obtain
the token from its environment, supporting both a direct value and a file path.
If no token is available, MCP tool calls that reach the API SHALL fail with a
descriptive error rather than sending unauthenticated requests.

#### Scenario: MCP attaches the token

- **WHEN** the MCP server has a token configured and invokes a tool that calls
  the API
- **THEN** the underlying HTTP request carries the bearer token and succeeds

#### Scenario: MCP without a token fails clearly

- **WHEN** the MCP server has no token available and a tool attempts to call the
  API
- **THEN** the tool returns a descriptive error and does not send an
  unauthenticated request

### Requirement: Frontend token handling

The web frontend SHALL attach the stored token to all API requests and to the
WebSocket URL. On receiving `401 Unauthorized`, it SHALL prompt the user to
enter a token and persist it for subsequent requests. The token entry flow is
the only authentication ceremony; no multi-user login is required.

#### Scenario: Token attached to requests

- **WHEN** a token is stored and the frontend makes an API request or opens the
  WebSocket
- **THEN** the token is included in the `Authorization` header and the WebSocket
  `token` query parameter respectively

#### Scenario: 401 triggers re-prompt

- **WHEN** an API request returns `401 Unauthorized`
- **THEN** the frontend prompts the user to enter a token and stores it for
  subsequent requests

### Requirement: Generic error responses

Server error responses (`500`) SHALL NOT include raw exception text, stack
traces, file paths, or query fragments in the client-visible body; the detail
SHALL be logged server-side and a generic message returned. This denies
reconnaissance value to unauthenticated or hostile callers.

#### Scenario: Internal error returns generic body

- **WHEN** a route raises an unhandled exception
- **THEN** the client receives a generic `500` message and the underlying detail
  is written only to the server log
