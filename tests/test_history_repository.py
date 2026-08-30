"""HistoryRepository 单元测试。"""

from __future__ import annotations

import pytest
import aiosqlite

from scaffold.infra.history import HistoryRepository, ThreadMessage


@pytest.fixture
async def repo():
    conn = await aiosqlite.connect(":memory:")
    repository = HistoryRepository(conn)
    await repository.migrate()
    yield repository
    await conn.close()


@pytest.mark.asyncio
async def test_ensure_thread_creates_record(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    summaries, total = await repo.list_threads("default")
    assert total == 1
    assert summaries[0].thread_id == "thread-1"
    assert summaries[0].agent_id == "default"


@pytest.mark.asyncio
async def test_add_message_is_idempotent(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    msg = ThreadMessage(
        thread_id="thread-1",
        message_id="msg-1",
        run_id="run-1",
        role="user",
        content="hello",
        created_at="2026-08-18T10:00:00Z",
    )
    await repo.add_message(msg)
    await repo.add_message(msg)
    messages = await repo.get_messages("thread-1")
    assert len(messages) == 1
    assert messages[0].content == "hello"


@pytest.mark.asyncio
async def test_list_threads_filtered_by_agent(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    await repo.ensure_thread("thread-2", "code_reviewer", "default")
    summaries, total = await repo.list_threads("default", agent_id="default")
    assert total == 1
    assert summaries[0].thread_id == "thread-1"


@pytest.mark.asyncio
async def test_add_message_upserts_tool_calls(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    await repo.add_message(
        ThreadMessage(
            thread_id="thread-1",
            message_id="msg-1",
            run_id="run-1",
            role="assistant",
            content="hi",
            created_at="2026-08-18T10:00:00Z",
        )
    )
    await repo.add_message(
        ThreadMessage(
            thread_id="thread-1",
            message_id="msg-1",
            run_id="run-1",
            role="assistant",
            content="hi",
            tool_calls=[{"id": "tc-1", "function": {"name": "render_ui", "arguments": "{}"}}],
            created_at="2026-08-18T10:00:00Z",
        )
    )
    messages = await repo.get_messages("thread-1")
    assert len(messages) == 1
    assert messages[0].tool_calls is not None
    assert messages[0].tool_calls[0]["function"]["name"] == "render_ui"


@pytest.mark.asyncio
async def test_update_title(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    await repo.update_title("thread-1", "测试标题")
    summaries, _ = await repo.list_threads("default")
    assert summaries[0].title == "测试标题"


@pytest.mark.asyncio
async def test_get_messages_returns_thread_id(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    await repo.add_message(
        ThreadMessage(
            thread_id="thread-1",
            message_id="msg-1",
            run_id="run-1",
            role="assistant",
            content="hi",
            created_at="2026-08-18T10:00:00Z",
        )
    )
    messages = await repo.get_messages("thread-1")
    assert len(messages) == 1
    assert messages[0].thread_id == "thread-1"


@pytest.mark.asyncio
async def test_list_threads_last_message_preview(repo: HistoryRepository) -> None:
    await repo.ensure_thread("thread-1", "default", "default")
    long_content = "a" * 120
    await repo.add_message(
        ThreadMessage(
            thread_id="thread-1",
            message_id="msg-1",
            run_id="run-1",
            role="user",
            content=long_content,
            created_at="2026-08-18T10:00:00Z",
        )
    )
    summaries, _ = await repo.list_threads("default")
    assert summaries[0].last_message_preview == long_content[:80] + "..."
