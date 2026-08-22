"""query_extracted_data 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.execute_extraction_code import execute_extraction_code
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code
from scaffold.plugins.tools.query_extracted_data import query_extracted_data


def _make_excel_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"
    ws.append(["carrier", "pol", "pod", "container_type", "amount"])
    ws.append(["MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3200])
    ws.append(["COSCO", "SHANGHAI", "LOS ANGELES", "20GP", 1800])
    ws.append(["ONE", "NINGBO", "LONG BEACH", "40HQ", 3100])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
async def extraction_id(client: TestClient) -> str:
    """完整抽取链路：上传 → 生成脚本 → 执行，返回抽取结果工件 ID。"""
    excel_bytes = _make_excel_bytes()
    resp = client.post(
        "/api/files/upload",
        data={"thread_id": "t-query"},
        files={
            "file": (
                "quote.xlsx",
                io.BytesIO(excel_bytes),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200
    upload_artifact_id = resp.json()["artifact_id"]

    gen = await generate_extraction_code(
        upload_artifact_id=upload_artifact_id,
        requirements={
            "description": "抽取运价",
            "fields": [
                {"name": "carrier", "required": True},
                {"name": "pol", "required": True},
                {"name": "pod", "required": True},
                {"name": "container_type", "required": True},
                {"name": "amount", "type": "number", "required": True},
            ],
        },
    )
    assert "error" not in gen
    exe = await execute_extraction_code(task_id=gen["task_id"])
    assert "error" not in exe
    return exe["extracted_artifact_id"]


class TestQueryExtractedData:
    async def test_aggregate_query(self, extraction_id: str) -> None:
        """合法聚合 SQL 返回结构化结果。"""
        result = await query_extracted_data(
            extraction_id=extraction_id,
            sql="SELECT pod, MIN(amount) AS min_price FROM data GROUP BY pod ORDER BY min_price",
        )
        assert "error" not in result
        assert result["columns"] == ["pod", "min_price"]
        assert result["row_count"] == 2
        # LOS ANGELES 最低价为 1800（COSCO 20GP），LONG BEACH 为 3100
        by_pod = {row[0]: row[1] for row in result["rows"]}
        assert by_pod["LOS ANGELES"] == 1800
        assert by_pod["LONG BEACH"] == 3100
        assert result["truncated"] is False

    async def test_limit_truncation(self, extraction_id: str) -> None:
        """limit 截断并标记 truncated。"""
        result = await query_extracted_data(
            extraction_id=extraction_id,
            sql="SELECT * FROM data",
            limit=2,
        )
        assert "error" not in result
        assert result["row_count"] == 2
        assert result["truncated"] is True

    async def test_invalid_sql_returns_error(self, extraction_id: str) -> None:
        """非法 SQL 返回可读错误，不抛异常。"""
        result = await query_extracted_data(
            extraction_id=extraction_id,
            sql="SELECT * FORM data",
        )
        assert "error" in result
        assert "SQL" in result["error"]

    async def test_non_select_rejected(self, extraction_id: str) -> None:
        """非只读语句被拒绝。"""
        result = await query_extracted_data(
            extraction_id=extraction_id,
            sql="DROP TABLE data",
        )
        assert "error" in result
        assert "SELECT" in result["error"]

    async def test_unknown_artifact(self) -> None:
        """不存在的工件返回错误。"""
        result = await query_extracted_data(extraction_id="art-nonexistent", sql="SELECT * FROM data")
        assert "error" in result

    async def test_wrong_artifact_type_rejected(self, client: TestClient) -> None:
        """非 extraction 类型工件被拒绝。"""
        excel_bytes = _make_excel_bytes()
        resp = client.post(
            "/api/files/upload",
            data={"thread_id": "t-query"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        upload_id = resp.json()["artifact_id"]
        result = await query_extracted_data(extraction_id=upload_id, sql="SELECT * FROM data")
        assert "error" in result
        assert "不是抽取结果" in result["error"]

    async def test_cross_thread_rejected(self, extraction_id: str) -> None:
        """thread_id 校验：调用方会话与工件归属不一致时拒绝访问。"""
        result = await query_extracted_data(
            extraction_id=extraction_id,
            sql="SELECT * FROM data",
            thread_id="another-thread",
        )
        assert "error" in result
        assert "不属于会话" in result["error"]
