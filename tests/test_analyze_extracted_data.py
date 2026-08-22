"""analyze_extracted_data 工具测试（自然语言意图识别 + 多文件对比）。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.analyze_extracted_data import analyze_extracted_data
from scaffold.plugins.tools.execute_extraction_code import execute_extraction_code
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code


def _make_excel_bytes(rows: list[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"
    ws.append(["carrier", "pol", "pod", "container_type", "amount"])
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


QUOTE_A_ROWS = [
    ("MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3200),
    ("COSCO", "SHANGHAI", "LOS ANGELES", "20GP", 1800),
    ("ONE", "NINGBO", "LONG BEACH", "40HQ", 3100),
]
QUOTE_B_ROWS = [
    ("MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3000),
    ("CMA", "NINGBO", "LONG BEACH", "40HQ", 2900),
]


async def _run_extraction(client: TestClient, thread_id: str, excel_bytes: bytes) -> str:
    resp = client.post(
        "/api/files/upload",
        data={"thread_id": thread_id},
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


class TestAnalyzeExtractedData:
    @pytest.fixture
    async def extraction_id(self, client: TestClient) -> str:
        return await _run_extraction(client, "t-analyze", _make_excel_bytes(QUOTE_A_ROWS))

    @pytest.fixture
    async def comparison_id(self, client: TestClient) -> str:
        return await _run_extraction(client, "t-analyze", _make_excel_bytes(QUOTE_B_ROWS))

    async def test_min_intent(self, extraction_id: str) -> None:
        """「最便宜」意图返回最低价行并带 SQL 与摘要。"""
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="哪条航线到洛杉矶最便宜？",
        )
        assert "error" not in result
        assert "sql" in result
        assert result["summary"]
        # 最低价为 COSCO 1800
        first = result["rows"][0]
        assert first[result["columns"].index("amount")] == 1800

    async def test_avg_intent(self, extraction_id: str) -> None:
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="计算平均运费",
        )
        assert "error" not in result
        avg_col = result["columns"][0]
        assert avg_col.startswith("avg_")
        avg_value = result["rows"][0][0]
        assert avg_value == pytest.approx((3200 + 1800 + 3100) / 3)

    async def test_count_intent(self, extraction_id: str) -> None:
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="一共有多少条记录？",
        )
        assert "error" not in result
        assert result["rows"][0][0] == 3

    async def test_group_intent(self, extraction_id: str) -> None:
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="按 pod 分组统计",
        )
        assert "error" not in result
        # 分组列 pod + cnt
        assert "pod" in result["columns"]
        assert "cnt" in result["columns"]
        assert result["row_count"] == 2

    async def test_comparison(self, extraction_id: str, comparison_id: str) -> None:
        """多文件对比：返回双方价格与差值列。"""
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="对比两份报价单相同航线的价格",
            comparison_extraction_id=comparison_id,
        )
        assert "error" not in result
        columns = result["columns"]
        assert "price_a" in columns
        assert "price_b" in columns
        assert "diff" in columns
        # MSC SHANGHAI→LOS ANGELES：a=3200, b=3000, diff=-200
        matched = [r for r in result["rows"] if r[columns.index("carrier")] == "MSC"]
        assert matched, "应存在 MSC 的对比行"
        row = matched[0]
        assert row[columns.index("price_a")] == 3200
        assert row[columns.index("price_b")] == 3000
        assert row[columns.index("diff")] == -200

    async def test_empty_request(self, extraction_id: str) -> None:
        result = await analyze_extracted_data(extraction_id=extraction_id, request="")
        assert "error" in result

    async def test_cross_thread_rejected(self, extraction_id: str) -> None:
        result = await analyze_extracted_data(
            extraction_id=extraction_id,
            request="按 pod 分组统计",
            thread_id="another-thread",
        )
        assert "error" in result
        assert "不属于会话" in result["error"]
