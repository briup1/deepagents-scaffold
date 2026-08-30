"""抽取工作区：统一封装抽取任务、工件与存储的生命周期。

本模块把原本散落在 `infra/history`、`infra/artifacts` 与 `plugins/tools/_extraction_common`
中的抽取相关操作集中到一个 deep module 后面。工具通过单一入口访问任务与工件，
无需关心 SQLite 连接、表迁移或文件系统的具体生命周期。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType
from typing import Any

import aiosqlite

from scaffold.infra.artifacts import Artifact, ArtifactRepository, ArtifactStorage
from scaffold.infra.config.app_config import AppConfig, get_app_config
from scaffold.infra.context import get_current_user_id
from scaffold.infra.extraction.fingerprint import compute_fingerprint
from scaffold.infra.history.models import ExtractionTask, ExtractionTemplate, TaskStatus, ValidationCheck, ValidationReport
from scaffold.infra.history.repository import ExtractionTaskRepository, ExtractionTemplateRepository
from scaffold.infra.time import _now

logger = logging.getLogger(__name__)


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
        self._template_repo: ExtractionTemplateRepository | None = None
        self._storage: ArtifactStorage | None = None

    async def __aenter__(self) -> ExtractionWorkspace:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._db_path))
        self._artifact_repo = ArtifactRepository(self._conn)
        self._task_repo = ExtractionTaskRepository(self._conn)
        self._template_repo = ExtractionTemplateRepository(self._conn)
        self._storage = ArtifactStorage(self._artifacts_dir)
        await self._artifact_repo.migrate()
        await self._task_repo.migrate()
        await self._template_repo.migrate()
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
            user_id=get_current_user_id(),
            upload_artifact_id=upload_artifact_id,
            status="goal_setting",
            requirements=requirements,
            created_at=now,
            updated_at=now,
        )
        await self._task_repo.create(task)
        return task

    async def save_template_from_task(self, task_id: str, name: str) -> dict[str, Any]:
        """把验证通过的任务固化为模板；返回 error dict 或模板摘要。"""
        if self._template_repo is None or self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        user_id = get_current_user_id()
        task = await self._task_repo.get(task_id)
        if task is None or task.user_id != user_id:
            return {"error": f"任务 {task_id} 不存在"}
        if task.status != "success":
            return {"error": f"任务 {task_id} 状态为 {task.status}，仅验证通过（success）的任务可保存为模板"}
        if task.script_artifact_id is None:
            return {"error": f"任务 {task_id} 没有抽取脚本工件，无法保存模板"}

        script_artifact = await self._artifact_repo.get(task.script_artifact_id) if self._artifact_repo else None
        if script_artifact is None or script_artifact.user_id != user_id:
            return {"error": f"任务 {task_id} 的脚本工件不存在"}
        script = (await self.read_artifact(script_artifact.artifact_id)).decode("utf-8", errors="replace")

        upload = await self._artifact_repo.get(task.upload_artifact_id) if self._artifact_repo else None
        if upload is None or upload.user_id != user_id:
            return {"error": f"任务 {task_id} 的来源文件不存在"}
        content = await self.read_artifact(upload.artifact_id)
        fingerprint = await asyncio.to_thread(compute_fingerprint, content)

        now = _now()
        template = ExtractionTemplate(
            template_id=f"tpl-{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            name=name,
            goal=task.requirements or {},
            script=script,
            fingerprint=fingerprint,
            source_file_name=upload.original_name,
            created_at=now,
            updated_at=now,
        )
        await self._template_repo.create(template)
        return {
            "template_id": template.template_id,
            "name": template.name,
            "signature": fingerprint["signature"],
        }

    async def match_template(self, artifact_id: str) -> dict[str, Any]:
        """按工件结构指纹匹配当前用户的模板；返回 matched 或 error。"""
        if self._template_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        user_id = get_current_user_id()
        artifact = await self.get_artifact(artifact_id)
        if artifact is None:
            return {"error": f"工件 {artifact_id} 不存在"}
        if artifact.artifact_type != "upload":
            return {"error": f"工件 {artifact_id} 不是上传文件，无法匹配模板"}
        content = await self.read_artifact(artifact_id)
        fingerprint = await asyncio.to_thread(compute_fingerprint, content)
        template = await self._template_repo.find_by_signature(fingerprint["signature"], user_id)
        if template is None:
            return {
                "matched": False,
                "reason": "结构指纹不匹配：列名或表结构与已存模板不一致，需走完整抽取流程",
                "signature": fingerprint["signature"],
            }
        return {
            "matched": True,
            "template": {
                "template_id": template.template_id,
                "name": template.name,
                "source_file_name": template.source_file_name,
                "script": template.script,
                "signature": template.fingerprint.get("signature"),
            },
        }

    async def list_templates(self) -> list[dict[str, Any]]:
        """列出当前用户的模板摘要（不含脚本全文）。"""
        if self._template_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        templates = await self._template_repo.list_by_user(get_current_user_id())
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "source_file_name": t.source_file_name,
                "signature": t.fingerprint.get("signature"),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in templates
        ]

    async def rename_template(self, template_id: str, name: str) -> dict[str, Any]:
        """重命名当前用户的模板。"""
        if self._template_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        user_id = get_current_user_id()
        ok = await self._template_repo.rename(template_id, user_id, name, _now())
        if not ok:
            return {"error": f"模板 {template_id} 不存在"}
        return {"template_id": template_id, "name": name}

    async def delete_template(self, template_id: str) -> dict[str, Any]:
        """删除当前用户的模板。"""
        if self._template_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        ok = await self._template_repo.delete(template_id, get_current_user_id())
        if not ok:
            return {"error": f"模板 {template_id} 不存在"}
        return {"template_id": template_id, "deleted": True}

    async def get_task(self, task_id: str) -> ExtractionTask | None:
        """根据 task_id 查询抽取任务（非当前用户的任务视为不存在）。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        task = await self._task_repo.get(task_id)
        if task is not None and task.user_id != get_current_user_id():
            logger.warning(
                "cross-user access denied: task_id=%s owner=%s requester=%s",
                task_id,
                task.user_id,
                get_current_user_id(),
            )
            return None
        return task

    async def update_task(self, task: ExtractionTask) -> bool:
        """更新抽取任务；自动刷新 updated_at。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        task.updated_at = _now()
        return await self._task_repo.update(task)

    def check_task_transition(
        self,
        task: ExtractionTask,
        *,
        allowed: tuple[TaskStatus, ...],
        action: str,
    ) -> dict[str, Any] | None:
        """纯守卫：当前状态不在允许的前置集合中时返回与工具错误响应同构的 error dict，否则返回 None。"""
        if task.status not in allowed:
            return {"error": f"任务 {task.task_id} 当前状态为 {task.status}，无法{action}"}
        return None

    async def transition_task(
        self,
        task: ExtractionTask,
        to: TaskStatus,
        *,
        allowed: tuple[TaskStatus, ...],
        action: str,
    ) -> dict[str, Any] | None:
        """守卫并流转任务状态：守卫失败返回 error dict；成功时刷新时间戳并持久化，返回 None。"""
        error = self.check_task_transition(task, allowed=allowed, action=action)
        if error is not None:
            return error
        task.status = to
        await self.update_task(task)
        return None

    async def fail_task(
        self,
        task: ExtractionTask,
        *,
        summary: str,
        rule: str,
        details: str | None,
        suggestion: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """任务失败仪式：构造 ValidationReport、置 failed、持久化，并返回工具错误响应。"""
        report = ValidationReport(
            passed=False,
            summary=summary,
            checks=[ValidationCheck(rule=rule, status="fail", details=details)],
            suggestion=suggestion,
        )
        task.validation_report = report.model_dump()
        task.status = "failed"
        await self.update_task(task)
        return {"task_id": task.task_id, "error": summary, **(extra or {}), "status": task.status}

    async def list_tasks(self, thread_id: str) -> list[ExtractionTask]:
        """列出当前用户在某会话下的全部抽取任务。"""
        if self._task_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._task_repo.list_by_thread(thread_id, get_current_user_id())

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
            user_id=get_current_user_id(),
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
        """查询工件元数据（非当前用户的工件视为不存在）。"""
        if self._artifact_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        artifact = await self._artifact_repo.get(artifact_id)
        if artifact is not None and artifact.user_id != get_current_user_id():
            logger.warning(
                "cross-user access denied: artifact_id=%s owner=%s requester=%s",
                artifact_id,
                artifact.user_id,
                get_current_user_id(),
            )
            return None
        return artifact

    async def list_artifacts(
        self,
        thread_id: str,
        artifact_type: str | None = None,
    ) -> list[Artifact]:
        """列出当前用户在某会话下的工件；可指定类型过滤。"""
        if self._artifact_repo is None:
            raise RuntimeError("Workspace 未进入上下文")
        return await self._artifact_repo.list_by_thread(thread_id, get_current_user_id(), artifact_type)


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
