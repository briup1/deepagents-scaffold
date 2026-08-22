"""抽取工具公共辅助函数。"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from scaffold.infra.artifacts import Artifact, ArtifactRepository, ArtifactStorage
from scaffold.infra.config.app_config import get_app_config
from scaffold.infra.history.models import ExtractionTask
from scaffold.infra.history.repository import ExtractionTaskRepository


def _new_task_id() -> str:
    return f"ext-{uuid.uuid4().hex[:12]}"


def _new_artifact_id() -> str:
    return f"art-{uuid.uuid4().hex[:12]}"


def _get_storage() -> ArtifactStorage:
    """根据当前配置获取工件存储实例。"""
    config = get_app_config()
    base_dir = Path(config.database.sqlite_dir or "./data") / "artifacts"
    return ArtifactStorage(base_dir)


async def _get_db_conn() -> aiosqlite.Connection:
    """根据当前配置获取历史库连接。"""
    config = get_app_config()
    db_path = config.database.history_db or f"{config.database.sqlite_dir or './data'}/history.db"
    return await aiosqlite.connect(db_path)


async def _get_artifact_repo() -> tuple[ArtifactRepository, aiosqlite.Connection]:
    """返回 ArtifactRepository 及其底层连接（调用方负责关闭）。"""
    conn = await _get_db_conn()
    repo = ArtifactRepository(conn)
    await repo.migrate()
    return repo, conn


async def _get_task_repo() -> tuple[ExtractionTaskRepository, aiosqlite.Connection]:
    """返回 ExtractionTaskRepository 及其底层连接（调用方负责关闭）。"""
    conn = await _get_db_conn()
    repo = ExtractionTaskRepository(conn)
    await repo.migrate()
    return repo, conn


async def _get_artifact(artifact_id: str) -> Artifact | None:
    """根据 artifact_id 查询工件元数据。"""
    repo, conn = await _get_artifact_repo()
    try:
        return await repo.get(artifact_id)
    finally:
        await conn.close()


async def _get_task(task_id: str) -> ExtractionTask | None:
    """根据 task_id 查询抽取任务。"""
    repo, conn = await _get_task_repo()
    try:
        return await repo.get(task_id)
    finally:
        await conn.close()


async def _update_task(task: ExtractionTask) -> bool:
    """更新抽取任务。"""
    repo, conn = await _get_task_repo()
    try:
        return await repo.update(task)
    finally:
        await conn.close()


async def _save_artifact(
    thread_id: str,
    artifact_type: str,
    filename: str,
    content: bytes,
    original_name: str | None = None,
    mime_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """保存工件并返回 Artifact 对象。"""
    storage = _get_storage()
    artifact_id, stored_path = storage.write(thread_id, artifact_type, filename, content)
    artifact = Artifact(
        artifact_id=artifact_id,
        thread_id=thread_id,
        artifact_type=artifact_type,  # type: ignore[arg-type]
        original_name=original_name or filename,
        stored_path=stored_path,
        mime_type=mime_type,
        size_bytes=len(content),
        created_at=_now(),
        metadata=metadata or {},
    )
    repo, conn = await _get_artifact_repo()
    try:
        await repo.create(artifact)
    finally:
        await conn.close()
    return artifact


def _now() -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.now(timezone.utc).isoformat()


async def _read_artifact_bytes(artifact: Artifact) -> bytes:
    """读取工件文件内容。"""
    storage = _get_storage()
    return await asyncio.to_thread(storage.read, artifact.stored_path)
