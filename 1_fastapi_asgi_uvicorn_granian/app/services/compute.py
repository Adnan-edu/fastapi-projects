import asyncio
import time


def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


def light_compute(n: int = 10000) -> dict:
    start = time.perf_counter()
    result = fibonacci(n)
    elapsed = time.perf_counter() - start
    return {"input": n, "result": result, "elapsed_seconds": round(elapsed, 6)}


async def io_simulated(delay: float = 0.5) -> dict:
    start = time.perf_counter()
    await asyncio.sleep(delay)
    elapsed = time.perf_counter() - start
    return {"simulated_delay": delay, "actual_elapsed_seconds": round(elapsed, 6)}