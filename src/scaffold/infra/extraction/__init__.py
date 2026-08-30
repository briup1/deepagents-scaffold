"""抽取工作区：统一封装抽取任务、工件与存储的生命周期。"""

from __future__ import annotations

from scaffold.infra.extraction.data_query import TableRef, fetch_result, run_data_query, validate_select_only
from scaffold.infra.extraction.workspace import ExtractionWorkspace, get_extraction_workspace

__all__ = [
    "ExtractionWorkspace",
    "TableRef",
    "fetch_result",
    "get_extraction_workspace",
    "run_data_query",
    "validate_select_only",
]
