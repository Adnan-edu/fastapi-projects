# FastAPI + Redis Pub/Sub: Multi-Session TDD Plan

## 1. Purpose and current baseline

Build an end-to-end example in which HTTP clients publish messages to a Redis channel and connected browser/WebSocket clients receive them in real time through FastAPI.

Confirmed project root (work only here):

```bash
export PROJECT_ROOT="/Users/adnan/Documents/adnanedu/adnanedu/fastapi_projects_new/fastapi_project_adnanedu/fastapi-projects/redis_pubsub"
cd "$PROJECT_ROOT"
```

Observed baseline on 2026-10-29:

- `uv 0.11.28`, Python `3.13.14`, and `${PROJECT_ROOT}/.venv` are available.
- `${PROJECT_ROOT}/pyproject.toml` has no dependencies and requires Python `>=3.13`.
- `${PROJECT_ROOT}/main.py` is the `uv` starter script; `${PROJECT_ROOT}/README.md` is empty.
- Docker and Docker Compose are available; local `redis-server` is not installed.
- `${PROJECT_ROOT}/Redis_Pub_Sub_Fundamentals.md` is the domain reference.
- No `${PROJECT_ROOT}/CONTEXT.md`, tests, or existing application conventions exist.

This file is the execution plan, not the implementation. Do not create application code before the first failing test in Session 2.

## 2. Goals, semantics, and boundaries

### Required outcome

- `POST /channels/{channel}/messages` publishes a JSON request's `message` to Redis.
- `WS /ws/{channel}` subscribes one WebSocket connection to that Redis channel.
- Every active subscriber on the channel receives each message (one-to-many fan-out).
- Subscribers on other channels do not receive it.
- Disconnecting a WebSocket releases its dedicated Redis Pub/Sub connection.
- A browser page at `GET /` provides a two-tab manual demo.
- Automated integration tests use real Redis and public HTTP/WebSocket interfaces.

### Redis semantics to preserve and document

- Redis Pub/Sub is live, fire-and-forget messaging, not a durable queue.
- Offline or disconnected clients miss messages; there is no replay, history, or acknowledgment.
- Redis's per-subscriber output buffers are temporary, not per-channel persistence.
- Redis `PUBLISH` returns the number of subscribers to which Redis sent the message. The API calls this `subscriber_count`; it is not proof that clients processed or acknowledged it.
- Use Redis Streams or another durable system for retention, replay, or delivery guarantees. Those are non-goals here.

### Non-goals

Authentication, authorization, TLS termination, multi-process worker coordination, rate limiting, persistence, acknowledgments, pattern subscriptions, and production deployment. Do not add these during the core TDD slices.

## 3. Confirmed public contracts and test seams

The user selected WebSocket as the subscriber interface. Tests must observe these public seams, not private functions or mocked internal collaborators.

### Publish request

```http
POST /channels/{channel}/messages
Content-Type: application/json

{"message":"Hello from Redis!"}
```

Successful response (`200`):

```json
{"channel":"notifications","subscriber_count":2}
```

Validation failures return `422`. Redis publish failures return `503` without leaking credentials or internal exception details.

### WebSocket subscriber

Connect to `WS /ws/{channel}`. After Redis confirms the subscription, the server sends:

```json
{"type":"subscribed","channel":"notifications"}
```

This readiness frame is contractual: tests and browser clients wait for it before publishing, avoiding a subscription/publish race. A published payload arrives as:

```json
{"type":"message","channel":"notifications","message":"Hello from Redis!"}
```

The WebSocket is receive-only for application messages. Reject invalid channel names with close code `1008`; use `1011` for unexpected server failures when the connection can still close cleanly.

### Validation contract

- Channel: 1–128 characters matching `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`.
- Message: a JSON string of 1–10,000 characters. Do not silently trim or mutate a valid message.
- Use a unique channel such as `test:<uuid4 hex>` in every integration test. Do not assume Redis logical databases isolate Pub/Sub channels.

## 4. Target design and files

Create files only when their session reaches them:

