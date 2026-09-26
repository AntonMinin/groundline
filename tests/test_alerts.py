import logging

import httpx
import pytest

from app import alerts
from app.config import settings

TOKEN = "123456789:AAH-secret-bot-token"


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    state = {"handler": None}
    real = httpx.AsyncClient

    def factory(**kwargs):
        return real(transport=httpx.MockTransport(state["handler"]), **kwargs)

    monkeypatch.setattr(alerts.httpx, "AsyncClient", factory)
    return state


def refused(request):
    return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})


def unreachable(request):
    raise httpx.ConnectError(f"cannot reach {request.url}", request=request)


@pytest.mark.parametrize("handler", [refused, unreachable], ids=["http-error", "network-error"])
async def test_a_failed_alert_never_logs_the_bot_token(telegram, caplog, handler):
    telegram["handler"] = handler
    with caplog.at_level(logging.DEBUG, logger="app.alerts"):
        await alerts.send("Groundline: test")
    assert "Could not deliver a Telegram alert" in caplog.text
    assert TOKEN not in caplog.text
    assert all(TOKEN not in str(record.exc_info) for record in caplog.records)


async def test_the_status_is_still_logged(telegram, caplog):
    telegram["handler"] = refused
    with caplog.at_level(logging.WARNING, logger="app.alerts"):
        await alerts.send("Groundline: test")
    assert "Telegram answered 400" in caplog.text
