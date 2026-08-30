"""历史消息仓库：基于 aiosqlite。"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from scaffold.infra.history.models import (
    ExtractionTask,
    ExtractionTemplate,
    ThreadMessage,
    ThreadSummary,
)
from scaffold.infra.time import _now


class HistoryRepository:
    """管理 threads 与 messages 的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建历史消息表结构。"""
        await _assert_user_id_schema(self._conn, "threads")
        await _assert_user_id_schema(self._conn, "extraction_tasks")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS threads (
                thread_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_threads_user_id ON threads(user_id);
            """
        )
        await self._conn.execute("PRAGMA user_version = 2")
        await self._conn.commit()

    async def ensure_thread(self, thread_id: str, agent_id: str, user_id: str) -> None:
        """确保线程记录存在；不存在则创建。已存在时不变更属主。"""
        now = _now()
        await self._conn.execute(
            """
            INSERT INTO threads (thread_id, agent_id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (thread_id, agent_id, user_id, None, now, now),
        )
        await self._conn.commit()

    async def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        """按用户查询线程基础信息（非本人 → None，design.md 3.4 契约）。"""
        return await self._get_thread_row(thread_id, user_id=user_id)

    async def get_thread_owner(self, thread_id: str) -> dict[str, Any] | None:
        """查询线程原始行（含 user_id）。授权层专用：路由需区分 403（非属主）与 404（不存在）。"""
        return await self._get_thread_row(thread_id, user_id=None)

    async def _get_thread_row(
        self, thread_id: str, *, user_id: str | None
    ) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            "SELECT thread_id, agent_id, user_id, title, created_at, updated_at FROM threads WHERE thread_id = ?"
            + (" AND user_id = ?" if user_id is not None else ""),
            (thread_id,) if user_id is None else (thread_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "thread_id": row[0],
            "agent_id": row[1],
            "user_id": row[2],
            "title": row[3],
            "created_at": row[4],
            "updated_at": row[5],
        }

    async def list_threads(
        self,
        user_id: str,
        agent_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ThreadSummary], int]:
        """返回某用户的线程列表和总数。"""
        where_clause = "WHERE t.user_id = ?"
        params: list[Any] = [user_id]
        if agent_id:
            where_clause += " AND t.agent_id = ?"
            params.append(agent_id)

        cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM threads t {where_clause}", tuple(params)
        )
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

    async def get_messages(self, thread_id: str, user_id: str) -> list[ThreadMessage]:
        """返回某用户在某线程的全部消息（非本人线程 → 空列表，design.md 3.4 契约）。"""
        cursor = await self._conn.execute(
            """
            SELECT
                m.thread_id, m.message_id, m.run_id, m.role, m.content, m.name, m.tool_call_id, m.tool_calls, m.created_at
            FROM messages m
            JOIN threads t ON t.thread_id = m.thread_id
            WHERE m.thread_id = ? AND t.user_id = ?
            ORDER BY m.created_at ASC, m.rowid ASC
            """,
            (thread_id, user_id),
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
        """写入单条消息；幂等（按 message_id 去重或更新）。

        使用 upsert 而不是 INSERT OR IGNORE，以便后续消息快照可以补充
        assistant 消息的 ``tool_calls`` 和缺失的 tool 结果消息。
        """
        await self._conn.execute(
            """
            INSERT INTO messages
            (message_id, thread_id, run_id, role, content, name, tool_call_id, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                run_id = COALESCE(excluded.run_id, run_id),
                role = excluded.role,
                content = COALESCE(excluded.content, content),
                name = COALESCE(excluded.name, name),
                tool_call_id = COALESCE(excluded.tool_call_id, tool_call_id),
                tool_calls = COALESCE(excluded.tool_calls, tool_calls),
                created_at = COALESCE(messages.created_at, excluded.created_at)
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
            (_now(), message.thread_id),
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
            (title, _now(), thread_id),
        )
        await self._conn.commit()

    async def delete_thread(self, thread_id: str, user_id: str) -> bool:
        """删除单个会话及其消息、抽取任务；仅属主可删，返回是否删除。"""
        cursor = await self._conn.execute(
            "SELECT 1 FROM threads WHERE thread_id = ? AND user_id = ?", (thread_id, user_id)
        )
        if await cursor.fetchone() is None:
            return False
        await self._delete_thread_rows(thread_id)
        await self._conn.commit()
        return True

    async def delete_threads_by_agent(self, agent_id: str, user_id: str) -> list[str]:
        """删除某用户在某 Agent 下的全部会话；返回被删除的 thread_id 列表。"""
        cursor = await self._conn.execute(
            "SELECT thread_id FROM threads WHERE agent_id = ? AND user_id = ?", (agent_id, user_id)
        )
        thread_ids = [row[0] for row in await cursor.fetchall()]
        for thread_id in thread_ids:
            await self._delete_thread_rows(thread_id)
        await self._conn.commit()
        return thread_ids

    async def _delete_thread_rows(self, thread_id: str) -> None:
        """删除单会话关联的所有行（不提交事务）。"""
        await self._conn.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        await self._conn.execute("DELETE FROM extraction_tasks WHERE thread_id = ?", (thread_id,))
        await self._conn.execute("DELETE FROM threads WHERE thread_id = ?", (thread_id,))


async def _assert_user_id_schema(conn: aiosqlite.Connection, table: str) -> None:
    """若表已存在但缺 user_id 列（旧版存量库），拒绝启动并指引删除 data/。"""
    cursor = await conn.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in await cursor.fetchall()]
    if cols and "user_id" not in cols:
        raise RuntimeError(
            f"表 {table} 为旧版 schema（缺 user_id 列）。存量数据不迁移，请删除 data/ 目录后重启服务。"
        )


