"""工件元数据仓库。"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from scaffold.infra.artifacts.models import Artifact
from scaffold.infra.history.repository import _assert_user_id_schema


class ArtifactRepository:
    """管理工件元数据的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建工件元数据表。"""
        await _assert_user_id_schema(self._conn, "artifacts")
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                original_name TEXT,
                stored_path TEXT NOT NULL,
                mime_type TEXT,
                size_bytes INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_artifacts_thread_id ON artifacts(thread_id);
            CREATE INDEX IF NOT EXISTS idx_artifacts_thread_type ON artifacts(thread_id, artifact_type);
            CREATE INDEX IF NOT EXISTS idx_artifacts_user_id ON artifacts(user_id);
            """
        )
        await self._conn.commit()

    async def create(self, artifact: Artifact) -> None:
        """创建工件记录。"""
        await self._conn.execute(
            """
            INSERT INTO artifacts
            (artifact_id, thread_id, user_id, artifact_type, original_name, stored_path, mime_type, size_bytes, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.thread_id,
                artifact.user_id,
                artifact.artifact_type,
                artifact.original_name,
                artifact.stored_path,
                artifact.mime_type,
                artifact.size_bytes,
                artifact.created_at,
                json.dumps(artifact.metadata, ensure_ascii=False),
            ),
        )
        await self._conn.commit()

    async def get(self, artifact_id: str, user_id: str) -> Artifact | None:
        """按用户查询工件（非本人 → None，design.md 3.4 契约）。"""
        cursor = await self._conn.execute(
            "SELECT * FROM artifacts WHERE artifact_id = ? AND user_id = ?",
            (artifact_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    async def get_any(self, artifact_id: str) -> Artifact | None:
        """按 artifact_id 查询工件原始记录。授权层（workspace）专用：存在性探测 + 归属比对 + 拒绝日志。"""
        cursor = await self._conn.execute(
            "SELECT * FROM artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_artifact(row)

    async def list_by_thread(
        self,
        thread_id: str,
        user_id: str,
        artifact_type: str | None = None,
    ) -> list[Artifact]:
        """列出某用户在某会话下的所有工件。"""
        if artifact_type:
            cursor = await self._conn.execute(
                "SELECT * FROM artifacts WHERE thread_id = ? AND user_id = ? AND artifact_type = ? ORDER BY created_at DESC",
                (thread_id, user_id, artifact_type),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM artifacts WHERE thread_id = ? AND user_id = ? ORDER BY created_at DESC",
                (thread_id, user_id),
            )
        rows = await cursor.fetchall()
        return [self._row_to_artifact(row) for row in rows]

    async def delete(self, artifact_id: str, user_id: str) -> bool:
        """删除工件元数据（仅属主）。返回是否删除成功。"""
        cursor = await self._conn.execute(
            "DELETE FROM artifacts WHERE artifact_id = ? AND user_id = ?",
            (artifact_id, user_id),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_artifact(self, row: Any) -> Artifact:
        metadata_json = row[9] or "{}"
        metadata = json.loads(metadata_json)
        return Artifact(
            artifact_id=row[0],
            thread_id=row[1],
            user_id=row[2],
            artifact_type=row[3],
            original_name=row[4],
            stored_path=row[5],
            mime_type=row[6],
            size_bytes=row[7] or 0,
            created_at=row[8],
            metadata=metadata,
        )
