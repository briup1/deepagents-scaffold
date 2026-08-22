"""对抽取结果 CSV 执行 DuckDB SQL 查询。

Phase 3 核心工具：让 Agent 能够对抽取结果执行 SQL 统计/筛选，
并支持跨文件对比分析（comparison_extraction_id）。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import duckdb

from scaffold.infra.artifacts import ArtifactStorage
from scaffold.infra.config.app_config import get_app_config
from scaffold.plugins.tools._extraction_common import _get_artifact

logger = logging.getLogger(__name__)


def _get_storage() -> ArtifactStorage:
    """根据当前配置获取工件存储实例。"""
    config = get_app_config()
    base_dir = Path(config.database.sqlite_dir or "./data") / "artifacts"
    return ArtifactStorage(base_dir)


def _validate_select_only(sql: str) -> tuple[str | None, str | None]:
    """限制为只读 SELECT/WITH 语句。返回 (规范化 SQL, 错误信息)，二者互斥。"""
    stripped = sql.strip().rstrip(";").strip()
    lowered = stripped.lower()
    if not lowered.startswith(("select", "with")):
        return None, "仅支持 SELECT 查询语句（只读），当前语句以其他关键字开头"
    # 禁止分号注入多条语句
    if ";" in stripped:
        return None, "不支持多条语句或内嵌分号"
    return stripped, None


def _load_table(con: duckdb.DuckDBPyConnection, table_name: str, csv_path: str) -> None:
    """从 CSV 加载内存表，避免并发读写文件锁。"""
    con.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv_auto(?)", [csv_path])


def _fetch_result(con: duckdb.DuckDBPyConnection, sql: str, limit: int) -> dict[str, Any]:
    """执行查询并转换为 columns/rows 结构。"""
    result = con.execute(sql)
    columns = [desc[0] for desc in result.description] if result.description else []
    rows = result.fetchmany(limit + 1)
    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    # 值统一 JSON 序列化安全化（DuckDB 返回 datetime/Decimal 等）
    def _safe(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        try:
            import json  # noqa: PLC0415

            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return str(value)

    safe_rows = [[_safe(cell) for cell in row] for row in rows]
    return {"columns": columns, "rows": safe_rows, "row_count": len(safe_rows), "truncated": truncated}


async def _artifact_csv(artifact_id: str, expected_type: str, thread_id: str | None) -> tuple[Any, str] | tuple[dict[str, Any], None]:
    """校验工件并返回 (artifact, 绝对 csv 路径)；失败返回 (错误 dict, None)。"""
    artifact = await _get_artifact(artifact_id)
    if artifact is None:
        return {"error": f"工件 {artifact_id} 不存在"}, None
    if artifact.artifact_type != expected_type:
        expected_label = {"extraction": "抽取结果", "upload": "上传文件"}.get(expected_type, expected_type)
        return (
            {"error": f"工件 {artifact_id} 不是{expected_label}（实际类型为 {artifact.artifact_type}）"},
            None,
        )
    if thread_id is not None and artifact.thread_id != thread_id:
        return {"error": f"工件 {artifact_id} 不属于会话 {thread_id}，已拒绝访问"}, None

    storage = _get_storage()
    try:
        content = await asyncio.to_thread(storage.read, artifact.stored_path)
    except FileNotFoundError:
        return {"error": f"工件文件不存在：{artifact.stored_path}"}, None

    # 写到临时文件供 DuckDB 读取（并发安全）
    import tempfile  # noqa: PLC0415

    fd, tmp_path = tempfile.mkstemp(suffix=".csv")
    with open(fd, "wb") as fh:
        fh.write(content)
    return artifact, tmp_path


async def query_extracted_data(
    extraction_id: str,
    sql: str,
    limit: int = 100,
    thread_id: str | None = None,
    comparison_extraction_id: str | None = None,
) -> dict[str, Any]:
    """对抽取结果 CSV 执行 DuckDB SQL 查询。

    Args:
        extraction_id: 抽取结果工件 ID。
        sql: 只读 SQL（SELECT / WITH）。单文件时表名为 ``data``；
            提供 comparison_extraction_id 时表名为 ``data_a``（主文件）与 ``data_b``（对比文件）。
        limit: 返回的最大行数，默认 100。
        thread_id: 可选，调用方所在会话；提供时校验工件归属。
        comparison_extraction_id: 可选，对比文件工件 ID，用于跨文件 JOIN。

    Returns:
        {"columns": [...], "rows": [...], "row_count": N, "truncated": bool}
        或 {"error": "可读错误信息"}。
    """
    logger.info(
        "query_extracted_data 被调用: extraction_id=%s comparison=%s",
        extraction_id,
        comparison_extraction_id,
    )

    checked_sql, sql_error = _validate_select_only(sql)
    if sql_error:
        return {"error": sql_error}

    artifact, primary_path = await _artifact_csv(extraction_id, "extraction", thread_id)
    if primary_path is None:
        return artifact  # type: ignore[return-value]

    comparison_path: str | None = None
    if comparison_extraction_id:
        comp, comparison_path = await _artifact_csv(comparison_extraction_id, "extraction", thread_id)
        if comparison_path is None:
            return comp  # type: ignore[return-value]

    def _run() -> dict[str, Any]:
        con = duckdb.connect()
        try:
            try:
                if comparison_path:
                    _load_table(con, "data_a", primary_path)  # type: ignore[arg-type]
                    _load_table(con, "data_b", comparison_path)
                else:
                    _load_table(con, "data", primary_path)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                return {"error": f"CSV 读取失败：{exc}"}

            try:
                return _fetch_result(con, checked_sql, limit)  # type: ignore[arg-type]
            except Exception as exc:  # noqa: BLE001
                return {"error": f"SQL 执行失败：{exc}"}
        finally:
            con.close()

    try:
        result = await asyncio.to_thread(_run)
    finally:
        for p in (primary_path, comparison_path):
            if p:
                Path(p).unlink(missing_ok=True)
    return result
