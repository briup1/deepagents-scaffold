"""对抽取结果 CSV 执行 DuckDB SQL 查询。

Phase 3 核心工具：让 Agent 能够对抽取结果执行 SQL 统计/筛选，
并支持跨文件对比分析（comparison_extraction_id）。
薄编排层：工件校验、临时文件、表加载、结果安全化均由
`scaffold.infra.extraction.data_query` 承担。
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.infra.extraction.data_query import TableRef, fetch_result, run_data_query, validate_select_only
from scaffold.plugins.tools._extraction_common import get_extraction_workspace

logger = logging.getLogger(__name__)


async def query_extracted_data(
    extraction_id: str,
    sql: str,
    limit: int = 100,
    thread_id: str | None = None,
    comparison_extraction_id: str | None = None,
    **kwargs: Any,
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

    checked_sql, sql_error = validate_select_only(sql)
    if sql_error or checked_sql is None:
        logger.warning("query_extracted_data SQL 校验未通过 | error=%s", sql_error)
        return {"error": sql_error}

    refs = [TableRef(artifact_id=extraction_id, table_name="data")]
    if comparison_extraction_id:
        refs = [
            TableRef(artifact_id=extraction_id, table_name="data_a"),
            TableRef(artifact_id=comparison_extraction_id, table_name="data_b"),
        ]

    logger.info("query_extracted_data 开始执行 | sql=%s limit=%s", checked_sql, limit)
    async with get_extraction_workspace() as ws:
        result = await run_data_query(
            ws,
            refs,
            lambda con: fetch_result(con, checked_sql, limit),
            thread_id=thread_id,
        )

    if "error" in result:
        logger.warning("query_extracted_data 返回错误 | error=%s", result["error"])
    else:
        logger.info(
            "query_extracted_data 执行成功 | columns=%s row_count=%s truncated=%s",
            result.get("columns"),
            result.get("row_count"),
            result.get("truncated"),
        )
    return result
