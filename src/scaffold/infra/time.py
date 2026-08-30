"""共享时间工具。"""

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
