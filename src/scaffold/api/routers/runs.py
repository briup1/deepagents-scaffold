"""Run execution API — 流式与阻塞端点。

兼容 LangGraph Platform API 规范。Run 由后台 worker 执行，并将事件发布到以 run_id 为键的 ``StreamBridge``。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from scaffold.api.deps import get_checkpointer, get_stream_bridge
from scaffold.core.agents import create_agent, get_agent
from scaffold.infra.config.app_config import get_app_config
from scaffold.runtime.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, StreamBridge
from scaffold.runtime.worker import run_worker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])


class MessageContent(BaseModel):
    role: str
    content: str


class RunCreateRequest(BaseModel):
    assistant_id: str = Field(default="default", description="Agent name to run")
    input: dict[str, Any] = Field(default_factory=dict, description="Input state, e.g. {'messages': [...]}")
    config: dict[str, Any] = Field(default_factory=dict, description="RunnableConfig overrides")
    stream_mode: str | list[str] = Field(default="values", description="LangGraph stream mode(s)")
    stream_subgraphs: bool = Field(default=False, description="Stream events from nested subgraphs")
    on_disconnect: Literal["cancel", "continue"] = Field(
        default="cancel",
        description="What to do if the client disconnects during a wait run",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Run metadata")


def _normalise_stream_modes(stream_mode: str | list[str]) -> list[str]:
    if isinstance(stream_mode, str):
        return [stream_mode]
    return list(stream_mode)


def _build_run_config(body: "RunCreateRequest", app_config: Any) -> tuple[str, str, dict[str, Any]]:
    """构建传给 LangGraph 的 RunnableConfig。

    注入 recursion_limit（来自 ``agent.max_iterations``）并保留用户覆盖项。

    Returns:
        ``(thread_id, run_id, config)`` 三元组。
    """
    thread_id = (body.config.get("configurable") or {}).get("thread_id") or str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id, "run_id": run_id},
        # LangGraph 原生迭代预算：达到该值会抛出 GraphRecursionError，作为兜底出口
        "recursion_limit": app_config.agent.max_iterations,
    }

    # 合并用户提供的 body.config（configurable 字段做浅合并，其余直接覆盖）
    for key, value in body.config.items():
        if key == "configurable" and isinstance(value, dict):
            config["configurable"] = {**config["configurable"], **value}
        else:
            config[key] = value

    return thread_id, run_id, config


@router.post("/stream")
async def stream_run(body: RunCreateRequest, request: Request) -> StreamingResponse:
    """创建 run 并通过 SSE 流式返回事件。"""
    checkpointer = get_checkpointer(request)
    bridge = get_stream_bridge(request)
    app_config = get_app_config()

    thread_id, run_id, config = _build_run_config(body, app_config)

    try:
        agent = get_agent(body.assistant_id)
    except KeyError:
        agent = create_agent(name=body.assistant_id, checkpointer=checkpointer)

    stream_modes = _normalise_stream_modes(body.stream_mode)
    asyncio.create_task(
        run_worker(
            bridge=bridge,
            agent=agent,
            run_id=run_id,
            thread_id=thread_id,
            input=body.input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
        ),
        name=f"scaffold-worker-{run_id}",
    )

    last_event_id = request.headers.get("last-event-id")
    return StreamingResponse(
        sse_consumer(bridge, run_id, request, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/threads/{thread_id}/runs/{run_id}",
        },
    )


@router.post("/wait", response_model=dict)
async def wait_run(body: RunCreateRequest, request: Request) -> dict:
    """创建 run，阻塞直到完成，并返回最终 checkpoint。"""
    checkpointer = get_checkpointer(request)
    bridge = get_stream_bridge(request)
    app_config = get_app_config()

    thread_id, run_id, config = _build_run_config(body, app_config)

    try:
        agent = get_agent(body.assistant_id)
    except KeyError:
        agent = create_agent(name=body.assistant_id, checkpointer=checkpointer)

    stream_modes = _normalise_stream_modes(body.stream_mode)
    worker_task = asyncio.create_task(
        run_worker(
            bridge=bridge,
            agent=agent,
            run_id=run_id,
            thread_id=thread_id,
            input=body.input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
        ),
        name=f"scaffold-worker-{run_id}",
    )

    try:
        await _wait_for_run_completion(bridge, run_id, request)
    except asyncio.CancelledError:
        if body.on_disconnect == "cancel" and not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
        raise
    finally:
        if worker_task.done() and not worker_task.cancelled():
            exc = worker_task.exception()
            if exc is not None:
                logger.exception("Run worker raised an exception: run_id=%s", run_id)

    checkpoint = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
    if checkpoint is None:
        raise HTTPException(status_code=500, detail="Run completed but no checkpoint found")

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "checkpoint": _serialize_checkpoint(checkpoint),
        "metadata": body.metadata,
    }


async def sse_consumer(
    bridge: StreamBridge,
    run_id: str,
    request: Request,
    *,
    last_event_id: str | None = None,
    heartbeat_interval: float = 15.0,
) -> AsyncIterator[str]:
    """从 ``bridge`` 中消费指定 *run_id* 的事件并生成 SSE 帧。"""
    event_counter = 0
    async for item in bridge.subscribe(
        run_id,
        last_event_id=last_event_id,
        heartbeat_interval=heartbeat_interval,
    ):
        if await request.is_disconnected():
            logger.debug("Client disconnected from SSE stream: run_id=%s", run_id)
            break

        if item is HEARTBEAT_SENTINEL:
            yield format_sse("heartbeat", "", event_id=f"{run_id}:hb:{event_counter}")
            event_counter += 1
            continue

        if item is END_SENTINEL:
            yield format_sse("end", json.dumps({"run_id": run_id}), event_id=f"{run_id}:end")
            break

        event_name = item.event or "message"
        data = _serialize_event_data(item.data)
        event_id = item.id or f"{run_id}:{event_counter}"
        yield format_sse(event_name, data, event_id=event_id)
        event_counter += 1


async def _wait_for_run_completion(
    bridge: StreamBridge,
    run_id: str,
    request: Request,
    *,
    heartbeat_interval: float = 15.0,
) -> None:
    """阻塞直到 bridge 为该 run 发出 end sentinel。

    定期检测连接断开与心跳唤醒，即使 agent 长时间未产生事件，也能保持 handler 响应。
    """
    async for item in bridge.subscribe(run_id, heartbeat_interval=heartbeat_interval):
        if item is END_SENTINEL:
            return
        if await request.is_disconnected():
            raise asyncio.CancelledError("Client disconnected while waiting for run completion")


def format_sse(event: str, data: str, event_id: str | None = None) -> str:
    """格式化单条 SSE 帧，字段顺序与 LangGraph Platform 保持一致。

    字段顺序：``event``、``data``、``id``（每项以 ``\n`` 结尾），最后跟一个空行。
    """
    lines: list[str] = [f"event: {event}", f"data: {data}"]
    if event_id is not None:
        lines.append(f"id: {event_id}")
    return "\n".join(lines) + "\n\n"


def _serialize_event_data(data: Any) -> str:
    """尽力将 event payload 序列化为 JSON 字符串。"""
    try:
        return json.dumps(_serialize_event(data), ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        logger.warning("Failed to serialise event data: %s", exc)
        return json.dumps({"error": "unserialisable payload", "detail": str(exc)})


def _serialize_event(event: Any) -> Any:
    """尽力将 LangGraph event 序列化为可 JSON 化的对象。"""
    if isinstance(event, dict):
        return {k: _serialize_event(v) for k, v in event.items()}
    if isinstance(event, list):
        return [_serialize_event(item) for item in event]
    if hasattr(event, "model_dump"):
        try:
            return event.model_dump()
        except Exception:
            pass
    if hasattr(event, "to_json"):
        try:
            return event.to_json()
        except Exception:
            pass
    return event


def _serialize_checkpoint(checkpoint: Any) -> dict[str, Any]:
    """尽力将 LangGraph checkpoint tuple 序列化为字典。"""
    if checkpoint is None:
        return {}
    if hasattr(checkpoint, "checkpoint"):
        return {
            "checkpoint": _serialize_event(checkpoint.checkpoint),
            "metadata": getattr(checkpoint, "metadata", None),
            "parent_config": getattr(checkpoint, "parent_config", None),
        }
    if hasattr(checkpoint, "_asdict"):
        return _serialize_event(checkpoint._asdict())
    if isinstance(checkpoint, dict):
        return _serialize_event(checkpoint)
    return {"value": str(checkpoint)}
