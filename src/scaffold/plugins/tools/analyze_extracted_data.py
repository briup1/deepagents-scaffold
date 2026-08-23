"""根据用户自然语言需求自动生成并执行 SQL 分析。

Phase 3 核心工具：MVP 采用规则化意图识别（无需调用 LLM），
支持最低/最高/平均/分组/计数/对比等常见分析意图。
"""

from __future__ import annotations

import logging
from typing import Any

from scaffold.plugins.tools._extraction_common import get_extraction_workspace
from scaffold.plugins.tools.query_extracted_data import _artifact_csv, _load_table, _validate_select_only

logger = logging.getLogger(__name__)

#: 常见数值（价格/金额）列名关键词，用于自动识别可聚合列
PRICE_KEYWORDS = ("amount", "price", "cost", "fee", "海运费", "运费", "金额", "价格", "费用", "报价")

#: 默认对比 JOIN 键（多文件对比时优先使用）
DEFAULT_JOIN_KEYS = ("pol", "pod", "container_type")

#: 类型为文本的 DuckDB 类型前缀
_TEXT_TYPE_PREFIXES = ("varchar", "text", "string", "date", "timestamp", "time", "blob")


def _describe_columns(con: Any, table: str) -> dict[str, str]:
    """返回 {列名: DuckDB 类型}。"""
    rows = con.execute(f"DESCRIBE SELECT * FROM {table}").fetchall()
    schema = {str(r[0]): str(r[1]).lower() for r in rows}
    logger.debug("DuckDB 表结构 | table=%s schema=%s", table, schema)
    return schema


def _is_numeric_type(duckdb_type: str) -> bool:
    return any(t in duckdb_type for t in ("int", "float", "double", "decimal", "numeric", "hugeint", "ubigint"))


def _pick_price_column(columns: dict[str, str]) -> str | None:
    """优先选择含价格关键词的数值列，其次选第一个数值列。"""
    for col, ctype in columns.items():
        lowered = col.lower()
        if any(k in lowered for k in PRICE_KEYWORDS) and _is_numeric_type(ctype):
            logger.debug("选中价格列 | column=%s type=%s", col, ctype)
            return col
    for col, ctype in columns.items():
        if _is_numeric_type(ctype):
            logger.debug("未找到价格关键词列， fallback 到第一个数值列 | column=%s type=%s", col, ctype)
            return col
    logger.warning("未找到任何数值列可用于聚合 | schema=%s", columns)
    return None


def _pick_text_columns(columns: dict[str, str], limit: int = 4) -> list[str]:
    """选择可用于 GROUP BY 的文本列。"""
    picked: list[str] = []
    for col, ctype in columns.items():
        if ctype.startswith(_TEXT_TYPE_PREFIXES) or not _is_numeric_type(ctype):
            picked.append(col)
        if len(picked) >= limit:
            break
    return picked


def _detect_group_column(request: str, columns: dict[str, str]) -> str | None:
    """从请求文本中匹配分组维度列。"""
    lowered = request.lower()
    for col in columns:
        if col.lower() in lowered:
            logger.debug("从请求中识别到分组列 | column=%s request=%s", col, request)
            return col
    logger.debug("未从请求中识别到分组列 | request=%s columns=%s", request, list(columns.keys()))
    return None


