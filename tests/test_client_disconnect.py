import asyncio
from types import SimpleNamespace

from runtime.bridge.pipeline import BridgePipeline
from runtime.bridge.bus import client_disconnected


def test_closed_client_is_not_a_server_fault() -> None:
    assert client_disconnected(ConnectionResetError(10054, "reset"))
    assert client_disconnected(ConnectionAbortedError(10053, "abort"))


def test_publish_to_closed_client_returns_false() -> None:
    class Bus:
        async def publish(self, event: object) -> None:
            raise ConnectionResetError(10054, "reset")

    pipe = BridgePipeline(router=SimpleNamespace())  # type: ignore[arg-type]
    ok = asyncio.run(pipe._publish(Bus(), SimpleNamespace(type="agent.cancel")))  # type: ignore[arg-type]
    assert ok is False
