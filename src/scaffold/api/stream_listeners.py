"""AG-UI 流事件监听器：把日志、历史持久化、标题同步从传输模块中拆出。

每个监听器只关注一种副作用：
- AgUILogListener：记录关键事件元信息（用于排查回复不完整）
- HistoryPersistenceListener：把助手文本消息写入 history 表
- ThreadTitleListener：同步 TitleMiddleware 生成的会话标题

监听器彼此独立，一个抛异常不会影响其他监听器。
"""

from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from scaffold.infra.history import HistoryRepository, ThreadMessage
from scaffold.infra.middleware.deerflow_adapters.title import get_thread_title

logger = logging.getLogger(__name__)


TAIL_CONTENT_EVENTS_TO_LOG = 3


def _get_event_type(event: Any) -> str | None:
    """安全地获取 AG-UI 事件类型（兼容 enum 与字符串）。"""
    if isinstance(event, dict):
        t = event.get("type")
    else:
        t = getattr(event, "type", None)
    if t is None:
        return None
    if isinstance(t, str):
        return t
    # 处理 Python/TypeScript enum 成员，如 EventType.TEXT_MESSAGE_CONTENT
    return getattr(t, "value", None) or str(t)


def _get_event_field(event: Any, field: str) -> Any:
    """安全地获取 AG-UI 事件字段。"""
    if isinstance(event, dict):
        return event.get(field)
    return getattr(event, field, None)


def _stream_extra(ctx: dict[str, Any]) -> dict[str, Any]:
    """把上下文包装成 ``JSONFormatter`` 需要的 ``record.extra`` 结构。"""
    return {"extra": ctx}


def _ctx_str(ctx: dict[str, Any]) -> str:
    """把上下文格式化为人类可读的键值对字符串，用于 text 格式日志。"""
    return " ".join(f"{k}={v}" for k, v in ctx.items())


class StreamEventListener(ABC):
    """AG-UI 流事件监听器基类。"""

    @abstractmethod
    async def on_event(self, event: Any, ctx: dict[str, Any]) -> None:
        """处理单个 AG-UI 事件。"""

    async def on_stream_end(self, ctx: dict[str, Any]) -> None:
        """流正常结束或异常结束时调用；用于 flush。默认空实现。"""


class AgUILogListener(StreamEventListener):
    """记录关键 AG-UI 事件，用于后续定位"回复不完整"问题。

    不记录完整消息内容，只记录长度、ID、事件类型等元信息。
    """

    def __init__(self, *, tail_content_events: int = TAIL_CONTENT_EVENTS_TO_LOG) -> None:
        self._text_buffers: dict[str, list[str]] = {}
        self._tail_content_buffer: list[dict[str, Any]] = []
        self._tail_content_events = tail_content_events

    async def on_event(self, event: Any, ctx: dict[str, Any]) -> None:
        etype = _get_event_type(event)
        if etype is None:
            return

        if etype == "TEXT_MESSAGE_START":
            message_id = _get_event_field(event, "message_id")
            self._text_buffers[message_id] = []
            logger.debug(
                "ag-ui text message start | %s message_id=%s",
                _ctx_str(ctx),
                message_id,
                extra=_stream_extra({**ctx, "message_id": message_id}),
            )

        elif etype == "TEXT_MESSAGE_CONTENT":
            message_id = _get_event_field(event, "message_id")
            delta = _get_event_field(event, "delta") or ""
            self._text_buffers.setdefault(message_id, []).append(delta)
            self._tail_content_buffer.append({"message_id": message_id, "delta_len": len(delta)})
            if len(self._tail_content_buffer) > self._tail_content_events:
                self._tail_content_buffer.pop(0)

        elif etype == "TEXT_MESSAGE_END":
            message_id = _get_event_field(event, "message_id")
            finish_reason = self._extract_finish_reason(event)
            full_text = "".join(self._text_buffers.pop(message_id, []))
            logger.info(
                "ag-ui text message finished | %s message_id=%s finish_reason=%s content_len=%d tail_lens=%s",
                _ctx_str(ctx),
                message_id,
                finish_reason,
                len(full_text),
                [t["delta_len"] for t in self._tail_content_buffer],
                extra=_stream_extra(
                    {
                        **ctx,
                        "message_id": message_id,
                        "finish_reason": finish_reason,
                        "content_len": len(full_text),
                        "tail_delta_lens": [t["delta_len"] for t in self._tail_content_buffer],
                    }
                ),
            )
            self._tail_content_buffer.clear()

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

    @staticmethod
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