```text
${PROJECT_ROOT}/app/__init__.py
${PROJECT_ROOT}/app/main.py          # app factory, lifespan, HTTP and WebSocket routes
${PROJECT_ROOT}/app/models.py        # request/response schemas and channel validation
${PROJECT_ROOT}/app/static/index.html
${PROJECT_ROOT}/tests/__init__.py
${PROJECT_ROOT}/tests/test_pubsub.py
${PROJECT_ROOT}/tests/test_validation.py
${PROJECT_ROOT}/tests/test_browser.py
${PROJECT_ROOT}/PLANS.md
${PROJECT_ROOT}/PROMPT.md
${PROJECT_ROOT}/compose.yaml
${PROJECT_ROOT}/.env.example
${PROJECT_ROOT}/.gitignore
${PROJECT_ROOT}/README.md
${PROJECT_ROOT}/pyproject.toml
${PROJECT_ROOT}/uv.lock
```

Architecture:

1. FastAPI lifespan creates one `redis.asyncio` client from `REDIS_URL` (default `redis://localhost:6379/0`) with `decode_responses=True`, checks `PING`, and stores it in `app.state`.
2. The publish route uses that shared client only for `PUBLISH`.
3. Each WebSocket creates its own `redis_client.pubsub()`. Pub/Sub connections are stateful and must not be shared across WebSockets or used for ordinary commands.
4. The WebSocket waits for Redis's `subscribe` acknowledgment before sending the `subscribed` frame. It forwards only Redis messages whose `type` is `message`.
5. Concurrently watch Redis and client disconnect events. A loop blocked only in `pubsub.listen()` cannot promptly observe a browser disconnect, so do not use that loop without disconnect handling.
6. In `finally`, cancel and await pending tasks and `await pubsub.aclose()` for each WebSocket. At shutdown, `await redis_client.aclose()` once for the shared client. Never close the shared client when one WebSocket disconnects.
7. Publish message text as the Redis payload; construct the documented JSON envelope at the WebSocket boundary.

## 5. How to execute and resume across sessions

At the start of every terminal/session:

```bash
export PROJECT_ROOT="/Users/adnan/Documents/adnanedu/adnanedu/fastapi_projects_new/fastapi_project_adnanedu/fastapi-projects/redis_pubsub"
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"
git switch redis-pub-sub
git status --short --branch
docker compose up -d redis
docker compose exec -T redis redis-cli PING
```

Expected Redis response: `PONG`. Before Session 1 creates `${PROJECT_ROOT}/compose.yaml`, skip the Docker commands. Preserve existing work when switching branches. Fetch and inspect remote changes before any pull; pull only into a clean tree with `git pull --ff-only origin redis-pub-sub`.

Rules:

- Complete sessions in order. In each TDD cycle, run the new test and capture the expected red result before editing application code.
- Work in vertical slices: one public behavior test, then the minimum implementation needed for that test. Do not write the whole suite up front.
- Do not mock Redis in end-to-end tests or assert private application state.
- Never mark a step complete if its test was skipped, xfailed, timed out, or failed unexpectedly.
- If a later test passes immediately because an earlier slice already provides that behavior, record it as a passing characterization test; do not break working code to manufacture red.
- Keep implementation and test runs inside `${PROJECT_ROOT}`. Do not edit unrelated parent-repository files.
- After each session, update these checkboxes and the Session Log with actual commands/results. Record any unresolved failure before pausing.

### Required Git workflow

- All implementation sessions use branch `redis-pub-sub`, created from `main`. The reusable executor is `${PROJECT_ROOT}/PROMPT.md`.
- Keep failed, partial, or unverified work uncommitted. Update the Session Log, stop, and resume the same session without discarding changes.
- After a session's complete exit check passes, update its checkboxes and Session Log, review the diff, and make one coherent session commit. Use an imperative message such as `feat: add redis pubsub websocket fan-out`; `${PROJECT_ROOT}/PROMPT.md` provides suggested messages for every session.
- Stage only this project by running `git add -- .` from `${PROJECT_ROOT}`. Inspect the staged files and run `git diff --cached --check` before committing.
- Push every completed session commit with `git push -u origin redis-pub-sub`, then confirm a clean working tree. Report the commit hash and push result.
- Complete and push Sessions 1–5 before using the final integration gate below. Merge and push `main` only after the merged result passes all verification.

