"""文件与工件管理 API。"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from scaffold.api.deps import get_artifact_repo
from scaffold.infra.artifacts import Artifact, ArtifactStorage
from scaffold.infra.config.app_config import get_app_config

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls
}
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _get_storage() -> ArtifactStorage:
    """获取工件存储实例。"""
    config = get_app_config()
    base_dir = config.database.sqlite_dir or "./data"
    artifacts_dir = os.path.join(base_dir, "artifacts")
    return ArtifactStorage(Path(artifacts_dir))


@router.post("/upload")
async def upload_file(
    request: Request,
    thread_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """上传 Excel 文件并保存为会话工件。"""
    if not thread_id:
        raise HTTPException(status_code=422, detail="thread_id 不能为空")

    if file.size is None:
        content = await file.read()
    else:
        content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")

    content_type = file.content_type or "application/octet-stream"
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix.lower()

    if content_type not in ALLOWED_MIME_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="仅支持 Excel 文件（.xlsx 或 .xls）")

    storage = _get_storage()
    artifact_id, stored_path = storage.save_upload(
        thread_id=thread_id,
        filename=original_name,
        content=content,
    )

    repo = get_artifact_repo(request)
    artifact = Artifact(
        artifact_id=artifact_id,
        thread_id=thread_id,
        artifact_type="upload",
        original_name=original_name,
        stored_path=stored_path,
        mime_type=content_type,
        size_bytes=len(content),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    await repo.create(artifact)

    return {
        "artifact_id": artifact_id,
        "thread_id": thread_id,
        "artifact_type": "upload",
        "original_name": original_name,
        "stored_path": stored_path,
        "mime_type": content_type,
        "size_bytes": len(content),
    }


@router.get("/")
async def list_files(
    request: Request,
    thread_id: str,
    artifact_type: str | None = None,
) -> dict[str, Any]:
    """列出某会话下的所有工件。"""
    if not thread_id:
        raise HTTPException(status_code=422, detail="thread_id 不能为空")

    repo = get_artifact_repo(request)
    artifacts = await repo.list_by_thread(thread_id, artifact_type)

    return {
        "thread_id": thread_id,
        "artifacts": [
            {
                "artifact_id": a.artifact_id,
                "artifact_type": a.artifact_type,
                "original_name": a.original_name,
                "stored_path": a.stored_path,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "created_at": a.created_at,
            }
            for a in artifacts
        ],
        "total": len(artifacts),
    }


@router.get("/{artifact_id}")
async def get_file(
    request: Request,
    artifact_id: str,
) -> dict[str, Any]:
    """获取单个工件元数据。"""
    repo = get_artifact_repo(request)
    artifact = await repo.get(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"工件 {artifact_id} 不存在")

    return {
        "artifact_id": artifact.artifact_id,
        "thread_id": artifact.thread_id,
        "artifact_type": artifact.artifact_type,
        "original_name": artifact.original_name,
        "stored_path": artifact.stored_path,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "created_at": artifact.created_at,
        "metadata": artifact.metadata,
    }