def _build_single_sql(request: str, columns: dict[str, str]) -> tuple[str, str] | tuple[None, str]:
    """构建单文件分析 SQL。返回 (SQL, 摘要) 或 (None, 错误信息)。"""
    lowered = request.lower()
    price_col = _pick_price_column(columns)
    group_col = _detect_group_column(request, columns)

    is_max = any(k in lowered for k in ("最高", "最贵", "最大", "max", "最贵"))
    is_min = any(k in lowered for k in ("最低", "最便宜", "最小", "min"))
    is_avg = any(k in lowered for k in ("平均", "均价", "avg", "average"))
    is_count = any(k in lowered for k in ("多少条", "数量", "几条", "count", "总行数"))
    is_group = any(k in lowered for k in ("按", "分组", "分别", "各", "每个", "group", "统计"))

    logger.debug(
        "意图识别 | request=%s price_col=%s group_col=%s is_min=%s is_max=%s is_avg=%s is_count=%s is_group=%s",
        request,
        price_col,
        group_col,
        is_min,
        is_max,
        is_avg,
        is_count,
        is_group,
    )

    if price_col is None and (is_min or is_max or is_avg):
        logger.warning("聚合失败：缺少数值列 | request=%s columns=%s", request, columns)
        return None, "未找到可聚合的数值列（金额/价格），请确认抽取结果包含数值字段"

    if is_count:
        if group_col:
            sql = f"SELECT {group_col}, COUNT(*) AS cnt FROM data GROUP BY {group_col} ORDER BY cnt DESC"
            logger.info("生成计数 SQL | sql=%s", sql)
            return sql, f"按 {group_col} 统计记录数"
        logger.info("生成计数 SQL | sql=SELECT COUNT(*) AS cnt FROM data")
        return "SELECT COUNT(*) AS cnt FROM data", "统计记录总数"

    if is_min and price_col:
        agg = f"MIN({price_col}) AS min_{price_col}"
        if group_col:
            sql = f"SELECT {group_col}, {agg} FROM data GROUP BY {group_col} ORDER BY min_{price_col} ASC LIMIT 10"
            logger.info("生成最低值 SQL | sql=%s", sql)
            return sql, f"按 {group_col} 统计最低 {price_col}"
        sql = f"SELECT * FROM data ORDER BY {price_col} ASC LIMIT 10"
        logger.info("生成最低值 SQL | sql=%s", sql)
        return sql, f"按 {price_col} 升序取最低 10 条"

    if is_max and price_col:
        agg = f"MAX({price_col}) AS max_{price_col}"
        if group_col:
            sql = f"SELECT {group_col}, {agg} FROM data GROUP BY {group_col} ORDER BY max_{price_col} DESC LIMIT 10"
            logger.info("生成最高值 SQL | sql=%s", sql)
            return sql, f"按 {group_col} 统计最高 {price_col}"
        sql = f"SELECT * FROM data ORDER BY {price_col} DESC LIMIT 10"
        logger.info("生成最高值 SQL | sql=%s", sql)
        return sql, f"按 {price_col} 降序取最高 10 条"

    if is_avg and price_col:
        if group_col:
            sql = f"SELECT {group_col}, AVG({price_col}) AS avg_{price_col} FROM data GROUP BY {group_col} ORDER BY avg_{price_col} ASC"
            logger.info("生成平均值 SQL | sql=%s", sql)
            return sql, f"按 {group_col} 计算平均 {price_col}"
        sql = f"SELECT AVG({price_col}) AS avg_{price_col} FROM data"
        logger.info("生成平均值 SQL | sql=%s", sql)
        return sql, f"计算 {price_col} 平均值"

    if is_group or group_col:
        if group_col:
            sql = (
                f"SELECT {group_col}, COUNT(*) AS cnt"
                + (f", AVG({price_col}) AS avg_{price_col}" if price_col else "")
                + f" FROM data GROUP BY {group_col} ORDER BY cnt DESC"
            )
            logger.info("生成分组统计 SQL | sql=%s", sql)
            return sql, f"按 {group_col} 分组统计"
        text_cols = _pick_text_columns(columns)
        if text_cols:
            col = text_cols[0]
            sql = f"SELECT {col}, COUNT(*) AS cnt FROM data GROUP BY {col} ORDER BY cnt DESC"
            logger.info("生成分组统计 SQL | sql=%s", sql)
            return sql, f"按 {col} 分组统计"

    # 兜底：返回全表前 N 行
    logger.info("未匹配到特定分析意图，返回前 50 行 | request=%s", request)
    return "SELECT * FROM data LIMIT 50", "返回数据前 50 行"


def _build_comparison_sql(
    columns_a: dict[str, str], columns_b: dict[str, str], join_keys: list[str]
) -> tuple[str, str] | tuple[None, str]:
    """构建跨文件对比 SQL。返回 (SQL, 摘要) 或 (None, 错误信息)。"""
    price_a = _pick_price_column(columns_a) or "amount"
    price_b = _pick_price_column(columns_b) or "amount"
    keys = [k for k in join_keys if k in columns_a and k in columns_b]
    logger.debug(
        "对比模式列匹配 | join_keys=%s matched_keys=%s schema_a=%s schema_b=%s", join_keys, keys, columns_a, columns_b
    )
    if not keys:
        # 取两表共有文本列的前 3 个
        common = [c for c in columns_a if c in columns_b and not _is_numeric_type(columns_a[c])]
        keys = common[:3]
        logger.debug("未命中默认 JOIN 键， fallback 到共有文本列 | keys=%s", keys)
    if not keys:
        logger.warning("对比失败：两份文件没有可用于 JOIN 的共有文本列")
        return None, "两份文件没有可用于 JOIN 的共有文本列，无法对比"

    # 展示列：主文件中的非数值列（排除 JOIN 键）
    display_cols = [c for c in columns_a if c not in keys and not _is_numeric_type(columns_a[c])][:3]

    select_parts = [f"a.{k} AS {k}" for k in keys]
    select_parts += [f"a.{c} AS {c}" for c in display_cols]
    select_parts += [f"a.{price_a} AS price_a", f"b.{price_b} AS price_b", f"b.{price_b} - a.{price_a} AS diff"]

    on_clause = " AND ".join(f"a.{k} = b.{k}" for k in keys)
    sql = f"SELECT {', '.join(select_parts)} FROM data_a a JOIN data_b b ON {on_clause} ORDER BY diff DESC"
    summary = f"按 {', '.join(keys)} 对比两份报价单价格（diff = 对比方 - 主方）"
    logger.info("生成跨文件对比 SQL | sql=%s summary=%s", sql, summary)
    return sql, summary


