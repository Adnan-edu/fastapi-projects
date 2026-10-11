import asyncio
import time
import sys
import httpx

BASE_UVLOOP = "http://127.0.0.1:8000"
BASE_DEFAULT = "http://127.0.0.1:8001"

PAYLOAD = [{"id": i, "data": f"item-{i}"} for i in range(50)]


async def check_loop(client: httpx.AsyncClient, base: str):
    r = await client.get(f"{base}/metrics/loop")
    print("Loop info:", r.json())


async def fire_batch(client: httpx.AsyncClient, base: str):
    r = await client.post(f"{base}/ingest/batch", json=PAYLOAD)
    r.raise_for_status()


async def run_test(label: str, base: str, concurrency: int = 1000):
    async with httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=500)) as client:
        await check_loop(client, base)
        start = time.perf_counter()
        await asyncio.gather(*[fire_batch(client, base) for _ in range(concurrency)])
        elapsed = time.perf_counter() - start
    rps = concurrency / elapsed
    print(f"[{label}] Elapsed: {elapsed:.2f}s | RPS: {rps:.0f}")
    return elapsed, rps


async def main():
    print("Load test: comparing uvloop vs default asyncio")
    print("Make sure both servers are running:")
    print("  Terminal 1: ./start.sh          (port 8000, uvloop)")
    print("  Terminal 2: ./start_default.sh  (port 8001, default loop)")
    print()

    try:
        uv_elapsed, uv_rps = await run_test("uvloop", BASE_UVLOOP)
    except Exception as e:
        print(f"[uvloop] Connection failed: {e}")
        sys.exit(1)

    try:
        def_elapsed, def_rps = await run_test("default", BASE_DEFAULT)
    except Exception as e:
        print(f"[default] Connection failed: {e}")
        sys.exit(1)

    print("\n--- Comparison ---")
    print(f"uvloop   : {uv_elapsed:.2f}s  {uv_rps:.0f} req/s")
    print(f"default  : {def_elapsed:.2f}s  {def_rps:.0f} req/s")
    if def_elapsed:
        improvement = (def_elapsed - uv_elapsed) / def_elapsed * 100
        print(f"Improvement: {improvement:.1f}% faster with uvloop")


if __name__ == "__main__":
    asyncio.run(main())
