"""ag-ui 集成：将已注册的 DeepAgents graph 托管为 /agent SSE 端点。

本模块用自定义 endpoint 替换 ag-ui-langgraph 默认的
``add_langgraph_fastapi_endpoint``，核心改动：

1. 在后台 Task 中预先把 LangGraph 事件写入 ``asyncio.Queue``，让 graph 执行与
   客户端拉取解耦，避免消费端暂停导致 LangGraph 因 backpressure 而停在
   pending Send 上。
2. SSE handler 从队列消费事件，空闲时发送 heartbeat comment，保持 Vite 代理 /
   浏览器连接不超时。
3. 事件副作用（日志、历史持久化、标题同步）通过 ``StreamEventListener`` 订阅者
   处理，传输模块本身只负责队列、心跳和 SSE 编码。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ag_ui.core import RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent

from scaffold.api.deps import get_history_repo
from scaffold.api.stream_listeners import (
    AgUILogListener,
    HistoryPersistenceListener,
    MessagesSnapshotListener,
    StreamEventListener,
    ThreadTitleListener,
    _ctx_str,
    _stream_extra,
)
from scaffold.infra.config.app_config import get_app_config
from scaffold.infra.context import request_id_ctx, trace_id_ctx, user_id_ctx
from scaffold.infra.history import HistoryRepository, ThreadMessage
from scaffold.runtime.agents import get_agent, list_agents

logger = logging.getLogger(__name__)

# 心跳间隔（秒）。SSE 连接在长时间无数据时可能被 Vite 代理 / 浏览器 / 中间件关闭，
# 定时发送 comment 可维持连接。
HEARTBEAT_INTERVAL_SECONDS = 15.0

# asyncio.Queue maxsize=0 表示无界队列。graph 事件生命周期很短，graph 完成后即可被
# 客户端逐步消费；无界队列确保 graph 不会因客户端拉取慢而暂停。
EVENT_QUEUE_MAXSIZE = 0

# 队列积压采样间隔：每产出/消费多少条事件检查一次队列深度。
QUEUE_BACKPRESSURE_SAMPLE_INTERVAL = 100

# 队列深度告警阈值。超过该值说明客户端消费明显落后，需要关注。
QUEUE_BACKPRESSURE_WARNING_THRESHOLD = 500


class _StreamSentinel:
    """用于标识事件流结束的唯一哨兵对象。"""


_SENTINEL = _StreamSentinel()


def _ag_ui_message_to_thread_message(msg: Any, thread_id: str, run_id: str | None) -> ThreadMessage | None:
    """将 ag_ui Message 转换为 ThreadMessage。"""
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    if role is None:
        return None

    content = msg.get("content")
    if not isinstance(content, str):
        content = None

    tool_calls = msg.get("tool_calls")
    if tool_calls is not None and not isinstance(tool_calls, list):
        tool_calls = None

    return ThreadMessage(
        message_id=msg.get("id") or str(uuid.uuid4()),
        run_id=run_id,
        role=role,
        content=content,
        name=msg.get("name"),
        tool_call_id=msg.get("tool_call_id"),
        tool_calls=tool_calls,
        created_at=datetime.now(timezone.utc).isoformat(),
        thread_id=thread_id,
    )


def _stream_ctx(input_data: RunAgentInput, **kwargs: Any) -> dict[str, Any]:
    """构造 SSE 流日志的上下文字段，既写进日志消息也放入结构化 extra。

    注意：不记录消息内容，只记录 thread_id / run_id / agent 等标识。
    """
    return {
        "thread_id": input_data.thread_id,
        "run_id": input_data.run_id,
        "agent": getattr(input_data, "agent_id", None),
        **kwargs,
    }


def _build_listeners(history_repo: HistoryRepository | None) -> list[StreamEventListener]:
    """根据是否可用历史仓库构建事件监听器列表。"""
    listeners: list[StreamEventListener] = [AgUILogListener()]
    if history_repo is not None:
        listeners.extend(
            [
                HistoryPersistenceListener(history_repo),
                MessagesSnapshotListener(history_repo),
                ThreadTitleListener(history_repo),
            ]
        )
    return listeners


async def _notify_listeners(
    listeners: list[StreamEventListener],
    event: Any,
    ctx: dict[str, Any],
) -> None:
    """通知所有监听器；单个监听器异常不影响其他监听器。"""
    for listener in listeners:
        try:
            await listener.on_event(event, ctx)
        except Exception:
            logger.exception(
                "Stream listener failed | listener=%s event_type=%s",
                type(listener).__name__,
                getattr(event, "type", None),
            )


async def _produce_events_to_queue(
    agent: LangGraphAgent,
    input_data: RunAgentInput,
    queue: asyncio.Queue[Any],
    listeners: list[StreamEventListener],
) -> None:
    """在后台 Task 中把 ``agent.run()`` 产生的事件写入队列并通知监听器。"""
    start = time.monotonic()
    event_count = 0
    sample_count = 0
    ctx = _stream_ctx(input_data, agent_name=agent.name)

    logger.info(
        "ag-ui stream producer started | %s",
        _ctx_str(ctx),
        extra=_stream_extra(ctx),
    )

    try:
        async for event in agent.run(input_data):
            await queue.put(event)
            event_count += 1
            sample_count += 1

            await _notify_listeners(listeners, event, ctx)

            # 采样检查队列深度，避免每条事件都检查
            if sample_count >= QUEUE_BACKPRESSURE_SAMPLE_INTERVAL:
                sample_count = 0
                qsize = queue.qsize()
                if qsize > QUEUE_BACKPRESSURE_WARNING_THRESHOLD:
                    backpressure_ctx = {**ctx, "queue_size": qsize, "events_produced": event_count}
                    logger.warning(
                        "ag-ui event queue backpressure detected | %s",
                        _ctx_str(backpressure_ctx),
                        extra=_stream_extra(backpressure_ctx),
                    )
    except Exception as exc:
        logger.exception(
            "ag-ui stream producer failed | %s",
            _ctx_str({**ctx, "events_produced": event_count}),
            extra=_stream_extra({**ctx, "events_produced": event_count}),
        )
        # 关键：把后端异常显式转成 AG-UI RUN_ERROR 事件发给前端。
        # 否则前端只会看到 RUN_STARTED 后流突然结束，表现为“没有反应”。
        error_event = RunErrorEvent(
            message=str(exc),
            code=getattr(exc, "code", None) or type(exc).__name__,
        )
        await queue.put(error_event)
        event_count += 1
        await _notify_listeners(listeners, error_event, ctx)
    finally:
        await queue.put(_SENTINEL)
        elapsed_ms = (time.monotonic() - start) * 1000
        finish_ctx = {**ctx, "events_produced": event_count, "producer_duration_ms": round(elapsed_ms, 2)}
        logger.info(
            "ag-ui stream producer finished | %s",
            _ctx_str(finish_ctx),
            extra=_stream_extra(finish_ctx),
        )


async def _eager_event_generator(
    agent: LangGraphAgent,
    input_data: RunAgentInput,
    encoder: EventEncoder,
    request: Request,
    listeners: list[StreamEventListener],
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> Any:
    """产生 SSE 事件流：后台执行 graph，前台带心跳消费。

    graph 在独立的 asyncio Task 中运行，事件被写入队列。本生成器从队列读取并编码
    为 SSE 数据行；若超过 ``heartbeat_interval`` 没有新事件，则发送一条 SSE comment
    （``:heartbeat``），防止连接被中间件超时关闭。
    """
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=EVENT_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _produce_events_to_queue(agent, input_data, queue, listeners),
        name=f"ag-ui-producer-{input_data.run_id}",
    )

    start = time.monotonic()
    events_yielded = 0
    heartbeats = 0
    ctx = _stream_ctx(input_data, agent_name=agent.name)

    logger.info(
        "ag-ui stream consumer started | %s",
        _ctx_str(ctx),
        extra=_stream_extra(ctx),
    )

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    elapsed_ms = (time.monotonic() - start) * 1000
                    disconnect_ctx = {
                        **ctx,
                        "events_yielded": events_yielded,
                        "heartbeats": heartbeats,
                        "consumer_duration_ms": round(elapsed_ms, 2),
                    }
                    logger.info(
                        "ag-ui client disconnected, aborting stream | %s",
                        _ctx_str(disconnect_ctx),
                        extra=_stream_extra(disconnect_ctx),
                    )
                    break
                heartbeats += 1
                heartbeat_ctx = {**ctx, "events_yielded": events_yielded, "heartbeats": heartbeats}
                logger.debug(
                    "ag-ui heartbeat emitted | %s",
                    _ctx_str(heartbeat_ctx),
                    extra=_stream_extra(heartbeat_ctx),
                )
                yield ":heartbeat\n\n"
                continue

            if event is _SENTINEL:
                break

            yield encoder.encode(event)
            events_yielded += 1

        elapsed_ms = (time.monotonic() - start) * 1000
        finish_ctx = {
            **ctx,
            "events_yielded": events_yielded,
            "heartbeats": heartbeats,
            "consumer_duration_ms": round(elapsed_ms, 2),
        }
        logger.info(
            "ag-ui stream consumer finished normally | %s",
            _ctx_str(finish_ctx),
            extra=_stream_extra(finish_ctx),
        )
    finally:
        producer.cancel()
        try:
            await producer
        except asyncio.CancelledError:
            logger.debug(
                "ag-ui stream producer cancelled | %s",
                _ctx_str(ctx),
                extra=_stream_extra(ctx),
            )


def _build_ag_ui_agent(name: str) -> LangGraphAgent:
    """包装已编译的 DeepAgents graph 为 ag-ui LangGraphAgent。"""
    graph = get_agent(name)
    app_config = get_app_config()
    config = {"recursion_limit": app_config.agent.max_iterations}
    return LangGraphAgent(name=name, graph=graph, config=config)


def _register_endpoint(app: FastAPI, base_agent: LangGraphAgent, path: str, *, op_id_suffix: str = "") -> None:
    """注册单个 agent 的 POST /agent 与 GET /agent/health 端点。"""
    suffix = op_id_suffix or base_agent.name

    @app.post(path, operation_id=f"run_agent_{suffix}")
    async def langgraph_agent_endpoint(
        input_data: RunAgentInput,
        request: Request,
    ) -> StreamingResponse:
        # 把 HTTP request_id / user_id 透传到 Agent 执行上下文，供中间件可观测性与数据隔离使用
        req_id = getattr(request.state, "request_id", None)
        if req_id:
            request_id_ctx.set(req_id)
            trace_id_ctx.set(req_id)
        user_id_ctx.set(getattr(request.state, "user_id", "default"))

        # 每个请求克隆一个独立 agent，避免并发请求间 per-request 状态互相污染
        request_agent = base_agent.clone()
        accept_header = request.headers.get("accept")
        encoder = EventEncoder(accept=accept_header)

        endpoint_ctx = {
            "thread_id": input_data.thread_id,
            "run_id": input_data.run_id,
            "agent_name": base_agent.name,
            "path": path,
            "accept": accept_header,
        }
        logger.info(
            "ag-ui endpoint invoked | %s",
            _ctx_str(endpoint_ctx),
            extra=_stream_extra(endpoint_ctx),
        )

        # 持久化用户消息（含会话归属校验：防止用他人 thread_id 劫持会话）
        history_repo: HistoryRepository | None = None
        try:
            history_repo = get_history_repo(request)
            current_user = user_id_ctx.get()
            existing_thread = await history_repo.get_thread_owner(input_data.thread_id)
            if existing_thread is not None and existing_thread["user_id"] != current_user:
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Thread {input_data.thread_id} 属于其他用户"},
                )
            await history_repo.ensure_thread(input_data.thread_id, base_agent.name, current_user)
            persisted = 0
            for msg in input_data.messages or []:
                tm = _ag_ui_message_to_thread_message(
                    msg.model_dump() if hasattr(msg, "model_dump") else dict(msg),
                    input_data.thread_id,
                    input_data.run_id,
                )
                if tm:
                    await history_repo.add_message(tm)
                    persisted += 1
            logger.info(
                "Persisted user messages | thread_id=%s count=%d",
                input_data.thread_id,
                persisted,
            )
        except Exception:
            logger.exception(
                "Failed to persist user messages | thread_id=%s run_id=%s",
                input_data.thread_id,
                input_data.run_id,
            )

        listeners = _build_listeners(history_repo)

        return StreamingResponse(
            _eager_event_generator(request_agent, input_data, encoder, request, listeners),
            media_type=encoder.get_content_type(),
        )

    @app.get(f"{path}/health", operation_id=f"agent_health_{suffix}")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": {"name": base_agent.name},
        }


def register_ag_ui_endpoints(app: FastAPI) -> None:
    """为每个已注册 agent 在 FastAPI app 上注册 ag-ui 端点（/agent/{name}）。"""
    agents = list_agents()
    if not agents:
        logger.warning("No agents registered; skipping ag-ui endpoint registration")
        return

    for info in agents:
        name = info["name"]
        base_agent = _build_ag_ui_agent(name)
        _register_endpoint(app, base_agent, f"/agent/{name}")
        logger.info("AG-UI endpoint registered: /agent/%s -> agent=%s", name, name)