---

## Session 1 — Reproducible environment and real Redis (no application code)

- [x] **1.1 Activate and record the baseline.**

  ```bash
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  python --version
  uv --version
  python -c 'import sys; print(sys.executable)'
  ```

  Confirm the interpreter is `${PROJECT_ROOT}/.venv/bin/python`.

- [x] **1.2 Install runtime and test dependencies.**

  ```bash
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  uv add fastapi redis 'uvicorn[standard]'
  uv add --dev pytest httpx pytest-timeout
  uv sync
  python -c 'import fastapi, httpx, pytest, redis, uvicorn; print("dependencies import successfully")'
  ```

  Expected effects: dependencies in `${PROJECT_ROOT}/pyproject.toml`, a created/updated `${PROJECT_ROOT}/uv.lock`, and packages in `${PROJECT_ROOT}/.venv`.

- [x] **1.3 Create `${PROJECT_ROOT}/compose.yaml` with one throwaway Redis 8 service.**

  Use image `redis:8-alpine`, service name `redis`, host port `6379` mapped to container port `6379`, and health check `redis-cli ping` with interval `1s`, timeout `1s`, and retries `10`. No volume is needed because this demonstrates non-durable Pub/Sub.

  ```bash
  cd "$PROJECT_ROOT"
  docker compose up -d redis
  docker compose ps
  docker compose exec -T redis redis-cli PING
  ```

  Required result: `PONG` and a healthy service. If port `6379` is occupied, stop the conflicting Redis or change the host port consistently in `${PROJECT_ROOT}/compose.yaml` and `REDIS_URL`; never run tests against an unknown server.

- [x] **1.4 Add local configuration and verify ignore rules.**

  Create `${PROJECT_ROOT}/.env.example` containing `REDIS_URL=redis://localhost:6379/0`. Do not commit real credentials. Review the existing `${PROJECT_ROOT}/.gitignore`; it covers virtual environments, Python/test caches, local environment files, build artifacts, IDE/OS files, logs, local databases, and Redis persistence files. Keep `.env.example`, `.python-version`, `compose.yaml`, and `uv.lock` tracked. Verify `git check-ignore .env .venv` prints both paths and `git check-ignore .env.example` produces no match.

