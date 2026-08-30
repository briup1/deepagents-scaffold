"""analyze 工具 NL→SQL 构造器的纯函数测试（不依赖 workspace / 数据库）。"""

from __future__ import annotations

from scaffold.plugins.tools.analyze_extracted_data import (
    DEFAULT_JOIN_KEYS,
    _build_comparison_sql,
    _build_single_sql,
)

COLUMNS = {
    "carrier": "varchar",
    "pol": "varchar",
    "pod": "varchar",
    "container_type": "varchar",
    "amount": "double",
}


class TestBuildSingleSql:
    def test_min_intent(self) -> None:
        sql, summary = _build_single_sql("哪条航线最便宜？", COLUMNS)
        assert sql is not None
        assert "ORDER BY amount ASC" in sql
        assert summary

    def test_max_with_group(self) -> None:
        sql, _ = _build_single_sql("按 pod 统计最高运费", COLUMNS)
        assert sql is not None
        assert "MAX(amount)" in sql
        assert "GROUP BY pod" in sql

    def test_avg_without_price_column_returns_error(self) -> None:
        sql, error = _build_single_sql("平均是多少", {"carrier": "varchar", "pod": "varchar"})
        assert sql is None
        assert "数值列" in error

    def test_count_intent(self) -> None:
        sql, _ = _build_single_sql("一共有多少条记录？", COLUMNS)
        assert sql == "SELECT COUNT(*) AS cnt FROM data"

    def test_group_by_detected_column(self) -> None:
        sql, _ = _build_single_sql("按 carrier 分组统计", COLUMNS)
        assert sql is not None
        assert "GROUP BY carrier" in sql

    def test_fallback_returns_first_50_rows(self) -> None:
        sql, summary = _build_single_sql("随便看看", COLUMNS)
        assert sql == "SELECT * FROM data LIMIT 50"
        assert "50" in summary


class TestBuildComparisonSql:
    def test_default_join_keys(self) -> None:
        sql, summary = _build_comparison_sql(COLUMNS, dict(COLUMNS), list(DEFAULT_JOIN_KEYS))
        assert sql is not None
        assert "a.pol = b.pol" in sql
        assert "price_a" in sql and "price_b" in sql and "diff" in sql
        assert "对比" in summary

    def test_fallback_to_common_text_columns(self) -> None:
        columns_a = {"route": "varchar", "amount": "double"}
        columns_b = {"route": "varchar", "price": "double"}
        sql, _ = _build_comparison_sql(columns_a, columns_b, ["nonexistent_key"])
        assert sql is not None
        assert "a.route = b.route" in sql

    def test_no_common_text_columns_returns_error(self) -> None:
        sql, error = _build_comparison_sql({"a_col": "varchar"}, {"b_col": "varchar"}, list(DEFAULT_JOIN_KEYS))
        assert sql is None
        assert "无法对比" in error
