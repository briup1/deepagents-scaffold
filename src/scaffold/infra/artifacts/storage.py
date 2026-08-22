"""工件文件系统存储。"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

UPLOAD_SUBDIR = "uploads"
SCRIPT_SUBDIR = "scripts"
EXTRACTION_SUBDIR = "extractions"
REPORT_SUBDIR = "reports"

ARTIFACT_SUBDIRS: dict[str, str] = {
    "upload": UPLOAD_SUBDIR,
    "script": SCRIPT_SUBDIR,
    "extraction": EXTRACTION_SUBDIR,
    "report": REPORT_SUBDIR,
}


def _sanitize_filename(name: str) -> str:
    """清理文件名，移除路径分隔符和特殊字符，保留扩展名。"""
    base = Path(name).name
    cleaned = re.sub(r"[^\w.\-]", "_", base)
    if not cleaned or cleaned.startswith("."):
        cleaned = f"file_{cleaned}"
    return cleaned


class ArtifactStorage:
    """管理工件在本地文件系统中的持久化。

    所有工件按 ``{base_dir}/{thread_id}/{artifact_type_dir}/{artifact_id}-{filename}``
    存放，天然实现会话隔离。
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _thread_dir(self, thread_id: str, artifact_type: str) -> Path:
        subdir = ARTIFACT_SUBDIRS.get(artifact_type, UPLOAD_SUBDIR)
        path = self._base_dir / thread_id / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _relative_path(self, thread_id: str, artifact_type: str, filename: str) -> str:
        subdir = ARTIFACT_SUBDIRS.get(artifact_type, UPLOAD_SUBDIR)
        return f"{thread_id}/{subdir}/{filename}"

    def save_upload(
        self,
        thread_id: str,
        filename: str,
        content: bytes,
    ) -> tuple[str, str]:
        """保存上传文件，返回 artifact_id 和相对存储路径。"""
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        safe_name = _sanitize_filename(filename)
        target_name = f"{artifact_id}-{safe_name}"
        target_path = self._thread_dir(thread_id, "upload") / target_name
        target_path.write_bytes(content)
        relative_path = self._relative_path(thread_id, "upload", target_name)
        return artifact_id, relative_path

    def resolve_path(self, stored_path: str) -> Path:
        """将数据库存储的相对路径解析为绝对路径，并检查是否落在 base_dir 内。"""
        target = (self._base_dir / stored_path).resolve()
        if not target.is_relative_to(self._base_dir.resolve()):
            raise ValueError(f"非法路径：{stored_path}")
        return target

    def read(self, stored_path: str) -> bytes:
        """读取工件内容。"""
        path = self.resolve_path(stored_path)
        if not path.exists():
            raise FileNotFoundError(f"工件不存在：{stored_path}")
        return path.read_bytes()

    def write(self, thread_id: str, artifact_type: str, filename: str, content: bytes) -> tuple[str, str]:
        """保存生成的工件（脚本、抽取结果、报告）。"""
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        safe_name = _sanitize_filename(filename)
        target_name = f"{artifact_id}-{safe_name}"
        target_path = self._thread_dir(thread_id, artifact_type) / target_name
        target_path.write_bytes(content)
        relative_path = self._relative_path(thread_id, artifact_type, target_name)
        return artifact_id, relative_path

    def delete(self, stored_path: str) -> None:
        """删除工件文件。"""
        path = self.resolve_path(stored_path)
        if path.exists():
            path.unlink()
