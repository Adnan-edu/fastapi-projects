from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.config import settings

result_backend = RedisAsyncResultBackend(
    redis_url=settings.redis_url,
    result_ex_time=3600,
    keep_results=True,
)

broker = RedisStreamBroker(
    url=settings.redis_url,
).with_result_backend(result_backend)