class HistoryPersistenceListener(StreamEventListener):
    """把助手文本消息持久化到历史表。"""

    def __init__(self, history_repo: HistoryRepository) -> None:
        self._history_repo = history_repo
        self._assistant_buffers: dict[str, list[str]] = {}

    async def on_event(self, event: Any, ctx: dict[str, Any]) -> None:
        etype = _get_event_type(event)
        if etype == "TEXT_MESSAGE_CONTENT":
            mid = _get_event_field(event, "message_id")
            delta = _get_event_field(event, "delta") or ""
            self._assistant_buffers.setdefault(mid, []).append(delta)

        elif etype == "TEXT_MESSAGE_END":
            mid = _get_event_field(event, "message_id")
            full_text = "".join(self._assistant_buffers.pop(mid, []))
            try:
                await self._history_repo.add_message(
                    ThreadMessage(
                        message_id=mid or self._new_message_id(),
                        run_id=ctx.get("run_id"),
                        role="assistant",
                        content=full_text,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        thread_id=ctx.get("thread_id", ""),
                    )
                )
            except Exception:
                logger.exception(
                    "Failed to persist assistant message | thread_id=%s message_id=%s",
                    ctx.get("thread_id"),
                    mid,
                )

    @staticmethod
    def _new_message_id() -> str:
        import uuid  # noqa: PLC0415

        return str(uuid.uuid4())


class MessagesSnapshotListener(StreamEventListener):
    """把 LangGraph checkpoint 的完整消息快照持久化到历史表。

    流式事件只覆盖了文本增量；tool 调用结果、assistant 的 ``tool_calls``
    等结构只在 ``MESSAGES_SNAPSHOT`` 中出现。通过监听快照，可以：

    - 补充 assistant 消息的 ``tool_calls`` 字段
    - 持久化 tool 结果消息（如 ``render_ui`` 返回的 generative_ui envelope）
    - 让前端切换回历史会话后仍能重新渲染 Generative UI
    """

    def __init__(self, history_repo: HistoryRepository) -> None:
        self._history_repo = history_repo

    async def on_event(self, event: Any, ctx: dict[str, Any]) -> None:
        if _get_event_type(event) != "MESSAGES_SNAPSHOT":
            return

        messages = _get_event_field(event, "messages") or []
        if not isinstance(messages, list):
            return

        thread_id = ctx.get("thread_id", "")
        run_id = ctx.get("run_id")
        created_at = datetime.now(timezone.utc).isoformat()
        to_persist: list[ThreadMessage] = []

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("user", "assistant", "tool", "system"):
                continue

            content = msg.get("content")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False) if content is not None else None

            tool_call_id = msg.get("tool_call_id")
            if tool_call_id is None and role == "tool":
                tool_call_id = msg.get("id")

            tool_calls = msg.get("tool_calls")
            if tool_calls is not None and not isinstance(tool_calls, list):
                tool_calls = None

            to_persist.append(
                ThreadMessage(
                    thread_id=thread_id,
                    message_id=msg.get("id") or str(uuid.uuid4()),
                    run_id=run_id,
                    role=role,
                    content=content,
                    name=msg.get("name"),
                    tool_call_id=tool_call_id,
                    tool_calls=tool_calls,
                    created_at=created_at,
                )
            )

        if not to_persist:
            return

        try:
            await self._history_repo.add_messages(to_persist)
        except Exception:
            logger.exception(
                "Failed to persist messages snapshot | thread_id=%s count=%d",
                thread_id,
                len(to_persist),
            )


class ThreadTitleListener(StreamEventListener):
    """同步 TitleMiddleware 生成的会话标题。"""

    def __init__(self, history_repo: HistoryRepository) -> None:
        self._history_repo = history_repo
        self._title_updated = False

    async def on_event(self, event: Any, ctx: dict[str, Any]) -> None:
        if self._title_updated or _get_event_type(event) != "RUN_FINISHED":
            return
        try:
            title = self._extract_thread_title(event) or get_thread_title(ctx.get("thread_id", ""))
            if title:
                await self._history_repo.update_title(ctx.get("thread_id", ""), title)
                self._title_updated = True
                logger.info(
                    "Updated thread title | thread_id=%s title=%s",
                    ctx.get("thread_id"),
                    title,
                )
        except Exception:
            logger.exception(
                "Failed to update thread title | thread_id=%s",
                ctx.get("thread_id"),
            )

    @staticmethod
    def _extract_thread_title(event: Any) -> str | None:
        """从 STATE_SNAPSHOT 或 RUN_FINISHED 事件中提取 TitleMiddleware 生成的标题。"""
        # STATE_SNAPSHOT 事件直接携带快照
        snapshot = _get_event_field(event, "snapshot")
        if snapshot is not None:
            if isinstance(snapshot, dict):
                title = snapshot.get("_thread_title")
            else:
                title = getattr(snapshot, "_thread_title", None)
            if isinstance(title, str) and title.strip():
                return title

        raw_event = _get_event_field(event, "raw_event")
        if raw_event is None:
            return None

        if isinstance(raw_event, dict):
            state = raw_event.get("state")
        else:
            state = getattr(raw_event, "state", None)

        if state is None:
            return None

        if isinstance(state, dict):
            title = state.get("_thread_title")
        else:
            title = getattr(state, "_thread_title", None)

        if isinstance(title, str) and title.strip():
            return title
        return None
