import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LoopInfo:
    loop_type: str
    loop_module: str
    is_uvloop: bool
    timestamp: str


def get_loop_info() -> LoopInfo:
    loop = asyncio.get_event_loop()
    cls = loop.__class__
    return LoopInfo(
        loop_type=f"{cls.__module__}.{cls.__name__}",
        loop_module=cls.__module__,
        is_uvloop=cls.__module__.startswith("uvloop"),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
