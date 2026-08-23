"""抽取工具公共辅助函数。

本模块现在只保留最小入口：
- `get_extraction_workspace()` 获取 ExtractionWorkspace 上下文管理器
- `_now()` 时间戳辅助

原先分散在多个 helper 中的连接管理、仓库调用、文件读取均已收进
`scaffold.infra.extraction.ExtractionWorkspace`。
"""

from __future__ import annotations

from datetime import datetime, timezone

from scaffold.infra.extraction import ExtractionWorkspace, get_extraction_workspace

__all__ = ["ExtractionWorkspace", "get_extraction_workspace", "_now"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
