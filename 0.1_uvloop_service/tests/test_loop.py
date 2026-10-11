import asyncio

from app.core.loop_inspector import get_loop_info


def test_uvloop_detected_when_installed():
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    info = get_loop_info()
    assert isinstance(info.is_uvloop, bool)
    loop.close()
