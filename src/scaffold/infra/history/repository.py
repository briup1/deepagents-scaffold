"""历史消息仓库：基于 aiosqlite。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import aiosqlite

from scaffold.infra.history.models import ThreadMessage, ThreadSummary


class HistoryRepository:
    """管理 threads 与 messages 的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建历史消息表结构。"""
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                run_id TEXT,
                role TEXT NOT NULL,
                content TEXT,
                name TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);
            CREATE INDEX IF NOT EXISTS idx_threads_updated_at ON threads(updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_threads_agent_id ON threads(agent_id);
            """
        )
        await self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def ensure_thread(self, thread_id: str, agent_id: str) -> None:
        """确保线程记录存在；不存在则创建。"""
        now = self._now()
        await self._conn.execute(
            """
            INSERT INTO threads (thread_id, agent_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (thread_id, agent_id, None, now, now),
        )
        await self._conn.commit()

    async def list_threads(
        self,
        agent_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ThreadSummary], int]:
        """返回线程列表和总数。"""
        where_clause = "WHERE agent_id = ?" if agent_id else ""
        params: tuple[Any, ...] = (agent_id,) if agent_id else ()

        cursor = await self._conn.execute(f"SELECT COUNT(*) FROM threads {where_clause}", params)
        row = await cursor.fetchone()
        total = row[0] if row else 0

        cursor = await self._conn.execute(
            f"""
            SELECT
                t.thread_id,
                t.agent_id,
                t.title,
                t.created_at,
                t.updated_at,
                m.content AS last_content
            FROM threads t
            LEFT JOIN messages m ON m.message_id = (
                SELECT message_id FROM messages
                WHERE thread_id = t.thread_id
                ORDER BY created_at DESC LIMIT 1
            )
            {where_clause}
            ORDER BY t.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = await cursor.fetchall()

        summaries = [
            ThreadSummary(
                thread_id=row[0],
                agent_id=row[1],
                title=row[2],
                last_message_preview=(row[5][:80] + "...") if row[5] and len(row[5]) > 80 else row[5],
                created_at=row[3],
                updated_at=row[4],
            )
            for row in rows
        ]
        return summaries, total

    async def get_messages(self, thread_id: str) -> list[ThreadMessage]:
        """返回某线程全部消息，按时间正序。"""
        cursor = await self._conn.execute(
            """
            SELECT
                thread_id, message_id, run_id, role, content, name, tool_call_id, tool_calls, created_at
            FROM messages
            WHERE thread_id = ?
            ORDER BY created_at ASC, rowid ASC
            """,
            (thread_id,),
        )
        rows = await cursor.fetchall()
        return [
            ThreadMessage(
                thread_id=row[0],
                message_id=row[1],
                run_id=row[2],
                role=row[3],
                content=row[4],
                name=row[5],
                tool_call_id=row[6],
                tool_calls=_parse_json(row[7]),
                created_at=row[8],
            )
            for row in rows
        ]

    async def add_message(self, message: ThreadMessage) -> None:
        """写入单条消息；幂等（按 message_id 去重）。"""
        await self._conn.execute(
            """
            INSERT OR IGNORE INTO messages
            (message_id, thread_id, run_id, role, content, name, tool_call_id, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.message_id,
                message.thread_id,
                message.run_id,
                message.role,
                message.content,
                message.name,
                message.tool_call_id,
                _dump_json(message.tool_calls),
                message.created_at,
            ),
        )
        await self._conn.execute(
            "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
            (self._now(), message.thread_id),
        )
        await self._conn.commit()

    async def add_messages(self, messages: list[ThreadMessage]) -> None:
        """批量写入消息。"""
        for message in messages:
            await self.add_message(message)

    async def update_title(self, thread_id: str, title: str) -> None:
        """更新会话标题。"""
        await self._conn.execute(
            "UPDATE threads SET title = ?, updated_at = ? WHERE thread_id = ?",
            (title, self._now(), thread_id),
        )
        await self._conn.commit()


def _parse_json(value: str | None) -> list[dict[str, Any]] | None:
    import json

    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _dump_json(value: list[dict[str, Any]] | None) -> str | None:
    import json

    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)
