# Open QoD Gateway

Open QoD Gateway is a Python service that exposes a simplified,
CAMARA-inspired Quality on Demand API and translates QoD sessions into
3GPP NEF AsSessionWithQoS subscriptions.

It was developed and validated with the customized free5GC environment
from the Infosys 5G Quality on Demand project.

## Architecture

```text
Application
    |
    | OAuth2 client_credentials
    | POST / GET / PATCH / DELETE /sessions
    v
Open QoD Gateway
    |
    | OAuth2 client_credentials
    | 3GPP AsSessionWithQoS
    v
free5GC NEF
    |
    v
PCF -> SMF -> UPF
```

The gateway stores the relationship between its public session UUID and
the corresponding NEF subscription ID in SQLite.

## Implemented features

- QoD session creation with `POST /sessions`
- Session retrieval with `GET /sessions/{sessionId}`
- Profile and duration update with `PATCH /sessions/{sessionId}`
- Session deletion with `DELETE /sessions/{sessionId}`
- Automatic expiration and cleanup of QoD sessions
- SQLite persistence
- QoS profile translation to NEF bandwidth parameters
- OAuth2 `client_credentials` token endpoint
- Bearer-token authorization
- Separate `qod:read` and `qod:write` scopes
- Optional TLS verification for the NEF connection
- Optional client certificate and key for outbound mTLS
- Automated unit and API tests
- FastAPI OpenAPI documentation

## Current QoS profiles

| Profile | Guaranteed bandwidth | Maximum bandwidth |
|---|---:|---:|
| `QOS_M` | 10 Mbps | 20 Mbps |
| `QOS_HIGH` | 12 Mbps | 24 Mbps |

The profiles are defined in `app/profiles.py`.

## Requirements

- Python 3.10 or newer
- A reachable free5GC NEF
- Valid NEF OAuth2 client credentials
- An active UE and PDU session for runtime QoD tests

## Installation

```bash
git clone <repository-url>
cd open-qod-gateway

python3 -m venv .venv
. .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env
```

Edit `.env` before starting the gateway.

## Configuration

```dotenv
APP_HOST=0.0.0.0
APP_PORT=8080
DATABASE_PATH=data/open-qod-gateway.db
SESSION_CLEANUP_INTERVAL_SECONDS=5

GATEWAY_OAUTH_CLIENT_ID=open-qod-client
GATEWAY_OAUTH_CLIENT_SECRET=replace-with-strong-secret
GATEWAY_OAUTH_SIGNING_SECRET=replace-with-strong-signing-secret
GATEWAY_OAUTH_TOKEN_TTL_SECONDS=3600

NEF_BASE_URL=https://10.100.200.14:8000
NEF_CLIENT_ID=replace-me
NEF_CLIENT_SECRET=replace-me
NEF_VERIFY_TLS=false
NEF_TIMEOUT_SECONDS=10
NEF_SCS_AS_ID=open-qod-gateway
NEF_NOTIFICATION_DESTINATION=http://10.100.200.1:9999/notifications
```

Optional outbound TLS and mTLS settings:

```dotenv
NEF_CA_BUNDLE=/path/to/ca.crt
NEF_CLIENT_CERT=/path/to/gateway-client.crt
NEF_CLIENT_KEY=/path/to/gateway-client.key
```

`NEF_CLIENT_CERT` and `NEF_CLIENT_KEY` must be configured together.

The client certificate is presented only when the NEF requests one.
The NEF must separately enforce and validate client certificates for
mutual TLS to be effective.

Do not commit `.env`, private keys, tokens or production credentials.

## Running the gateway

```bash
. .venv/bin/activate

python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8080
```

Health check:

```bash
curl http://127.0.0.1:8080/health
```

Expected response:

```json
{"status":"ok"}
```

Interactive API documentation:

```text
http://127.0.0.1:8080/docs
```

## Obtaining an access token

```bash
curl -X POST \
    http://127.0.0.1:8080/oauth2/token \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=client_credentials' \
    --data-urlencode 'client_id=open-qod-client' \
    --data-urlencode 'client_secret=replace-with-strong-secret' \
    --data-urlencode 'scope=qod:read qod:write'
```

Example response:

```json
{
  "access_token": "<token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "qod:read qod:write"
}
```

## Creating a QoD session

```bash
curl -X POST \
    http://127.0.0.1:8080/sessions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer <token>' \
    -d '{
      "device": {
        "ipv4Address": "10.61.0.1"
      },
      "applicationServer": {
        "ipv4Address": "10.100.200.1/32"
      },
      "qosProfile": "QOS_M",
      "duration": 300
    }'
```

The returned `sessionId` is the public gateway identifier. The internal
NEF subscription ID is not exposed by the public API.

## Reading a session

```bash
curl \
    -H 'Authorization: Bearer <token>' \
    http://127.0.0.1:8080/sessions/<session-id>
```

This operation requires the `qod:read` scope.

## Updating a session

```bash
curl -X PATCH \
    http://127.0.0.1:8080/sessions/<session-id> \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer <token>' \
    -d '{
      "qosProfile": "QOS_HIGH",
      "duration": 600
    }'
```

This operation requires the `qod:write` scope.

## Deleting a session

```bash
curl -X DELETE \
    -H 'Authorization: Bearer <token>' \
    http://127.0.0.1:8080/sessions/<session-id>
```

A successful deletion returns HTTP `204`.

## Testing

```bash
. .venv/bin/activate
python -m pytest -q
```

Syntax validation:

```bash
python -m compileall -q app scripts tests
```

## Runtime validation performed

The implementation was exercised against the Infosys/free5GC
environment using the following workflow:

1. UE registration and PDU session establishment
2. Gateway OAuth2 token issuance
3. QoD session creation
4. NEF AsSessionWithQoS subscription creation
5. Dedicated QER installation in the UPF
6. QoS update from 10/20 Mbps to 12/24 Mbps
7. Gateway and SQLite session retrieval
8. Explicit session deletion
9. Automatic session expiration
10. Dedicated QER removal while retaining the default QER

The tests demonstrate control-plane provisioning and UPF rule changes.
They do not independently prove guaranteed radio performance or RAN
scheduler enforcement.

## API scope

This project implements the subset required for the research prototype.

It should be described as CAMARA-inspired, rather than as a complete or
certified implementation of the CAMARA Quality on Demand API.

## Project structure

```text
app/
  config.py       Application settings
  database.py     SQLite repository
  main.py         FastAPI routes and lifecycle
  models.py       Public API models
  nef_client.py   NEF OAuth2 and AsSessionWithQoS client
  oauth.py        Gateway token issuance and validation
  profiles.py     QoS profile definitions
  service.py      Session orchestration

scripts/
  smoke_nef_subscription.py

tests/
  API, persistence, OAuth2, authorization, TLS and service tests
```

## Security notes

- Change all example credentials before deployment.
- Use HTTPS for public exposure.
- Store secrets outside the repository.
- Enable NEF certificate verification with a trusted CA.
- mTLS requires client configuration in this gateway and server-side
  certificate enforcement in the NEF.
- Production deployments should normally use a dedicated authorization
  server with managed signing keys and key rotation.

## Status

Research prototype.

It is not intended for production deployment without additional
security review, interoperability testing and operational hardening.