- [x] **1.5 Add pytest discovery and deadlock protection to `${PROJECT_ROOT}/pyproject.toml`.**

  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  addopts = "-q --timeout=10"
  ```

  The timeout prevents a broken WebSocket receive from hanging indefinitely; it is not a substitute for correct cleanup.

**Session 1 exit check:** imports succeed, `uv.lock` exists, and Docker Redis returns `PONG`. No files under `${PROJECT_ROOT}/app` should exist yet.

## Session 2 — RED first, then the thin end-to-end fan-out slice

- [x] **2.1 Write only the first behavior test.**

  Create `${PROJECT_ROOT}/tests/__init__.py` and `${PROJECT_ROOT}/tests/test_pubsub.py`. Do not create `${PROJECT_ROOT}/app` yet. Put this exact test in `${PROJECT_ROOT}/tests/test_pubsub.py`:

  ```python
  import time
  from uuid import uuid4

  import pytest
  from fastapi.testclient import TestClient

  from app.main import app


  def test_publish_fans_out_and_cleans_up_disconnected_subscribers():
      channel = f"test:{uuid4().hex}"

      with TestClient(app) as client:
          with (
              client.websocket_connect(f"/ws/{channel}") as first,
              client.websocket_connect(f"/ws/{channel}") as second,
          ):
              assert first.receive_json() == {
                  "type": "subscribed",
                  "channel": channel,
              }
              assert second.receive_json() == {
                  "type": "subscribed",
                  "channel": channel,
              }

              response = client.post(
                  f"/channels/{channel}/messages",
                  json={"message": "Hello from Redis!"},
              )

              assert response.status_code == 200
              assert response.json() == {
                  "channel": channel,
                  "subscriber_count": 2,
              }
              expected = {
                  "type": "message",
                  "channel": channel,
                  "message": "Hello from Redis!",
              }
              assert first.receive_json() == expected
              assert second.receive_json() == expected

          deadline = time.monotonic() + 2
          while True:
              response = client.post(
                  f"/channels/{channel}/messages",
                  json={"message": "cleanup probe"},
              )
              assert response.status_code == 200
              if response.json()["subscriber_count"] == 0:
                  break
              if time.monotonic() >= deadline:
                  pytest.fail("Redis subscribers remained after WebSocket disconnect")
              time.sleep(0.05)
  ```

  This is one user journey: two clients subscribe, both receive a fan-out message, and disconnected clients stop counting as subscribers. Unique channels prevent cross-test interference.

- [x] **2.2 Run the test and prove RED before implementation.**

  ```bash
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  docker compose up -d redis
  uv run pytest "$PROJECT_ROOT/tests/test_pubsub.py" -q
  ```

  Required red result: collection fails with `ModuleNotFoundError: No module named 'app'`. Record the command and failure in the Session Log. If it fails because Redis or a dependency is unavailable, fix Session 1 first; that is not the intended application red.

- [x] **2.3 Implement only the vertical slice needed by this test.**

  Create `${PROJECT_ROOT}/app/__init__.py`, `${PROJECT_ROOT}/app/models.py`, and `${PROJECT_ROOT}/app/main.py`:

  1. Define a request model with a string `message` and a response model with `channel` and integer `subscriber_count`. Detailed length/channel constraints are deliberately deferred to Session 3.
  2. Add an async lifespan that creates and pings the shared `redis.asyncio` client before `yield`, then closes it with `aclose()` in `finally`. Expose a module-level `app` for `uvicorn app.main:app` and the test import.
  3. Add the publish route. Await Redis `publish(channel, request.message)`, return the documented response, and do not invent persistence or acknowledgment semantics.
  4. Add the WebSocket route with a dedicated Pub/Sub object. Accept the connection, subscribe, consume the matching Redis `subscribe` acknowledgment, and only then send the `subscribed` frame.
  5. Forward live `message` events using the documented envelope. Ignore `subscribe`, `unsubscribe`, and other control frames.
  6. Run Redis forwarding and WebSocket disconnect detection concurrently. The disconnect watcher should ignore incoming application frames and finish only on `websocket.disconnect`. When either side finishes, cancel and await the other task.
  7. Always close that WebSocket's Pub/Sub object in `finally`. Keep the shared Redis client open for other requests.

  Prefer `redis.asyncio`, `get_message(ignore_subscribe_messages=True, timeout=None)` for forwarding, explicit `subscribe`-acknowledgment handling for readiness, and `asyncio.wait(..., return_when=asyncio.FIRST_COMPLETED)` or an equivalently correct task pattern. Do not use synchronous `redis.Redis` in async routes.

- [x] **2.4 Run the same test until GREEN, then run the whole suite.**

  ```bash
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  uv run pytest "$PROJECT_ROOT/tests/test_pubsub.py" -q
  uv run pytest
  uv run python -m compileall -q "$PROJECT_ROOT/app" "$PROJECT_ROOT/tests"
  ```

  Required result: one test passed with no unclosed-task, unclosed-connection, or other resource-cleanup warnings. If cleanup fails, inspect task cancellation and `pubsub.aclose()` rather than weakening the assertion or increasing the timeout.

**Session 2 exit check:** preserve the earlier red evidence; the same test now passes against real Redis and disconnect cleanup reaches `subscriber_count == 0`.

## Session 3 — Validation and channel isolation, one behavior at a time

Keep Redis running. Add each test to the indicated file, run it before the related implementation, and record its actual result.

- [x] **3.1 RED: reject invalid message lengths through the HTTP seam.**

  In `${PROJECT_ROOT}/tests/test_validation.py`, add `test_message_length_validation`: inside `with TestClient(app) as client`, POST to a fresh valid channel with `{"message": ""}` and then with a string of 10,001 characters. Assert `422` for both; no WebSocket is needed.

  ```bash
  uv run pytest "$PROJECT_ROOT/tests/test_validation.py::test_message_length_validation" -q
  ```

  Expected initial red: the empty message currently publishes and returns `200`. Only then add Pydantic `Field(min_length=1, max_length=10_000)` to the request model. Re-run the new test and then all tests.

- [x] **3.2 RED: reject an invalid HTTP channel.**

  Add `test_publish_rejects_invalid_channel`: POST to `/channels/-invalid/messages` with a valid body and assert `422`. Run it and confirm the current route returns `200` instead. Then apply the shared channel regular expression with FastAPI `Path(pattern=...)` (or equivalent public-request validation) and make the test green without changing valid channel behavior.

- [x] **3.3 RED: reject an invalid WebSocket channel.**

  Add `test_websocket_rejects_invalid_channel`: use `pytest.raises(WebSocketDisconnect)` around connecting to `/ws/-invalid`, then assert `exc_info.value.code == 1008`. Run it before implementation and record the actual mismatch. Add WebSocket-side validation using the same channel rule; HTTP path validation alone does not protect the WebSocket route. Close before creating a Redis Pub/Sub resource.

- [x] **3.4 Verify channel isolation through observable messages.**

  Add `test_messages_do_not_cross_channels` to `${PROJECT_ROOT}/tests/test_pubsub.py`:

  1. Create two unique channels and open one WebSocket on each; consume both readiness frames.
  2. Publish `only-a` to channel A and assert its response has `subscriber_count == 1`.
  3. Assert WebSocket A's next frame is the exact `only-a` envelope.
  4. Publish `only-b` to channel B. Assert WebSocket B's next frame is exactly `only-b`, not a leaked `only-a` frame.

  ```bash
  uv run pytest "$PROJECT_ROOT/tests/test_pubsub.py::test_messages_do_not_cross_channels" -q
  ```

  This may pass immediately because Redis subscriptions already isolate channels. If so, record it as a green characterization test; no production change is needed. If red, fix subscription/forwarding behavior rather than adding test sleeps.

- [x] **3.5 Verify validation boundaries and regression safety.**

  Add `test_valid_boundaries_are_accepted`: through HTTP, a 128-character valid channel and a 10,000-character message should return `200` and `subscriber_count == 0` with no subscribers. Run it before changing anything. It should characterize the completed validation; if it fails, correct only the relevant boundary logic.

  Finish with:

  ```bash
  uv run pytest
  uv run python -m compileall -q "$PROJECT_ROOT/app" "$PROJECT_ROOT/tests"
  ```

**Session 3 exit check:** all validation and isolation tests pass without skips; invalid resources do not create subscriptions; the original fan-out/cleanup test remains green.

## Session 4 — Browser demo behind the same public API

- [x] **4.1 RED: test the browser entry point before adding it.**

  Create `${PROJECT_ROOT}/tests/test_browser.py` with `test_browser_demo_is_served`: using `TestClient`, GET `/`, assert status `200`, an HTML content type, and visible markers for a channel input, message input, connect action, send action, and message list. Run:

  ```bash
  uv run pytest "$PROJECT_ROOT/tests/test_browser.py" -q
  ```

  Required initial red: `404`. Do not add `${PROJECT_ROOT}/app/static/index.html` until this result is observed.

- [x] **4.2 Implement the smallest usable browser client.**

  Add `${PROJECT_ROOT}/app/static/index.html` and serve it at `GET /` (or serve an equivalent HTML response). It must:

  1. Provide channel/message inputs, Connect/Disconnect and Send buttons, connection status, and a message list.
  2. Build the WebSocket URL using the current hostname and `wss:` for HTTPS, otherwise `ws:`; URL-encode the channel.
  3. Wait for the `subscribed` JSON frame before enabling Send. Display messages with `textContent`, never `innerHTML`, so message text is not executed as HTML.
  4. Publish with `fetch()` to the existing HTTP endpoint and show HTTP validation/error responses. Do not create a second browser-to-server publish protocol over WebSocket.
  5. Close the WebSocket on Disconnect and before page unload; reset UI state on close/error.

  Re-run the browser test and all tests. Do not mark this complete based only on HTML assertions.

- [x] **4.3 Manually prove two-browser-tab fan-out.**

  Terminal A:

  ```bash
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  docker compose up -d redis
  export REDIS_URL="redis://localhost:6379/0"
  uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
  ```

  Open `http://127.0.0.1:8000` in two tabs. In both, enter `notifications`, click Connect, and wait for subscribed status. Send `Hello from Redis!` from the first tab. Required observations: both tabs display exactly one message; the HTTP result reports one subscriber with one tab and two with both; a third channel receives nothing. Disconnect one tab, send again, and confirm only the connected tab receives it.

  Interactive docs at `http://127.0.0.1:8000/docs` document HTTP; OpenAPI does not document this WebSocket contract, so `${PROJECT_ROOT}/README.md` must do so.

