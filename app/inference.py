import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
_lock = asyncio.Lock()
_waiting = 0


def waiting() -> int:
    return _waiting


def configure_torch() -> None:
    if settings.torch_num_threads <= 0:
        return
    import torch

    torch.set_num_threads(settings.torch_num_threads)
    log.info("torch intra-op threads limited to %d", settings.torch_num_threads)


async def run_inference(function: Callable[..., Any], *args: Any) -> tuple[Any, float]:
    global _waiting
    _waiting += 1
    started = time.perf_counter()
    try:
        async with _lock:
            waited_ms = (time.perf_counter() - started) * 1000
            if waited_ms > 1000:
                log.info("%s waited %.0f ms for the inference lock", getattr(function, "__name__", function), waited_ms)
            return await asyncio.get_running_loop().run_in_executor(_executor, function, *args), waited_ms
    finally:
        _waiting -= 1


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
