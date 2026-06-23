"""In-memory stream bridge backed by a per-run bounded event log."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .base import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge, StreamEvent

logger = logging.getLogger(__name__)


@dataclass
class _RunStream:
    events: list[StreamEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    ended: bool = False
    start_offset: int = 0


class MemoryStreamBridge(StreamBridge):
    """Per-run in-memory event log implementation.

    Events are retained for a bounded window per run so late subscribers and
    reconnecting clients can replay buffered events from ``Last-Event-ID``.

    Improvements over the original DeerFlow implementation:
    - O(1) ``Last-Event-ID`` lookup via a per-run ``id_to_offset`` dict.
    """

    def __init__(self, *, queue_maxsize: int = 256) -> None:
        if queue_maxsize <= 0:
            raise ValueError("queue_maxsize must be positive")
        self._maxsize = queue_maxsize
        self._streams: dict[str, _RunStream] = {}
        self._counters: dict[str, int] = {}
        # run_id -> {event_id -> absolute_offset}
        self._id_to_offset: dict[str, dict[str, int]] = {}

    # -- helpers ---------------------------------------------------------------

    def _get_or_create_stream(self, run_id: str) -> _RunStream:
        if run_id not in self._streams:
            self._streams[run_id] = _RunStream()
            self._counters[run_id] = 0
            self._id_to_offset[run_id] = {}
        return self._streams[run_id]

    def _next_id(self, run_id: str) -> str:
        self._counters[run_id] = self._counters.get(run_id, 0) + 1
        ts = int(time.time() * 1000)
        seq = self._counters[run_id] - 1
        return f"{ts}-{seq}"

    def _resolve_start_offset(self, stream: _RunStream, run_id: str, last_event_id: str | None) -> int:
        if last_event_id is None:
            return stream.start_offset

        mapped = self._id_to_offset.get(run_id, {}).get(last_event_id)
        if mapped is not None:
            return mapped + 1

        if stream.events:
            logger.warning(
                "last_event_id=%s not found in retained buffer for run %s; replaying from earliest retained event",
                last_event_id,
                run_id,
            )
        return stream.start_offset

    def _prune_id_mappings(self, run_id: str, min_offset: int) -> None:
        mapping = self._id_to_offset.get(run_id, {})
        stale = [eid for eid, off in mapping.items() if off < min_offset]
        for eid in stale:
            del mapping[eid]

    # -- StreamBridge API ------------------------------------------------------

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        stream = self._get_or_create_stream(run_id)
        entry = StreamEvent(id=self._next_id(run_id), event=event, data=data)
        async with stream.condition:
            offset = stream.start_offset + len(stream.events)
            self._id_to_offset.setdefault(run_id, {})[entry.id] = offset
            stream.events.append(entry)
            if len(stream.events) > self._maxsize:
                overflow = len(stream.events) - self._maxsize
                del stream.events[:overflow]
                stream.start_offset += overflow
                self._prune_id_mappings(run_id, stream.start_offset)
            stream.condition.notify_all()

    async def publish_end(self, run_id: str) -> None:
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            stream.ended = True
            stream.condition.notify_all()

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        stream = self._get_or_create_stream(run_id)
        async with stream.condition:
            next_offset = self._resolve_start_offset(stream, run_id, last_event_id)

        while True:
            async with stream.condition:
                if next_offset < stream.start_offset:
                    logger.warning(
                        "subscriber for run %s fell behind retained buffer; resuming from offset %s",
                        run_id,
                        stream.start_offset,
                    )
                    next_offset = stream.start_offset

                local_index = next_offset - stream.start_offset
                if 0 <= local_index < len(stream.events):
                    entry = stream.events[local_index]
                    next_offset += 1
                elif stream.ended:
                    entry = END_SENTINEL
                else:
                    try:
                        await asyncio.wait_for(stream.condition.wait(), timeout=heartbeat_interval)
                    except TimeoutError:
                        entry = HEARTBEAT_SENTINEL
                    else:
                        continue

            if entry is END_SENTINEL:
                yield END_SENTINEL
                return
            yield entry

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        self._streams.pop(run_id, None)
        self._counters.pop(run_id, None)
        self._id_to_offset.pop(run_id, None)

    async def close(self) -> None:
        self._streams.clear()
        self._counters.clear()
        self._id_to_offset.clear()