def _parse_json(value: str | None) -> list[dict[str, Any]] | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _dump_json(value: list[dict[str, Any]] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


class ExtractionTaskRepository:
    """管理抽取任务的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建抽取任务表（通常由 HistoryRepository.migrate 统一调用）。"""
        await _assert_user_id_schema(self._conn, "extraction_tasks")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS extraction_tasks (
                task_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                upload_artifact_id TEXT NOT NULL,
                status TEXT NOT NULL,
                requirements TEXT,
                script_artifact_id TEXT,
                extracted_artifact_id TEXT,
                validation_report TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
                FOREIGN KEY (upload_artifact_id) REFERENCES artifacts(artifact_id),
                FOREIGN KEY (script_artifact_id) REFERENCES artifacts(artifact_id),
                FOREIGN KEY (extracted_artifact_id) REFERENCES artifacts(artifact_id)
            );

            CREATE INDEX IF NOT EXISTS idx_extraction_tasks_thread_id ON extraction_tasks(thread_id);
            CREATE INDEX IF NOT EXISTS idx_extraction_tasks_user_id ON extraction_tasks(user_id);
            """
        )
        await self._conn.commit()

    async def create(self, task: ExtractionTask) -> None:
        """创建抽取任务记录。"""
        await self._conn.execute(
            """
            INSERT INTO extraction_tasks
            (task_id, thread_id, user_id, upload_artifact_id, status, requirements,
             script_artifact_id, extracted_artifact_id, validation_report, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.thread_id,
                task.user_id,
                task.upload_artifact_id,
                task.status,
                _dump_json(task.requirements),
                task.script_artifact_id,
                task.extracted_artifact_id,
                _dump_json(task.validation_report),
                task.created_at,
                task.updated_at,
            ),
        )
        await self._conn.commit()

    async def get(self, task_id: str, user_id: str) -> ExtractionTask | None:
        """按用户查询抽取任务（非本人 → None，design.md 3.4 契约）。"""
        cursor = await self._conn.execute(
            """
            SELECT
                task_id, thread_id, user_id, upload_artifact_id, status, requirements,
                script_artifact_id, extracted_artifact_id, validation_report, created_at, updated_at
            FROM extraction_tasks
            WHERE task_id = ? AND user_id = ?
            """,
            (task_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    async def get_any(self, task_id: str) -> ExtractionTask | None:
        """按 task_id 查询任务原始记录。授权层（workspace）专用：存在性探测 + 归属比对 + 拒绝日志。"""
        cursor = await self._conn.execute(
            """
            SELECT
                task_id, thread_id, user_id, upload_artifact_id, status, requirements,
                script_artifact_id, extracted_artifact_id, validation_report, created_at, updated_at
            FROM extraction_tasks
            WHERE task_id = ?
            """,
            (task_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    async def update(self, task: ExtractionTask, user_id: str) -> bool:
        """更新抽取任务记录（仅属主，非本人 → False）；返回是否更新成功。"""
        cursor = await self._conn.execute(
            """
            UPDATE extraction_tasks
            SET status = ?,
                requirements = ?,
                script_artifact_id = ?,
                extracted_artifact_id = ?,
                validation_report = ?,
                updated_at = ?
            WHERE task_id = ? AND user_id = ?
            """,
            (
                task.status,
                _dump_json(task.requirements),
                task.script_artifact_id,
                task.extracted_artifact_id,
                _dump_json(task.validation_report),
                task.updated_at,
                task.task_id,
                user_id,
            ),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_by_thread(self, thread_id: str, user_id: str) -> list[ExtractionTask]:
        """列出某用户在某会话的全部抽取任务。"""
        cursor = await self._conn.execute(
            """
            SELECT
                task_id, thread_id, user_id, upload_artifact_id, status, requirements,
                script_artifact_id, extracted_artifact_id, validation_report, created_at, updated_at
            FROM extraction_tasks
            WHERE thread_id = ? AND user_id = ?
            ORDER BY created_at DESC
            """,
            (thread_id, user_id),
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: Any) -> ExtractionTask:
        requirements_json = row[5] or "{}"
        validation_json = row[8] or "{}"
        return ExtractionTask(
            task_id=row[0],
            thread_id=row[1],
            user_id=row[2],
            upload_artifact_id=row[3],
            status=row[4],
            requirements=_parse_json(requirements_json),
            script_artifact_id=row[6],
            extracted_artifact_id=row[7],
            validation_report=_parse_json(validation_json),
            created_at=row[9],
            updated_at=row[10],
        )


class ExtractionTemplateRepository:
    """管理抽取模板的异步仓库（强制 user_id 过滤）。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建抽取模板表。"""
        await _assert_user_id_schema(self._conn, "extraction_templates")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS extraction_templates (
                template_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                goal TEXT NOT NULL,
                script TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                source_file_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_templates_user ON extraction_templates(user_id);
            CREATE INDEX IF NOT EXISTS idx_templates_signature
                ON extraction_templates(user_id, json_extract(fingerprint, '$.signature'));
            """
        )
        await self._conn.commit()

    async def create(self, template: ExtractionTemplate) -> None:
        """创建模板记录。"""
        await self._conn.execute(
            """
            INSERT INTO extraction_templates
            (template_id, user_id, name, goal, script, fingerprint, source_file_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                template.template_id,
                template.user_id,
                template.name,
                _dump_json(template.goal),
                template.script,
                _dump_json(template.fingerprint),
                template.source_file_name,
                template.created_at,
                template.updated_at,
            ),
        )
        await self._conn.commit()

    async def get(self, template_id: str, user_id: str) -> ExtractionTemplate | None:
        """按 id + 用户查询模板。"""
        cursor = await self._conn.execute(
            """
            SELECT template_id, user_id, name, goal, script, fingerprint, source_file_name, created_at, updated_at
            FROM extraction_templates
            WHERE template_id = ? AND user_id = ?
            """,
            (template_id, user_id),
        )
        row = await cursor.fetchone()
        return self._row_to_template(row) if row else None

    async def find_by_signature(self, signature: str, user_id: str) -> ExtractionTemplate | None:
        """按结构指纹 signature 查候选模板（取最近更新的一条）。"""
        cursor = await self._conn.execute(
            """
            SELECT template_id, user_id, name, goal, script, fingerprint, source_file_name, created_at, updated_at
            FROM extraction_templates
            WHERE user_id = ? AND json_extract(fingerprint, '$.signature') = ?
            ORDER BY updated_at DESC, created_at DESC, rowid DESC
            LIMIT 1
            """,
            (user_id, signature),
        )
        row = await cursor.fetchone()
        return self._row_to_template(row) if row else None

    async def list_by_user(self, user_id: str) -> list[ExtractionTemplate]:
        """列出某用户的全部模板。"""
        cursor = await self._conn.execute(
            """
            SELECT template_id, user_id, name, goal, script, fingerprint, source_file_name, created_at, updated_at
            FROM extraction_templates
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_template(row) for row in rows]

    async def rename(self, template_id: str, user_id: str, name: str, updated_at: str) -> bool:
        """重命名模板（仅属主）；返回是否更新成功。"""
        cursor = await self._conn.execute(
            "UPDATE extraction_templates SET name = ?, updated_at = ? WHERE template_id = ? AND user_id = ?",
            (name, updated_at, template_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def delete(self, template_id: str, user_id: str) -> bool:
        """删除模板（仅属主）；返回是否删除成功。"""
        cursor = await self._conn.execute(
            "DELETE FROM extraction_templates WHERE template_id = ? AND user_id = ?",
            (template_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_template(self, row: Any) -> ExtractionTemplate:
        return ExtractionTemplate(
            template_id=row[0],
            user_id=row[1],
            name=row[2],
            goal=_parse_json(row[3]),
            script=row[4],
            fingerprint=_parse_json(row[5]),
            source_file_name=row[6],
            created_at=row[7],
            updated_at=row[8],
        )
