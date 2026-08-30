"""抽取工作区：统一封装抽取任务、工件与存储的生命周期。

本模块把原本散落在 `infra/history`、`infra/artifacts` 与 `plugins/tools/_extraction_common`
中的抽取相关操作集中到一个 deep module 后面。工具通过单一入口访问任务与工件，
无需关心 SQLite 连接、表迁移或文件系统的具体生命周期。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType
from typing import Any

import aiosqlite

from scaffold.infra.artifacts import Artifact, ArtifactRepository, ArtifactStorage
from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.history.models import ExtractionTask
from scaffold.infra.history.repository import ExtractionTaskRepository
from scaffold.infra.time import _now


class ExtractionWorkspace(AbstractAsyncContextManager["ExtractionWorkspace"]):
    """抽取工作区：一次抽取任务所需的完整上下文。

    用法示例：

        async with get_extraction_workspace() as ws:
            task = await ws.create_task(thread_id, upload_id, requirements)
            artifact = await ws.get_artifact(upload_id)
            content = await ws.read_artifact(upload_id)

    作为异步上下文管理器，进入时打开 SQLite 连接并完成迁移，退出时关闭连接；
    调用方无需关心连接生命周期。
    """

    def __init__(self, db_path: str | Path, artifacts_dir: Path) -> None:
        self._db_path = Path(db_path)
        self._artifacts_dir = Path(artifacts_dir)
        self._conn: aiosqlite.Connection | None = None
        self._artifact_repo: ArtifactRepository | None = None
        self._task_repo: ExtractionTaskRepository | None = None
        self._storage: ArtifactStorage | None = None

    async def __aenter__(self) -> ExtractionWorkspace:
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._artifact_repo = ArtifactRepository(self._conn)
        self._task_repo = ExtractionTaskRepository(self._conn)
        self._storage = ArtifactStorage(self._artifacts_dir)
        await self._artifact_repo.migrate()
        await self._task_repo.migrate()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._conn is not None:
            await self._conn.close()
        self._conn = None
        self._artifact_repo = None
        self._task_repo = None
        self._storage = None

    async def create_task(
        self,
        thread_id: str,
        upload_artifact_id: str,
        requirements: dict[str, Any] | None = None,
    ) -> ExtractionTask:
        """创建抽取任务，并返回包含新 task_id 的任务对象。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        task_id = _new_task_id()
        now = _now()
        task = ExtractionTask(
            task_id=task_id,
            thread_id=thread_id,
            upload_artifact_id=upload_artifact_id,
            status="goal_setting",
            requirements=requirements,
            created_at=now,
            updated_at=now,
        )
        await self._task_repo.create(task)
        return task

    async def get_task(self, task_id: str) -> ExtractionTask | None:
        """根据 task_id 查询抽取任务。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._task_repo.get(task_id)

    async def update_task(self, task: ExtractionTask) -> bool:
        """更新抽取任务；自动刷新 updated_at。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        task.updated_at = _now()
        return await self._task_repo.update(task)

    async def list_tasks(self, thread_id: str) -> list[ExtractionTask]:
        """列出某会话下的全部抽取任务。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._task_repo.list_by_thread(thread_id)

    async def save_artifact(
        self,
        thread_id: str,
        artifact_type: str,
        filename: str,
        content: bytes,
        *,
        original_name: str | None = None,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        """保存工件：先写入文件系统，再写入元数据表，返回 Artifact。"""
        if self._artifact_repo is None or self._storage is None:
            raise RuntimeError("Workspace 未进入上下文")
        artifact_id, stored_path = self._storage.write(
            thread_id=thread_id,
            artifact_type=artifact_type,
            filename=filename,
            content=content,
        )
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
        await self._artifact_repo.create(artifact)
        return artifact

    async def read_artifact(self, artifact_id: str) -> bytes:
        """读取工件原始内容。"""
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            raise FileNotFoundError(f"工件 {artifact_id} 不存在")
        if self._storage is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await asyncio.to_thread(self._storage.read, artifact.stored_path)

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        """查询工件元数据。"""
        if self._artifact_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._artifact_repo.get(artifact_id)

    async def list_artifacts(
        self,
        thread_id: str,
        artifact_type: str | None = None,
    ) -> list[Artifact]:
        """列出某会话下的工件；可指定类型过滤。"""
        if self._artifact_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._artifact_repo.list_by_thread(thread_id, artifact_type)


def _new_task_id() -> str:
    return f"ext-{uuid.uuid4().hex[:12]}"


def get_extraction_workspace(
    app_config: AppConfig | None = None,
) -> ExtractionWorkspace:
    """根据当前配置构造 ExtractionWorkspace（尚未进入上下文）。"""
    if app_config is None:
        app_config = get_app_config()
    db_path = app_config.database.history_db or f"{app_config.database.sqlite_dir or './data'}/history.db"
    artifacts_dir = Path(app_config.database.sqlite_dir or "./data") / "artifacts"
    return ExtractionWorkspace(db_path=db_path, artifacts_dir=artifacts_dir)