**Session 4 exit check:** the entry-point test and all prior tests pass, and manual two-tab fan-out/disconnect observations are recorded in the Session Log.

## Session 5 — Failure behavior, documentation, and final verification

- [x] **5.1 RED: observe publish behavior during a real Redis outage.**

  With Redis healthy, start Uvicorn on `127.0.0.1:8000`. Then run:

  ```bash
  cd "$PROJECT_ROOT"
  docker compose stop redis
  curl --max-time 15 -sS -i -X POST \
    'http://127.0.0.1:8000/channels/outage-check/messages' \
    -H 'Content-Type: application/json' \
    -d '{"message":"should return 503"}'
  ```

  Before implementation, record the actual `500` or disconnected-request result as red; the required behavior is `503`. Add handling around the publish operation for `redis.exceptions.RedisError` that returns/raises an HTTP `503` with a safe detail such as `Redis publish unavailable`. Do not catch `Exception`, hide programming errors, or expose `REDIS_URL`.

  Repeat the same `curl` while Redis is stopped and require `503`. Then recover and prove reconnection:

  ```bash
  docker compose up -d redis
  docker compose exec -T redis redis-cli PING
  curl --max-time 15 -sS -i -X POST \
    'http://127.0.0.1:8000/channels/outage-check/messages' \
    -H 'Content-Type: application/json' \
    -d '{"message":"Redis is back"}'
  ```

  Required recovered result: `200` with `subscriber_count: 0` when no subscriber is connected. Also inspect WebSocket error paths: Redis failures must cancel tasks, close dedicated Pub/Sub resources, and use close code `1011` where possible. If this inspection finds a bug, add a public-seam regression test and observe it fail before fixing that bug.

