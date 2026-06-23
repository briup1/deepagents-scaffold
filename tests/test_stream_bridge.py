"""Tests for MemoryStreamBridge publish/subscribe/Last-Event-ID/cleanup."""

from __future__ import annotations

import asyncio

import pytest

from scaffold.runtime.stream_bridge import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    MemoryStreamBridge,
    StreamEvent,
)

RUN_ID = "run-1"


@pytest.fixture
def bridge() -> MemoryStreamBridge:
    return MemoryStreamBridge(queue_maxsize=8)


async def collect_events(
    bridge: MemoryStreamBridge,
    run_id: str = RUN_ID,
    **kwargs,
) -> list:
    """Drain a bridge until ``END_SENTINEL`` and return collected items."""
    items: list = []
    async for item in bridge.subscribe(run_id, **kwargs):
        if item is END_SENTINEL:
            break
        items.append(item)
    return items


class TestPublishSubscribe:
    async def test_publish_and_receive(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "hello")
        await bridge.publish(RUN_ID, "custom", "world")
        await bridge.publish_end(RUN_ID)

        items = await collect_events(bridge)

        assert len(items) == 2
        assert items[0].data == "hello"
        assert items[0].event == "message"
        assert items[1].data == "world"
        assert items[1].event == "custom"

    async def test_multiple_runs_are_isolated(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish("run-a", "message", "a")
        await bridge.publish("run-b", "message", "b")
        await bridge.publish_end("run-a")
        await bridge.publish_end("run-b")

        a_items = await collect_events(bridge, run_id="run-a")
        b_items = await collect_events(bridge, run_id="run-b")

        assert [e.data for e in a_items] == ["a"]
        assert [e.data for e in b_items] == ["b"]

    async def test_multiple_consumers_receive_same_events(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "a")
        await bridge.publish(RUN_ID, "message", "b")
        await bridge.publish_end(RUN_ID)

        first = await collect_events(bridge)
        second = await collect_events(bridge)

        assert [e.data for e in first] == ["a", "b"]
        assert [e.data for e in second] == ["a", "b"]


class TestLastEventId:
    async def test_resume_after_last_event_id(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "one")
        id_two = (await _last_event_id(bridge, RUN_ID, 1))[0]
        await bridge.publish(RUN_ID, "message", "three")
        await bridge.publish_end(RUN_ID)

        items = await collect_events(bridge, last_event_id=id_two)

        assert len(items) == 1
        assert items[0].data == "three"

    async def test_unknown_last_event_id_falls_back_to_start(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "one")
        await bridge.publish(RUN_ID, "message", "two")
        await bridge.publish_end(RUN_ID)

        items = await collect_events(bridge, last_event_id="missing")

        assert len(items) == 2
        assert [e.data for e in items] == ["one", "two"]

    async def test_pruned_id_falls_back_to_earliest_retained(self, bridge: MemoryStreamBridge) -> None:
        for i in range(10):
            await bridge.publish(RUN_ID, "message", f"evt-{i}")
        await bridge.publish_end(RUN_ID)

        items = await collect_events(bridge, last_event_id="0")
        assert len(items) == 8
        assert [e.data for e in items] == [f"evt-{i}" for i in range(2, 10)]


class TestCleanup:
    async def test_buffer_drops_old_events(self, bridge: MemoryStreamBridge) -> None:
        for i in range(10):
            await bridge.publish(RUN_ID, "message", f"evt-{i}")

        await bridge.publish_end(RUN_ID)

        items = await collect_events(bridge)
        assert len(items) == 8
        assert [e.data for e in items] == [f"evt-{i}" for i in range(2, 10)]

    async def test_old_id_mappings_are_pruned(self, bridge: MemoryStreamBridge) -> None:
        ids = []
        for i in range(10):
            await bridge.publish(RUN_ID, "message", f"evt-{i}")
            ids.append(bridge._streams[RUN_ID].events[-1].id)

        mapping = bridge._id_to_offset.get(RUN_ID, {})
        assert ids[0] not in mapping
        assert ids[1] not in mapping
        assert ids[-1] in mapping

    async def test_cleanup_removes_run_state(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "x")
        await bridge.publish_end(RUN_ID)
        await bridge.cleanup(RUN_ID)

        assert RUN_ID not in bridge._streams
        assert RUN_ID not in bridge._counters
        assert RUN_ID not in bridge._id_to_offset


class TestLifecycle:
    async def test_publish_end_yields_end_sentinel(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "only")
        await bridge.publish_end(RUN_ID)

        items = []
        async for item in bridge.subscribe(RUN_ID):
            items.append(item)

        assert items[-1] is END_SENTINEL

    async def test_empty_stream_yields_end_sentinel(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish_end(RUN_ID)

        items = []
        async for item in bridge.subscribe(RUN_ID):
            items.append(item)

        assert items == [END_SENTINEL]

    async def test_close_clears_all_runs(self, bridge: MemoryStreamBridge) -> None:
        await bridge.publish(RUN_ID, "message", "x")
        await bridge.publish("run-2", "message", "y")
        await bridge.close()

        assert not bridge._streams
        assert not bridge._counters
        assert not bridge._id_to_offset


class TestHeartbeat:
    async def test_heartbeat_emitted_while_waiting(self, bridge: MemoryStreamBridge) -> None:
        collected = []
        event_received = asyncio.Event()

        async def consumer() -> None:
            async for item in bridge.subscribe(RUN_ID, heartbeat_interval=0.05):
                collected.append(item)
                if isinstance(item, StreamEvent) and item.data == "x":
                    event_received.set()
                    break

        task = asyncio.create_task(consumer())
        await asyncio.sleep(0.12)
        await bridge.publish(RUN_ID, "message", "x")
        await asyncio.wait_for(event_received.wait(), timeout=1.0)
        await task

        assert any(item is HEARTBEAT_SENTINEL for item in collected)
        assert any(isinstance(item, StreamEvent) and item.data == "x" for item in collected)


class TestEdgeCases:
    async def test_invalid_queue_maxsize_raises(self) -> None:
        with pytest.raises(ValueError, match="queue_maxsize must be positive"):
            MemoryStreamBridge(queue_maxsize=0)


async def _last_event_id(bridge: MemoryStreamBridge, run_id: str, index: int) -> tuple[str, ...]:
    """Return the ids of buffered events for *run_id*."""
    stream = bridge._streams[run_id]
    return tuple(e.id for e in stream.events)
