"""用于执行 agent 运行并通过桥接器流式传输事件的背景 worker。

该 worker 以 asyncio Task 形式运行，将事件发布到每个运行对应的
``StreamBridge`` 流中，由 SSE 端点或阻塞等待端点消费。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Iterable

from langchain_core.messages import BaseMessage

from scaffold.runtime.stream_bridge import StreamBridge

logger = logging.getLogger(__name__)


async def run_worker(
    bridge: StreamBridge,
    agent: Any,
    run_id: str,
    thread_id: str,
    input: dict[str, Any],
    config: dict[str, Any],
    stream_modes: Iterable[str],
    stream_subgraphs: bool = False,
) -> None:
    """在后台执行 agent 运行并将事件发布到 ``bridge``。

    Args:
        bridge: 用于向消费者发布事件的流桥接器。
        agent: 已编译的 DeepAgents 图（CompiledStateGraph）。
        run_id: 唯一运行标识符。
        thread_id: 对话线程标识符。
        input: 传递给 agent 的输入状态（例如 ``{"messages": [...]}``）。
        config: RunnableConfig 覆盖项（必须已包含 ``thread_id``）。
        stream_modes: 请求的 LangGraph ``stream_mode`` 值（例如
            ``["values"]``、``["messages"]``、``["debug"]``）。
        stream_subgraphs: 是否从嵌套子图中流式传输事件。
    """
    stream_mode_arg: str | list[str]
    modes = list(stream_modes)
    stream_mode_arg = modes[0] if len(modes) == 1 else modes

    await bridge.publish(
        run_id,
        "metadata",
        {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "pending",
            "stream_mode": stream_mode_arg,
            "stream_subgraphs": stream_subgraphs,
        },
    )

    try:
        await bridge.publish(
            run_id,
            "metadata",
            {"run_id": run_id, "thread_id": thread_id, "status": "running"},
        )

        astream_kwargs: dict[str, Any] = {
            "input": input,
            "config": config,
            "stream_mode": stream_mode_arg,
        }
        if stream_subgraphs:
            astream_kwargs["subgraphs"] = True

        async for chunk in agent.astream(**astream_kwargs):
            if len(modes) == 1:
                event_name = modes[0]
                await bridge.publish(run_id, event_name, _serialize_chunk(chunk))
            else:
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    event_name, payload = chunk  # type: ignore[misc]
                else:
                    event_name, payload = modes[0], chunk
                await bridge.publish(run_id, str(event_name), _serialize_chunk(payload))

        await bridge.publish(
            run_id,
            "metadata",
            {"run_id": run_id, "thread_id": thread_id, "status": "success"},
        )
    except asyncio.CancelledError:
        await bridge.publish(
            run_id,
            "metadata",
            {"run_id": run_id, "thread_id": thread_id, "status": "cancelled"},
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Run worker failed: run_id=%s thread_id=%s", run_id, thread_id)
        await bridge.publish(
            run_id,
            "error",
            {
                "run_id": run_id,
                "thread_id": thread_id,
                "status": "error",
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )
    finally:
        try:
            await bridge.publish_end(run_id)
        except Exception:
            logger.exception("Failed to publish end sentinel for run_id=%s", run_id)
        asyncio.create_task(
            _safe_cleanup(bridge, run_id, delay=60.0),
            name=f"scaffold-cleanup-{run_id}",
        )


async def _safe_cleanup(bridge: StreamBridge, run_id: str, delay: float) -> None:
    """延迟一段时间后清理每个运行对应的流，并记录任何异常。"""
    try:
        await asyncio.sleep(delay)
        await bridge.cleanup(run_id, delay=0)
        logger.debug("Bridge cleaned up for run_id=%s after delay=%.0fs", run_id, delay)
    except Exception:
        logger.exception("Safe cleanup failed for run_id=%s", run_id)


def _serialize_chunk(chunk: Any) -> Any:
    """尽力将流式分块转换为可 JSON 序列化的表示。"""
    if chunk is None:
        return None
    if isinstance(chunk, BaseMessage):
        return {
            "type": chunk.type,
            "content": chunk.content,
            "additional_kwargs": getattr(chunk, "additional_kwargs", None),
            "id": getattr(chunk, "id", None),
        }
    if isinstance(chunk, dict):
        return {k: _serialize_chunk(v) for k, v in chunk.items()}
    if isinstance(chunk, list):
        return [_serialize_chunk(v) for v in chunk]
    if isinstance(chunk, tuple):
        return [_serialize_chunk(v) for v in chunk]
    if hasattr(chunk, "model_dump"):
        try:
            return chunk.model_dump()
        except Exception:
            pass
    if hasattr(chunk, "to_json"):
        try:
            return chunk.to_json()
        except Exception:
            pass
    if hasattr(chunk, "__dict__"):
        try:
            return {k: _serialize_chunk(v) for k, v in chunk.__dict__.items()}
        except Exception:
            pass
    try:
        json.dumps(chunk, default=str)
    except (TypeError, ValueError):
        return str(chunk)
    return chunk
