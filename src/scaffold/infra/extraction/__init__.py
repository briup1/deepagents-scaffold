"""抽取工作区：统一封装抽取任务、工件与存储的生命周期。"""

from __future__ import annotations

from scaffold.infra.extraction.workspace import ExtractionWorkspace, get_extraction_workspace

__all__ = ["ExtractionWorkspace", "get_extraction_workspace"]
