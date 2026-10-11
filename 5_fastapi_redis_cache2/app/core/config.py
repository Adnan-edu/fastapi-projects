from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Redis connection ---
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 20
    redis_socket_timeout: float = 2.0
    redis_retry_attempts: int = 2

    # --- Cache TTLs (seconds) ---
    cache_ttl: int = 30  # legacy weather endpoint
    cache_prefix: str = "fastapi-cache"
    cache_ttl_product: int = 60
    cache_ttl_list: int = 15
    cache_ttl_search: int = 30
    cache_ttl_featured: int = 60

    # --- Simulated DB latency (keeps focus on Redis, no Postgres needed) ---
    weather_simulated_delay: float = 2.0
    simulated_db_delay: float = 0.4

    # --- Patterns ---
    idempotency_ttl: int = 86400  # 24h
    rate_limit_max: int = 10
    rate_limit_window_s: int = 60
    cart_ttl_s: int = 1800  # 30 min
    lock_ttl_ms: int = 5000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
