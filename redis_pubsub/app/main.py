import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket

from app.models import PublishRequest, PublishResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    app.state.redis_client = redis_client
    try:
        await redis_client.ping()
        yield
    finally:
        await redis_client.aclose()


app = FastAPI(lifespan=lifespan)


@app.post("/channels/{channel}/messages", response_model=PublishResponse)
async def publish_message(channel: str, request: PublishRequest) -> PublishResponse:
    subscriber_count = await app.state.redis_client.publish(channel, request.message)
    return PublishResponse(channel=channel, subscriber_count=subscriber_count)


async def forward_messages(websocket: WebSocket, pubsub: redis.client.PubSub, channel: str) -> None:
    while True:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=None)
        if message is not None and message["type"] == "message":
            await websocket.send_json(
                {
                    "type": "message",
                    "channel": channel,
                    "message": message["data"],
                }
            )


async def watch_disconnect(websocket: WebSocket) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@app.websocket("/ws/{channel}")
async def subscribe_to_channel(websocket: WebSocket, channel: str) -> None:
    await websocket.accept()
    pubsub = websocket.app.state.redis_client.pubsub()
    tasks: set[asyncio.Task[None]] = set()
    try:
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(timeout=None)
            if (
                message is not None
                and message["type"] == "subscribe"
                and message["channel"] == channel
            ):
                break
        await websocket.send_json({"type": "subscribed", "channel": channel})

        tasks = {
            asyncio.create_task(forward_messages(websocket, pubsub, channel)),
            asyncio.create_task(watch_disconnect(websocket)),
        }
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await pubsub.aclose()
