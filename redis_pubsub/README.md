# FastAPI + Redis Pub/Sub

Publish a message over HTTP and deliver it live to every WebSocket subscriber on the same Redis channel.

## How it works

```text
+-----------+  HTTP POST  +---------+  PUBLISH  +---------------+
| Publisher | ----------> | FastAPI | --------> | Redis channel |
+-----------+             +---------+           +-------+-------+
                                                        | message
                                                        v
+---------------+  WebSocket fan-out  +--------------------------+
| Browser A + B | <------------------ | FastAPI Redis subscriber |
+---------------+                     +--------------------------+
```

Each WebSocket has its own Redis Pub/Sub connection. FastAPI sends a `subscribed` frame only after Redis confirms the subscription, so clients know when it is safe to publish.

## Run the demo

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker with Docker Compose, and Python 3.13. `uv` can install the required Python version.

From the repository root:

```bash
cd redis_pubsub
uv sync --frozen
source .venv/bin/activate
docker compose up -d redis
docker compose exec -T redis redis-cli PING
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The Redis check must print `PONG`. The app uses `redis://localhost:6379/0` by default. To use another Redis server, set `REDIS_URL` before starting Uvicorn:

```bash
export REDIS_URL="redis://localhost:6379/0"
```

`.env.example` is a template; the app does not load it automatically.

## Verify browser fan-out

1. Open `http://127.0.0.1:8000` in two tabs.
2. In both tabs, enter `notifications`, click **Connect**, and wait for **Subscribed to notifications**.
3. Send `Hello from Redis!` from one tab.
4. Confirm both tabs display the message exactly once and the result shows `"subscriber_count": 2`.
5. Connect a third tab to `other-channel`; publish again to `notifications`. The third tab must receive nothing.
6. Disconnect one `notifications` tab and publish again. Only the remaining tab receives it, with `"subscriber_count": 1`.

The browser publishes over HTTP and subscribes over WebSocket. HTTP documentation is available at `http://127.0.0.1:8000/docs`; the WebSocket contract is documented below.

## Publish over HTTP

```bash
curl --max-time 15 -sS -X POST \
  'http://127.0.0.1:8000/channels/notifications/messages' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello from Redis!"}'
```

With no subscribers, the response is:

```json
{"channel":"notifications","subscriber_count":0}
```

`subscriber_count` is the number of Redis subscribers that received the payload. It does not confirm that a browser processed or displayed it.

## Subscribe over WebSocket

Connect to `ws://127.0.0.1:8000/ws/notifications`. Wait for this readiness frame before publishing:

```json
{"type":"subscribed","channel":"notifications"}
```

Each published message then arrives as:

```json
{"type":"message","channel":"notifications","message":"Hello from Redis!"}
```

The WebSocket is receive-only for application messages.

## Validation and errors

- Channels: 1–128 characters matching `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`.
- Messages: JSON strings of 1–10,000 characters.
- Invalid HTTP input: `422`.
- Invalid WebSocket channel: close code `1008`.
- Redis publish failure: `503` with `{"detail":"Redis publish unavailable"}`.
- Redis subscription failure: WebSocket close code `1011` when a clean close is possible.

## Run the tests

Keep the project's Docker Redis running and use another terminal:

```bash
cd redis_pubsub
uv run pytest
uv run python -m compileall -q app tests
```

Expected result: **8 passed**, with no skipped or xfailed tests. The integration tests use real Redis and public HTTP/WebSocket interfaces. One test stops and restarts this project's Redis container to verify outage handling.

## Delivery semantics

Redis Pub/Sub is live, fire-and-forget messaging. Offline clients miss messages; there is no history, replay, persistence, or acknowledgment. Use Redis Streams or another durable system when those guarantees are required.

See [Redis Pub/Sub fundamentals](Redis_Pub_Sub_Fundamentals.md) for the underlying concepts.

## Stop the demo

Press `Ctrl+C` to stop Uvicorn, then run:

```bash
docker compose down
```
