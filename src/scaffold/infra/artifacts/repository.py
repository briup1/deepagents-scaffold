"""工件元数据仓库。"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from scaffold.infra.artifacts.models import Artifact


class ArtifactRepository:
    """管理工件元数据的异步仓库。"""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def migrate(self) -> None:
        """创建工件元数据表。"""
        await self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
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
            """
        )
        await self._conn.commit()

    async def create(self, artifact: Artifact) -> None:
        """创建工件记录。"""
        await self._conn.execute(
            """
            INSERT INTO artifacts
            (artifact_id, thread_id, artifact_type, original_name, stored_path, mime_type, size_bytes, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.thread_id,
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

    async def get(self, artifact_id: str) -> Artifact | None:
        """根据 artifact_id 查询工件。"""
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
        artifact_type: str | None = None,
    ) -> list[Artifact]:
        """列出某会话的所有工件。"""
        if artifact_type:
            cursor = await self._conn.execute(
                "SELECT * FROM artifacts WHERE thread_id = ? AND artifact_type = ? ORDER BY created_at DESC",
                (thread_id, artifact_type),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM artifacts WHERE thread_id = ? ORDER BY created_at DESC",
                (thread_id,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_artifact(row) for row in rows]

    async def delete(self, artifact_id: str) -> bool:
        """删除工件元数据。返回是否删除成功。"""
        cursor = await self._conn.execute(
            "DELETE FROM artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    def _row_to_artifact(self, row: Any) -> Artifact:
        metadata_json = row[8] or "{}"
        metadata = json.loads(metadata_json)
        return Artifact(
            artifact_id=row[0],
            thread_id=row[1],
            artifact_type=row[2],
            original_name=row[3],
            stored_path=row[4],
            mime_type=row[5],
            size_bytes=row[6] or 0,
            created_at=row[7],
            metadata=metadata,
        )