- [x] **5.2 Write complete operator documentation in `${PROJECT_ROOT}/README.md`.**

  Include prerequisites (`uv` and Docker Compose), the absolute project root, environment activation, `uv sync`, Redis start/stop/health commands, `REDIS_URL` configuration, Uvicorn startup, `pytest`, the browser walkthrough, and an HTTP `curl` example. Explicitly state that `${PROJECT_ROOT}/.env.example` is a template and is not loaded automatically; export `REDIS_URL` or rely on the local default.

  Document both public contracts and example JSON frames, validation limits, `subscriber_count` semantics, readiness-frame rationale, one-Pub/Sub-object-per-WebSocket lifecycle, and graceful shutdown. Include the fire-and-forget/offline-message-loss warning and point to `${PROJECT_ROOT}/Redis_Pub_Sub_Fundamentals.md`. Mention that `/docs` covers HTTP but not WebSocket.

- [x] **5.3 Review without changing the public contracts.**

  Inspect every created file. Check for synchronous Redis calls in async routes, shared Pub/Sub objects, missing `aclose()`, uncancelled tasks, publishes before subscription readiness, unsafe browser HTML insertion, secret leakage, tests of private internals, and claims of durability. Run a separate code-review/refactor pass only after all tests are green; after any refactor, rerun all verification.

