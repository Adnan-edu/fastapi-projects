# FastAPI + Redis Pub/Sub Demo

A small end-to-end example of live one-to-many messaging: HTTP clients publish text to a Redis channel, and every browser/WebSocket subscriber on that channel receives the message through FastAPI.

## Prerequisites and setup

Install [uv](https://docs.astral.sh/uv/) and Docker with Docker Compose. The project uses Python 3.13 (see `.python-version`), which `uv` can provide.

From a fresh terminal:

```bash
export PROJECT_ROOT="/Users/adnan/Documents/adnanedu/adnanedu/fastapi_projects_new/fastapi_project_adnanedu/fastapi-projects/redis_pubsub"
cd "$PROJECT_ROOT"
uv sync --frozen
source "$PROJECT_ROOT/.venv/bin/activate"
```

The application reads `REDIS_URL`, defaulting to `redis://localhost:6379/0`. `$PROJECT_ROOT/.env.example` is a template only; it is **not loaded automatically**. Export the setting yourself when needed, or rely on the local default:

```bash
export REDIS_URL="redis://localhost:6379/0"
```

Do not commit real credentials or a local `.env` file.

## Start Redis and FastAPI

Start the throwaway Redis 8 container and verify its health:

```bash
cd "$PROJECT_ROOT"
docker compose up -d redis
docker compose ps
docker compose exec -T redis redis-cli PING
```

The last command must print `PONG`. No volume is configured because this demo intentionally uses non-durable Pub/Sub.

Start Uvicorn in the activated environment:

```bash
cd "$PROJECT_ROOT"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Press `Ctrl+C` to stop Uvicorn gracefully. To stop or remove Redis from another terminal:

```bash
cd "$PROJECT_ROOT"
docker compose stop redis       # stop only
docker compose up -d redis      # start it again
docker compose down             # optional container cleanup
```

## Run the tests

Keep Docker Redis running, then use another activated terminal:

```bash
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"
uv run pytest
uv run python -m compileall -q "$PROJECT_ROOT/app" "$PROJECT_ROOT/tests"
```

The integration tests use real Redis and the public HTTP/WebSocket interfaces. One failure-path test deliberately stops and restarts the project's Compose Redis service, so do not run the suite against a Redis instance you cannot interrupt. Each test uses a unique channel; Redis logical databases do not isolate Pub/Sub channels.

## Browser walkthrough

1. Start Redis and Uvicorn, then open `http://127.0.0.1:8000` in two tabs.
2. In both tabs, enter `notifications`, click **Connect**, and wait for **Subscribed to notifications**. The Send button remains disabled until the server confirms the Redis subscription.
3. Send `Hello from Redis!` from the first tab. Both tabs should display it exactly once, and the HTTP result should report `subscriber_count` 2. With only one connected tab, the count is 1.
4. Connect a third tab to `other-channel` and publish again to `notifications`. The third tab should receive nothing.
5. Disconnect one `notifications` tab and publish again. Only the remaining tab should receive the message, with `subscriber_count` 1.

The browser publishes through HTTP; it does not invent a separate WebSocket publish protocol. Interactive documentation at `http://127.0.0.1:8000/docs` covers HTTP only, not the WebSocket contract documented below.

## HTTP publish contract

```http
POST /channels/{channel}/messages
Content-Type: application/json

{"message":"Hello from Redis!"}
```

For example, with no subscribers:

```bash
curl --max-time 15 -sS -i -X POST \
  'http://127.0.0.1:8000/channels/notifications/messages' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello from Redis!"}'
```

Successful response (`200`):

```json
{"channel":"notifications","subscriber_count":0}
```

`subscriber_count` is Redis's `PUBLISH` return value: the number of subscribers to which Redis sent the payload. It is not proof that a browser processed, displayed, or acknowledged the message.

Validation failures return `422`. Channels must be 1–128 characters and match `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`. Messages must be JSON strings of 1–10,000 characters; valid text is not trimmed or mutated.

If Redis cannot publish, the route returns `503` without exposing credentials or internal exception details:

```json
{"detail":"Redis publish unavailable"}
```

After Redis recovers, the shared asynchronous client can reconnect and publish successfully without rebuilding the application.

## WebSocket subscriber contract

Connect to `WS /ws/{channel}`, for example `ws://127.0.0.1:8000/ws/notifications` (the browser uses `wss:` when the page is served over HTTPS). The WebSocket is receive-only for application messages.

After Redis confirms the subscription, the server sends this readiness frame:

```json
{"type":"subscribed","channel":"notifications"}
```

Wait for this frame before publishing. It prevents the race where a publish occurs after the socket opens but before Redis has registered the subscriber. A published payload then arrives as:

```json
{"type":"message","channel":"notifications","message":"Hello from Redis!"}
```

Subscribers on other channels do not receive that payload. Invalid channels are rejected with close code `1008`. Redis failures close the WebSocket with `1011` where the connection can still close cleanly.

## Connection lifecycle and shutdown

The FastAPI lifespan creates and pings one shared `redis.asyncio` client with response decoding enabled. HTTP routes use that client only for ordinary commands such as `PUBLISH`.

Each WebSocket creates its own dedicated Redis Pub/Sub object and connection. Pub/Sub connections are stateful, so they are never shared across WebSockets or reused for ordinary commands. The server waits for Redis's subscribe acknowledgment before sending readiness, then concurrently watches Redis messages and client disconnect events. Only Redis `message` events are forwarded; subscription control events are not application messages.

On disconnect, server failure, or shutdown, pending tasks are cancelled and awaited, and the dedicated Pub/Sub object is closed with `aclose()`. The shared Redis client remains available to other requests and is closed once by the application lifespan at shutdown. Disconnecting one subscriber therefore does not close Redis for everyone else.

## Delivery semantics and limitations

Redis Pub/Sub is live, fire-and-forget messaging—not a durable queue:

- Offline or disconnected clients miss messages. There is no history, replay, persistence, or acknowledgment.
- Redis's per-subscriber output buffers are temporary in-memory socket buffers, not per-channel storage.
- Use Redis Streams or another durable messaging system when retention, replay, or delivery guarantees are required.

See `$PROJECT_ROOT/Redis_Pub_Sub_Fundamentals.md` (`Redis_Pub_Sub_Fundamentals.md` in this directory) for the underlying channel, buffering, and delivery concepts.

This example intentionally omits authentication, authorization, TLS termination, multi-process worker coordination, rate limiting, persistence, acknowledgments, pattern subscriptions, and production deployment.