async def analyze_extracted_data(
    extraction_id: str,
    request: str,
    comparison_extraction_id: str | None = None,
    thread_id: str | None = None,
    join_keys: list[str] | None = None,
) -> dict[str, Any]:
    """根据用户自然语言需求自动生成并执行 SQL 分析。

    Args:
        extraction_id: 抽取结果工件 ID（主文件）。
        request: 自然语言分析需求，例如「哪条航线到洛杉矶最便宜」「按船公司分组统计」。
        comparison_extraction_id: 可选，对比文件工件 ID，触发跨文件对比分析。
        thread_id: 可选，调用方所在会话；提供时校验工件归属。
        join_keys: 可选，对比 JOIN 键，默认 pol/pod/container_type（不存在时自动取共有文本列）。

    Returns:
        {"columns": [...], "rows": [...], "row_count": N, "sql": "...", "summary": "..."}
        或 {"error": "可读错误信息"}。
    """
    logger.info(
        "analyze_extracted_data 被调用: extraction_id=%s comparison=%s request=%s",
        extraction_id,
        comparison_extraction_id,
        request,
    )
    if not request or not request.strip():
        return {"error": "分析需求不能为空"}

    async with get_extraction_workspace() as ws:
        artifact, primary_path = await _artifact_csv(ws, extraction_id, "extraction", thread_id)
        if primary_path is None:
            return artifact  # type: ignore[return-value]

        comparison_path: str | None = None
        if comparison_extraction_id:
            comp, comparison_path = await _artifact_csv(ws, comparison_extraction_id, "extraction", thread_id)
            if comparison_path is None:
                return comp  # type: ignore[return-value]

        def _run() -> dict[str, Any]:
            import duckdb  # noqa: PLC0415

            from scaffold.plugins.tools.query_extracted_data import _fetch_result  # noqa: PLC0415

            con = duckdb.connect()
            try:
                try:
                    if comparison_path:
                        _load_table(con, "data_a", primary_path)  # type: ignore[arg-type]
                        _load_table(con, "data_b", comparison_path)
                        columns_a = _describe_columns(con, "data_a")
                        columns_b = _describe_columns(con, "data_b")
                        keys = join_keys or list(DEFAULT_JOIN_KEYS)
                        logger.info("进入跨文件对比模式 | keys=%s", keys)
                        built = _build_comparison_sql(columns_a, columns_b, keys)
                        if built[0] is None:
                            return {"error": built[1]}
                        sql, summary = built  # type: ignore[misc]
                    else:
                        _load_table(con, "data", primary_path)  # type: ignore[arg-type]
                        columns = _describe_columns(con, "data")
                        logger.info("进入单文件自然语言分析模式 | schema=%s", columns)
                        built = _build_single_sql(request, columns)
                        if built[0] is None:
                            return {"error": built[1]}
                        sql, summary = built  # type: ignore[misc]
                except Exception as exc:  # noqa: BLE001
                    logger.exception("DuckDB CSV 读取失败")
                    return {"error": f"CSV 读取失败：{exc}"}

                try:
                    checked, sql_error = _validate_select_only(sql)
                    if sql_error:
                        logger.warning("SQL 校验未通过 | error=%s", sql_error)
                        return {"error": sql_error}
                    result = _fetch_result(con, checked, limit=100)  # type: ignore[arg-type]
                except Exception as exc:  # noqa: BLE001
                    logger.exception("DuckDB SQL 执行失败 | sql=%s", sql)
                    return {"error": f"SQL 执行失败：{exc}"}

                result["sql"] = sql
                result["summary"] = summary
                return result
            finally:
                con.close()

    import asyncio  # noqa: PLC0415

    try:
        result = await asyncio.to_thread(_run)
    finally:
        from pathlib import Path  # noqa: PLC0415

        for p in (primary_path, comparison_path):
            if p:
                Path(p).unlink(missing_ok=True)

    if "error" in result:
        logger.warning("analyze_extracted_data 返回错误 | error=%s", result["error"])
    else:
        logger.info(
            "analyze_extracted_data 执行成功 | sql=%s summary=%s columns=%s row_count=%s",
            result.get("sql"),
            result.get("summary"),
            result.get("columns"),
            result.get("row_count"),
        )
    return result
