"""对抽取结果执行只读 SQL 查询的深 module。

收编 query / analyze 两个工具共享的全部机制：工件存在性与会话归属校验、
临时 CSV 文件生命周期（finally 保证清理）、DuckDB 表加载、SELECT-only 校验、
结果 JSON 安全化。工具只需提供"拿到数据库连接后做什么"的回调。
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import duckdb

if TYPE_CHECKING:
    from scaffold.infra.extraction.workspace import ExtractionWorkspace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableRef:
    """一个待加载的工件引用：artifact_id + 目标表名（工件类型恒为抽取结果）。"""

    artifact_id: str
    table_name: str


def validate_select_only(sql: str) -> tuple[str | None, str | None]:
    """限制为只读 SELECT/WITH 语句。返回 (规范化 SQL, 错误信息)，二者互斥。"""
    stripped = sql.strip().rstrip(";").strip()
    lowered = stripped.lower()
    if not lowered.startswith(("select", "with")):
        logger.warning("SQL 校验失败：非 SELECT/WITH 开头 | sql=%s", sql[:200])
        return None, "仅支持 SELECT 查询语句（只读），当前语句以其他关键字开头"
    # 禁止分号注入多条语句
    if ";" in stripped:
        logger.warning("SQL 校验失败：包含分号 | sql=%s", sql[:200])
        return None, "不支持多条语句或内嵌分号"
    return stripped, None


def fetch_result(con: duckdb.DuckDBPyConnection, sql: str, limit: int) -> dict[str, Any]:
    """执行查询并转换为 columns/rows 结构（值统一做 JSON 序列化安全化）。"""
    logger.info("DuckDB 执行 SQL | sql=%s limit=%s", sql, limit)
    result = con.execute(sql)
    columns = [desc[0] for desc in result.description] if result.description else []
    rows = result.fetchmany(limit + 1)
    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]
    logger.info("DuckDB 查询结果 | columns=%s row_count=%s truncated=%s", columns, len(rows), truncated)

    safe_rows = [[_json_safe(cell) for cell in row] for row in rows]
    return {"columns": columns, "rows": safe_rows, "row_count": len(safe_rows), "truncated": truncated}


def _json_safe(value: Any) -> Any:
    """DuckDB 可能返回 datetime/Decimal 等类型，不可 JSON 序列化时转字符串。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


async def run_data_query(
    ws: ExtractionWorkspace,
    refs: list[TableRef],
    run: Callable[[duckdb.DuckDBPyConnection], dict[str, Any]],
    *,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """校验工件、加载表、执行回调，并保证临时文件清理。

    Args:
        ws: 抽取工作区（已进入上下文）。
        refs: 待加载的工件引用列表，按顺序加载为对应表名。
        run: 拿到 DuckDB 连接后执行的同步回调（在线程池中运行），返回结果 dict。
        thread_id: 可选，调用方所在会话；提供时校验工件归属。

    Returns:
        回调返回的结果 dict，或 {"error": "可读错误信息"}。
    """
    tmp_paths: list[str] = []
    try:
        for ref in refs:
            csv_path, error = await _dump_artifact_csv(ws, ref, thread_id)
            if error is not None:
                return error
            assert csv_path is not None
            tmp_paths.append(csv_path)

        def _run() -> dict[str, Any]:
            con = duckdb.connect()
            try:
                try:
                    for ref, csv_path in zip(refs, tmp_paths, strict=True):
                        _load_table(con, ref.table_name, csv_path)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("DuckDB CSV 读取失败")
                    return {"error": f"CSV 读取失败：{exc}"}

                try:
                    return run(con)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("DuckDB SQL 执行失败")
                    return {"error": f"SQL 执行失败：{exc}"}
            finally:
                con.close()

        return await asyncio.to_thread(_run)
    finally:
        for p in tmp_paths:
            Path(p).unlink(missing_ok=True)


async def _dump_artifact_csv(
    ws: ExtractionWorkspace,
    ref: TableRef,
    thread_id: str | None,
) -> tuple[str, None] | tuple[None, dict[str, Any]]:
    """校验工件并转存为临时 CSV；成功返回 (路径, None)，失败返回 (None, 错误 dict)。"""
    artifact_id = ref.artifact_id
    logger.debug("校验工件 | artifact_id=%s thread_id=%s", artifact_id, thread_id)
    artifact = await ws.get_artifact(artifact_id)
    if artifact is None:
        logger.warning("工件不存在 | artifact_id=%s", artifact_id)
        return None, {"error": f"工件 {artifact_id} 不存在"}
    if artifact.artifact_type != "extraction":
        logger.warning(
            "工件类型不匹配 | artifact_id=%s actual=%s",
            artifact_id,
            artifact.artifact_type,
        )
        return None, {"error": f"工件 {artifact_id} 不是抽取结果（实际类型为 {artifact.artifact_type}）"}
    if thread_id is not None and artifact.thread_id != thread_id:
        logger.warning(
            "跨会话访问被拒 | artifact_id=%s artifact_thread=%s request_thread=%s",
            artifact_id,
            artifact.thread_id,
            thread_id,
        )
        return None, {"error": f"工件 {artifact_id} 不属于会话 {thread_id}，已拒绝访问"}

    try:
        content = await ws.read_artifact(artifact_id)
    except FileNotFoundError:
        logger.warning("工件文件不存在 | artifact_id=%s stored_path=%s", artifact_id, artifact.stored_path)
        return None, {"error": f"工件文件不存在：{artifact.stored_path}"}

    # 写到临时文件供 DuckDB 读取（并发安全）；由 run_data_query 统一清理
    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    with open(fd, "wb") as fh:
        fh.write(content)
    logger.debug("工件已转临时 CSV | artifact_id=%s tmp_path=%s bytes=%s", artifact_id, tmp_path, len(content))
    return tmp_path, None


def _load_table(con: duckdb.DuckDBPyConnection, table_name: str, csv_path: str) -> None:
    """从 CSV 加载内存表，避免并发读写文件锁。"""
    logger.debug("DuckDB 加载 CSV | table_name=%s csv_path=%s", table_name, csv_path)
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)", [csv_path])
    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    logger.info("DuckDB 表加载完成 | table_name=%s rows=%s", table_name, row_count)
