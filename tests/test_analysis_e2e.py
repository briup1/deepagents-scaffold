"""Phase 3 工具级端到端测试：上传 → 抽取 → 分析 → 生成式 UI 信封全链路。

不依赖任何 LLM，是 Phase 3 完成判定的确定性自动化证据（L1 层）。
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.analyze_extracted_data import analyze_extracted_data
from scaffold.plugins.tools.execute_extraction_code import execute_extraction_code
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code
from scaffold.plugins.tools.generative_ui import render_ui
from scaffold.plugins.tools.query_extracted_data import query_extracted_data


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


class TestAnalysisE2E:
    @pytest.fixture
    async def extracted(self, client: TestClient) -> dict[str, str]:
        """返回 {extraction_id, comparison_id}，均为 thread=t-e2e 下的抽取结果。"""
        return {
            "extraction_id": await _run_extraction(client, "t-e2e", _make_excel_bytes(QUOTE_A_ROWS)),
            "comparison_id": await _run_extraction(client, "t-e2e", _make_excel_bytes(QUOTE_B_ROWS)),
        }

    async def test_full_chain_query_render(self, extracted: dict[str, str]) -> None:
        """场景 A+D：SQL 聚合查询 → 结果可转成 data_table 信封。"""
        q = await query_extracted_data(
            extraction_id=extracted["extraction_id"],
            sql="SELECT pod, MIN(amount) AS min_price FROM data GROUP BY pod ORDER BY min_price",
        )
        assert "error" not in q
        assert q["row_count"] == 2

        # 把查询结果转换为符合组件规范的 data_table props
        columns = [{"key": col, "label": col} for col in q["columns"]]
        rows = [dict(zip(q["columns"], row)) for row in q["rows"]]
        envelope = await render_ui(
            type="data_table",
            props={"title": "各目的港最低运价", "columns": columns, "rows": rows},
        )
        assert envelope["generative_ui"]["type"] == "data_table"
        props = envelope["generative_ui"]["props"]
        assert props["columns"][0] == {"key": "pod", "label": "pod"}
        assert props["rows"][0]["pod"] == "LOS ANGELES"
        assert props["rows"][0]["min_price"] == 1800

    async def test_full_chain_analyze_render(self, extracted: dict[str, str]) -> None:
        """场景 B+D：自然语言分析 → chart 信封。"""
        a = await analyze_extracted_data(
            extraction_id=extracted["extraction_id"],
            request="按 pod 分组统计最低运价",
        )
        assert "error" not in a
        assert a["row_count"] == 2

        chart_data = [{"label": row[0], "value": row[1]} for row in a["rows"]]
        envelope = await render_ui(
            type="chart",
            props={"title": "各目的港最低运价", "kind": "bar", "data": chart_data},
        )
        assert envelope["generative_ui"]["type"] == "chart"
        assert envelope["generative_ui"]["props"]["kind"] == "bar"
        assert envelope["generative_ui"]["props"]["data"][0]["label"] == "LOS ANGELES"

    async def test_full_chain_comparison(self, extracted: dict[str, str]) -> None:
        """场景 C：多文件对比分析返回双方价格与差值。"""
        c = await analyze_extracted_data(
            extraction_id=extracted["extraction_id"],
            request="对比两份报价单相同航线的价格",
            comparison_extraction_id=extracted["comparison_id"],
        )
        assert "error" not in c
        assert "diff" in c["columns"]
        assert c["row_count"] >= 1
        # MSC 航线 a=3200, b=3000, diff=-200
        msc = [r for r in c["rows"] if r[c["columns"].index("carrier")] == "MSC"][0]
        assert msc[c["columns"].index("diff")] == -200

    async def test_session_isolation_chain(self, client: TestClient, extracted: dict[str, str]) -> None:
        """场景 E-4：另一会话的 thread_id 无法访问本会话抽取结果。"""
        other = await _run_extraction(client, "t-other", _make_excel_bytes(QUOTE_A_ROWS))
        # t-other 的调用方用 t-e2e 的 extraction_id 时被拒
        result = await query_extracted_data(
            extraction_id=extracted["extraction_id"],
            sql="SELECT * FROM data",
            thread_id="t-other",
        )
        assert "error" in result
        assert "不属于会话" in result["error"]
        # 正确归属的仍可访问
        ok = await query_extracted_data(extraction_id=other, sql="SELECT * FROM data", thread_id="t-other")
        assert "error" not in ok
