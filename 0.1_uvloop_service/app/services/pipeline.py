import asyncio
from typing import List


async def validate_item(item: dict) -> dict:
    await asyncio.sleep(0.001)
    item["valid"] = True
    return item


async def process_batch(items: List[dict]) -> List[dict]:
    tasks = [asyncio.create_task(validate_item(item)) for item in items]
    return await asyncio.gather(*tasks)


async def generate_stream_items(count: int):
    async def fetch_one(i: int):
        await asyncio.sleep(0.002)
        return {"index": i, "status": "ok"}

    tasks = [asyncio.create_task(fetch_one(i)) for i in range(count)]
    for task in asyncio.as_completed(tasks):
        yield await task
