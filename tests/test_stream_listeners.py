"""流事件监听器单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ag_ui.core import (
    RunFinishedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)

from scaffold.api.stream_listeners import (
    AgUILogListener,
    HistoryPersistenceListener,
    ThreadTitleListener,
    _get_event_type,
)
from scaffold.infra.history import ThreadMessage


class TestGetEventType:
    def test_enum_event(self) -> None:
        event = TextMessageStartEvent(messageId="m1")
        assert _get_event_type(event) == "TEXT_MESSAGE_START"

    def test_dict_event(self) -> None:
        assert _get_event_type({"type": "RUN_FINISHED"}) == "RUN_FINISHED"

    def test_none_event(self) -> None:
        assert _get_event_type({}) is None


class TestExtractThreadTitle:
    def test_from_state_snapshot(self) -> None:
        event = {"type": "STATE_SNAPSHOT", "snapshot": {"_thread_title": "Hello World"}}
        assert ThreadTitleListener._extract_thread_title(event) == "Hello World"

    def test_from_raw_event_state(self) -> None:
        event = {"type": "RUN_FINISHED", "raw_event": {"state": {"_thread_title": "My Title"}}}
        assert ThreadTitleListener._extract_thread_title(event) == "My Title"

    def test_missing_title(self) -> None:
        event = {"type": "RUN_FINISHED", "raw_event": {"state": {}}}
        assert ThreadTitleListener._extract_thread_title(event) is None


class TestAgUILogListener:
    @pytest.fixture
    def listener(self) -> AgUILogListener:
        return AgUILogListener()

    @pytest.mark.asyncio
    async def test_logs_text_message_lifecycle(
        self, listener: AgUILogListener, caplog: pytest.LogCaptureFixture
    ) -> None:
        ctx = {"thread_id": "t-1", "run_id": "r-1"}

        with caplog.at_level("DEBUG", logger="scaffold.api.stream_listeners"):
            await listener.on_event(TextMessageStartEvent(messageId="m1"), ctx)
            await listener.on_event(TextMessageContentEvent(messageId="m1", delta="hi "), ctx)
            await listener.on_event(TextMessageContentEvent(messageId="m1", delta="there"), ctx)
            await listener.on_event(TextMessageEndEvent(messageId="m1"), ctx)

        assert any("text message start" in record.message for record in caplog.records)
        assert any("text message finished" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_run_finished(self, listener: AgUILogListener, caplog: pytest.LogCaptureFixture) -> None:
        ctx = {"thread_id": "t-1", "run_id": "r-1"}
        with caplog.at_level("INFO", logger="scaffold.api.stream_listeners"):
            await listener.on_event(RunFinishedEvent(threadId="t-1", runId="r-1"), ctx)
        assert any("run finished" in record.message for record in caplog.records)


class TestHistoryPersistenceListener:
    @pytest.mark.asyncio
    async def test_persists_assistant_message(self) -> None:
        history_repo = MagicMock()
        history_repo.add_message = AsyncMock()
        listener = HistoryPersistenceListener(history_repo)
        ctx = {"thread_id": "t-1", "run_id": "r-1"}

        await listener.on_event(TextMessageStartEvent(messageId="m1"), ctx)
        await listener.on_event(TextMessageContentEvent(messageId="m1", delta="hello "), ctx)
        await listener.on_event(TextMessageContentEvent(messageId="m1", delta="world"), ctx)
        await listener.on_event(TextMessageEndEvent(messageId="m1"), ctx)

        history_repo.add_message.assert_awaited_once()
        msg = history_repo.add_message.await_args.args[0]
        assert isinstance(msg, ThreadMessage)
        assert msg.role == "assistant"
        assert msg.content == "hello world"

    @pytest.mark.asyncio
    async def test_swallow_history_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        history_repo = MagicMock()
        history_repo.add_message = AsyncMock(side_effect=RuntimeError("db down"))
        listener = HistoryPersistenceListener(history_repo)
        ctx = {"thread_id": "t-1", "run_id": "r-1"}

        await listener.on_event(TextMessageContentEvent(messageId="m1", delta="x"), ctx)
        await listener.on_event(TextMessageEndEvent(messageId="m1"), ctx)

        assert any("Failed to persist assistant message" in record.message for record in caplog.records)


class TestThreadTitleListener:
    @pytest.mark.asyncio
    async def test_updates_title_from_event(self) -> None:
        history_repo = MagicMock()
        history_repo.update_title = AsyncMock()
        listener = ThreadTitleListener(history_repo)
        ctx = {"thread_id": "t-1", "run_id": "r-1"}

        event = {"type": "RUN_FINISHED", "raw_event": {"state": {"_thread_title": "My Title"}}}
        await listener.on_event(event, ctx)

        history_repo.update_title.assert_awaited_once_with("t-1", "My Title")

    @pytest.mark.asyncio
    async def test_ignores_second_run_finished(self) -> None:
        history_repo = MagicMock()
        history_repo.update_title = AsyncMock()
        listener = ThreadTitleListener(history_repo)
        ctx = {"thread_id": "t-1", "run_id": "r-1"}

        event = {"type": "RUN_FINISHED", "raw_event": {"state": {"_thread_title": "My Title"}}}
        await listener.on_event(event, ctx)
        await listener.on_event(event, ctx)

        assert history_repo.update_title.await_count == 1
