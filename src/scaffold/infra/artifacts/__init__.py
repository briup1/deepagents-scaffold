"""工件基础设施：模型、文件存储、元数据仓库。"""

from __future__ import annotations

from scaffold.infra.artifacts.models import Artifact
from scaffold.infra.artifacts.repository import ArtifactRepository
from scaffold.infra.artifacts.storage import ArtifactStorage

__all__ = ["Artifact", "ArtifactRepository", "ArtifactStorage"]