- [x] **5.4 Run final verification from the project root.**

  Stop Uvicorn from the manual session, then use a fresh terminal:

  ```bash
  export PROJECT_ROOT="/Users/adnan/Documents/adnanedu/adnanedu/fastapi_projects_new/fastapi_project_adnanedu/fastapi-projects/redis_pubsub"
  cd "$PROJECT_ROOT"
  source "$PROJECT_ROOT/.venv/bin/activate"
  uv sync --frozen
  docker compose config --quiet
  docker compose up -d redis
  docker compose exec -T redis redis-cli PING
  uv run pytest
  uv run python -m compileall -q "$PROJECT_ROOT/app" "$PROJECT_ROOT/tests"
  git status --short -- .
  ```

  Required results: `PONG`, all tests passed with none skipped/xfailed, no compile errors, and changes limited to this project's intended files. Update all Session 5 technical checkboxes and the Session Log, then commit and push Session 5 using the Required Git workflow.

  Optional cleanup after all observations are recorded:

  ```bash
  docker compose down
  ```

### Final integration gate — merge only after Sessions 1–5 pass

Preconditions: every technical checkbox is complete, manual browser evidence is recorded, the Session 5 commit is pushed to `origin/redis-pub-sub`, and the feature-branch working tree is clean. From `${PROJECT_ROOT}`, run:

```bash
git switch main
git pull --ff-only origin main
git merge --no-ff redis-pub-sub -m "merge: complete redis pubsub fastapi demo"
```

If conflicts occur, stop the command sequence, resolve them while preserving both sides' intended behavior, and complete the merge. Then verify the merged result before pushing:

```bash
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"
uv sync --frozen
docker compose config --quiet
docker compose up -d redis
docker compose exec -T redis redis-cli PING
uv run pytest
uv run python -m compileall -q "$PROJECT_ROOT/app" "$PROJECT_ROOT/tests"
git push origin main
git status --short --branch
git log -1 --oneline --decorate
```

Push `main` only when every merged-result check passes. Confirm `main` and `origin/main` point to the merged commit and report the feature, merge, and push results.

## 6. Definition of done

- [x] Initial red evidence is recorded before any application implementation.
- [x] Real Redis fan-out reaches two WebSocket subscribers with the exact documented payload.
- [x] Readiness prevents subscription races; channel isolation and boundary validation are tested.
- [x] Disconnected clients are cleaned up and publish returns an eventual subscriber count of zero.
- [x] Browser fan-out is manually observed in two tabs.
- [x] Redis outage returns `503`, recovery works, and no secret/internal error is exposed.
- [x] README instructions work from a fresh terminal and explain non-durable semantics.
- [x] `uv sync --frozen`, Compose validation, all tests, and bytecode compilation pass.

## 7. Session Log (update after every work session)

