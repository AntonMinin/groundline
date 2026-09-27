import asyncio
import weakref

import httpx

_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = weakref.WeakKeyDictionary()


def client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    shared = _clients.get(loop)
    if shared is None or shared.is_closed:
        shared = _clients[loop] = httpx.AsyncClient(
            timeout=30, limits=httpx.Limits(max_keepalive_connections=20, keepalive_expiry=300)
        )
    return shared
