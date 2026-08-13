"""ag-ui 集成：将已注册的 DeepAgents graph 托管为 /agent SSE 端点。

本模块用自定义 endpoint 替换 ag-ui-langgraph 默认的
``add_langgraph_fastapi_endpoint``，核心改动：

1. 在后台 Task 中预先把 LangGraph 事件写入 ``asyncio.Queue``，让 graph 执行与
   客户端拉取解耦，避免消费端暂停导致 LangGraph 因 backpressure 而停在
   pending Send 上。
2. SSE handler 从队列消费事件，空闲时发送 heartbeat comment，保持 Vite 代理 /
   浏览器连接不超时。
3. 全流程结构化日志，方便复现时定位是 graph 卡住、网络断开还是客户端丢事件。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent

from scaffold.core.agents import get_agent, list_agents
from scaffold.infra.config.app_config import get_app_config

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

# 为诊断“回复看起来不完整”而保留的最近 CONTENT 事件数。
TAIL_CONTENT_EVENTS_TO_LOG = 3


class _StreamSentinel:
    """用于标识事件流结束的唯一哨兵对象。"""


_SENTINEL = _StreamSentinel()


def _get_event_type(event: Any) -> str | None:
    """安全地获取 AG-UI 事件类型。"""
    if isinstance(event, dict):
        return event.get("type")
    return getattr(event, "type", None)


def _get_event_field(event: Any, field: str) -> Any:
    """安全地获取 AG-UI 事件字段。"""
    if isinstance(event, dict):
        return event.get(field)
    return getattr(event, field, None)


def _extract_finish_reason(event: Any) -> str | None:
    """从 TEXT_MESSAGE_END 的 raw_event 中提取模型 finish_reason。"""
    raw_event = _get_event_field(event, "raw_event")
    if raw_event is None:
        return None

    # 支持 dict 与 pydantic model 两种形式
    if isinstance(raw_event, dict):
        data = raw_event.get("data", {})
        output = data.get("output", {})
        response_metadata = output.get("response_metadata", {})
    else:
        data = getattr(raw_event, "data", None) or {}
        output = getattr(data, "output", None) or {}
        response_metadata = getattr(output, "response_metadata", None) or {}

    if isinstance(response_metadata, dict):
        return response_metadata.get("finish_reason")
    return getattr(response_metadata, "finish_reason", None)


def _log_stream_event(
    event: Any,
    *,
    ctx: dict[str, Any],
    text_buffers: dict[str, list[str]],
    tail_content_buffer: list[dict[str, Any]],
) -> None:
    """记录关键 AG-UI 事件，用于后续定位“回复不完整”问题。

    不记录完整消息内容，只记录长度、ID、事件类型等元信息。
    """
    etype = _get_event_type(event)
    if etype is None:
        return

    if etype == "TEXT_MESSAGE_START":
        message_id = _get_event_field(event, "message_id")
        text_buffers[message_id] = []
        logger.debug(
            "ag-ui text message start | %s message_id=%s",
            _ctx_str(ctx),
            message_id,
            extra=_stream_extra({**ctx, "message_id": message_id}),
        )

    elif etype == "TEXT_MESSAGE_CONTENT":
        message_id = _get_event_field(event, "message_id")
        delta = _get_event_field(event, "delta") or ""
        text_buffers.setdefault(message_id, []).append(delta)
        tail_content_buffer.append({"message_id": message_id, "delta_len": len(delta)})
        if len(tail_content_buffer) > TAIL_CONTENT_EVENTS_TO_LOG:
            tail_content_buffer.pop(0)

    elif etype == "TEXT_MESSAGE_END":
        message_id = _get_event_field(event, "message_id")
        finish_reason = _extract_finish_reason(event)
        full_text = "".join(text_buffers.pop(message_id, []))
        logger.info(
            "ag-ui text message finished | %s message_id=%s finish_reason=%s content_len=%d tail_lens=%s",
            _ctx_str(ctx),
            message_id,
            finish_reason,
            len(full_text),
            [t["delta_len"] for t in tail_content_buffer],
            extra=_stream_extra(
                {
                    **ctx,
                    "message_id": message_id,
                    "finish_reason": finish_reason,
                    "content_len": len(full_text),
                    "tail_delta_lens": [t["delta_len"] for t in tail_content_buffer],
                }
            ),
        )
        tail_content_buffer.clear()

    elif etype == "RUN_FINISHED":
        logger.info(
            "ag-ui run finished | %s",
            _ctx_str(ctx),
            extra=_stream_extra(ctx),
        )

    elif etype == "RUN_ERROR":
        message = _get_event_field(event, "message")
        logger.error(
            "ag-ui run error | %s error=%s",
            _ctx_str(ctx),
            message,
            extra=_stream_extra({**ctx, "error": message}),
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


def _stream_extra(ctx: dict[str, Any]) -> dict[str, Any]:
    """把上下文包装成 ``JSONFormatter`` 需要的 ``record.extra`` 结构。"""
    return {"extra": ctx}


def _ctx_str(ctx: dict[str, Any]) -> str:
    """把上下文格式化为人类可读的键值对字符串，用于 text 格式日志。"""
    return " ".join(f"{k}={v}" for k, v in ctx.items())


async def _produce_events_to_queue(
    agent: LangGraphAgent,
    input_data: RunAgentInput,
    queue: asyncio.Queue[Any],
) -> None:
    """在后台 Task 中把 ``agent.run()`` 产生的事件写入队列。"""
    start = time.monotonic()
    event_count = 0
    sample_count = 0
    ctx = _stream_ctx(input_data, agent_name=agent.name)
    # 用于累计 TEXT_MESSAGE_CONTENT 内容，仅在 TEXT_MESSAGE_END 时记录长度
    text_buffers: dict[str, list[str]] = {}
    tail_content_buffer: list[dict[str, Any]] = []

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

            _log_stream_event(
                event,
                ctx=ctx,
                text_buffers=text_buffers,
                tail_content_buffer=tail_content_buffer,
            )

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
    except Exception:
        logger.exception(
            "ag-ui stream producer failed | %s",
            _ctx_str({**ctx, "events_produced": event_count}),
            extra=_stream_extra({**ctx, "events_produced": event_count}),
        )
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
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
) -> Any:
    """产生 SSE 事件流：后台执行 graph，前台带心跳消费。

    graph 在独立的 asyncio Task 中运行，事件被写入队列。本生成器从队列读取并编码
    为 SSE 数据行；若超过 ``heartbeat_interval`` 没有新事件，则发送一条 SSE comment
    （``:heartbeat``），防止连接被中间件超时关闭。
    """
    queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=EVENT_QUEUE_MAXSIZE)
    producer = asyncio.create_task(
        _produce_events_to_queue(agent, input_data, queue),
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


def _register_endpoint(app: FastAPI, base_agent: LangGraphAgent, path: str) -> None:
    """注册单个 agent 的 POST /agent 与 GET /agent/health 端点。"""

    @app.post(path, operation_id=f"run_agent_{base_agent.name}")
    async def langgraph_agent_endpoint(
        input_data: RunAgentInput,
        request: Request,
    ) -> StreamingResponse:
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

        return StreamingResponse(
            _eager_event_generator(request_agent, input_data, encoder, request),
            media_type=encoder.get_content_type(),
        )

    @app.get(f"{path}/health", operation_id=f"agent_health_{base_agent.name}")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": {"name": base_agent.name},
        }


def register_ag_ui_endpoints(app: FastAPI) -> None:
    """为每个已注册 agent 在 FastAPI app 上注册 ag-ui 端点。"""
    agents = list_agents()
    if not agents:
        logger.warning("No agents registered; skipping ag-ui endpoint registration")
        return

    for info in agents:
        name = info["name"]
        path = f"/agent/{name}" if len(agents) > 1 else "/agent"
        base_agent = _build_ag_ui_agent(name)
        _register_endpoint(app, base_agent, path)
        logger.info("AG-UI endpoint registered: %s -> agent=%s", path, name)
