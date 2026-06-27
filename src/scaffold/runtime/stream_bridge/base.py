"""Abstract stream bridge protocol.

StreamBridge 将 agent worker（生产者）与 SSE 端点（消费者）解耦，
与 LangGraph Platform 的 queue + stream 架构对齐。
每个 run 拥有独立的逻辑流，以 ``run_id`` 为键。
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """单个流事件。

    Attributes:
        id: 单调递增的事件 ID（用作 SSE ``id:`` 字段，
            支持 ``Last-Event-ID`` 重连）。
        event: SSE 事件名称，例如 ``"metadata"``、``"values"``、
            ``"messages"``、``"error"``、``"end"``。
        data: 可 JSON 序列化的 payload。
    """

    id: str
    event: str
    data: Any


HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)


class StreamBridge(abc.ABC):
    """流桥接器的抽象基类。

    单个桥接器实例可以复用多个 run 作用域的流。生产者和消费者
    始终通过 ``run_id`` 标识流。
    """

    @abc.abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """为 *run_id* 入队单个事件（生产者侧）。"""

    @abc.abstractmethod
    async def publish_end(self, run_id: str) -> None:
        """标记 *run_id* 不再产生新事件。"""

    @abc.abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        """为 *run_id* 产生事件的异步迭代器（消费者侧）。

        当 *heartbeat_interval* 秒内未收到事件时，产出 :data:`HEARTBEAT_SENTINEL`。
        当生产者调用 :meth:`publish_end` 后，产出 :data:`END_SENTINEL`。
        """

    @abc.abstractmethod
    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """释放与 *run_id* 关联的资源。

        若 *delay* > 0，实现应等待后再释放，
        给延迟订阅者留出排空剩余事件的机会。
        """

    async def close(self) -> None:
        """释放后端资源。默认实现为空操作。"""