| Date/session | Steps completed | Red evidence (command + expected failure) | Green/manual evidence | Remaining issue or next step |
|---|---|---|---|---|
| 2026-10-29 planning | Read fundamentals; confirmed WebSocket seam; created plan, executor prompt, feature branch, and ignore rules | Not run yet; Session 2 must produce it | Environment and Docker availability inspected; planning task committed and pushed | Execute Session 1 |
| 2026-10-30 Session 1 | Completed 1.1–1.5: recorded Python 3.13.14, uv 0.11.28, and the project `.venv` interpreter; added runtime/test dependencies; created `uv.lock`, Redis 8 Compose service, `.env.example`, and pytest discovery/timeout configuration | Not applicable: Session 1 creates no application test or code; Session 2 initial RED remains pending | `uv sync --frozen` and dependency imports passed; Compose validation passed; Redis is healthy and `redis-cli PING` returned `PONG`; ignore rules and pytest configuration verified; no `app/` directory exists | Execute Session 2: add the exact fan-out test and capture pre-implementation RED |
| 2026-10-30 Session 2 | Completed 2.1–2.4: added the exact public fan-out/cleanup test; implemented the async Redis lifespan, publish route, per-WebSocket Pub/Sub, subscribe readiness, concurrent forwarding/disconnect detection, and shielded resource cleanup | `uv run pytest "$PROJECT_ROOT/tests/test_pubsub.py" -q` before creating `app/`: collection failed as expected with `ModuleNotFoundError: No module named 'app'` | Docker Redis `PING` returned `PONG`; the focused test and `uv run pytest` passed (`1 passed`), including the eventual post-disconnect `subscriber_count == 0`; `compileall` passed; no skips/xfails or resource-cleanup warnings (one Starlette `httpx` deprecation warning); no manual checks in this session | Execute Session 3: validation and channel isolation, one behavior at a time |
| 2026-10-30 Session 3 | Completed 3.1–3.5: enforced 1–10,000-character messages and the shared 1–128-character channel rule on HTTP and WebSocket; invalid WebSockets close with `1008` before accept or Pub/Sub creation; added channel-isolation and valid-boundary coverage | `uv run pytest "$PWD/tests/test_validation.py::test_message_length_validation" -q`: empty message returned `200` instead of `422`; `uv run pytest "$PWD/tests/test_validation.py::test_publish_rejects_invalid_channel" -q`: invalid channel returned `200` instead of `422`; `uv run pytest "$PWD/tests/test_validation.py::test_websocket_rejects_invalid_channel" -q`: `DID NOT RAISE WebSocketDisconnect` instead of close code `1008` | All focused validation tests passed after their implementations; channel isolation and valid boundaries passed immediately as green characterization tests; `uv run pytest` passed (`6 passed`, no skips/xfails) and `compileall` passed; Docker Redis `PING` returned `PONG`; no manual checks in this session | Execute Session 4: add the browser entry-point test and capture its `404` RED before implementing the demo |
| 2026-10-30 Session 4 | Completed 4.1–4.3: added the browser entry-point test; served a static browser client at `GET /`; reused the existing HTTP/WebSocket contracts with readiness-gated Send and safe `textContent` rendering; manually verified fan-out, subscriber counts, channel isolation, and disconnect behavior | `uv run pytest "$PWD/tests/test_browser.py" -q` before adding the route or static HTML: expected initial `404`, observed `assert 404 == 200` | Focused browser test passed; `uv run pytest` passed (`7 passed`, no skips/xfails); `compileall` passed; Redis `PING` returned `PONG` and live `GET /` returned `200`. User confirmed all manual checks: `Solo check` reached Tab A once with `subscriber_count == 1`; `Hello from Redis!` reached Tabs A and B once each with count `2`; `Channel isolation` reached A/B once each and not `other-channel` Tab C; after B disconnected, `After disconnect` reached only A with count `1` | Execute Session 5: capture the real Redis outage RED, add safe `503`/recovery behavior, and complete documentation/final verification |
| 2026-10-30 Session 5 | Completed 5.1–5.4: mapped Redis publish failures to safe `503` responses; propagated WebSocket Redis task failures to close `1011` while preserving shielded task/Pub/Sub cleanup; added a real-outage public-seam regression test; wrote complete operator documentation and reviewed all project files | `docker compose stop redis` followed by the documented publish `curl` before implementation returned `500 Internal Server Error` instead of `503`; `uv run pytest "$PWD/tests/test_pubsub.py::test_websocket_closes_with_1011_when_redis_fails" -q` initially timed out after `10s` waiting for a close frame, matching the live pre-fix abnormal close `1006` | The identical stopped-Redis `curl` returned `503` with only `{"detail":"Redis publish unavailable"}`; recovery returned `PONG`, then HTTP `200` with `subscriber_count: 0`. The focused WebSocket test passed, and live Uvicorn closed with `1011` during a real outage. Final `uv sync --frozen`, Compose validation, Redis `PING`, and `compileall` passed; `uv run pytest` reported `8 passed` with no skips/xfails (one known Starlette `httpx` deprecation warning). No new browser checks; Session 4 manual evidence remains valid | Sessions 1–5 complete and verified; next run performs only the final integration gate: merge and verify `redis-pub-sub` on `main` |

## 8. Useful recovery commands

```bash
cd "$PROJECT_ROOT"
source "$PROJECT_ROOT/.venv/bin/activate"
docker compose ps
docker compose logs --tail=100 redis
docker compose restart redis
docker compose exec -T redis redis-cli PING
uv run pytest -vv
```

If resuming after a failure, do not start a later session. Re-run the failed public behavior, preserve the error in the log, fix the smallest relevant implementation detail, and return to that session's exit check.
