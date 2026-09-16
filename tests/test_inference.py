import asyncio
import time

from app import inference


async def test_local_inference_calls_never_overlap():
    state = {"active": 0, "peak": 0}

    def work(index: int) -> int:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        state["active"] -= 1
        return index

    results = await asyncio.gather(*(inference.run_inference(work, index) for index in range(4)))

    assert state["peak"] == 1
    assert sorted(value for value, _ in results) == [0, 1, 2, 3]
    assert max(waited for _, waited in results) > 0


async def test_waiting_counter_returns_to_zero():
    assert inference.waiting() == 0
    await inference.run_inference(lambda: None)
    assert inference.waiting() == 0


async def test_failures_release_the_lock():
    def boom():
        raise RuntimeError("model failed")

    try:
        await inference.run_inference(boom)
    except RuntimeError:
        pass

    assert inference.waiting() == 0
    value, _ = await inference.run_inference(lambda: "still works")
    assert value == "still works"
