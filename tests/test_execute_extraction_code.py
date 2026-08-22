"""execute_extraction_code 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.execute_extraction_code import execute_extraction_code
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code


def _make_excel_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"
    ws.append(["carrier", "pol", "pod", "container_type", "amount"])
    ws.append(["MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3200])
    ws.append(["COSCO", "SHANGHAI", "LOS ANGELES", "20GP", 1800])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestExecuteExtractionCode:
    @pytest.fixture
    async def task_id(self, client: TestClient) -> str:
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-execute"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 200
        upload_artifact_id = upload_response.json()["artifact_id"]

        gen_result = await generate_extraction_code(
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
        assert "error" not in gen_result
        return gen_result["task_id"]

    async def test_execute_extraction_code_success(self, task_id: str, client: TestClient) -> None:
        result = await execute_extraction_code(task_id=task_id)

        assert "error" not in result
        assert result["status"] == "validating"
        extracted_artifact_id = result["extracted_artifact_id"]
        assert extracted_artifact_id.startswith("art-")
        assert result["total_rows"] == 2
        assert "carrier" in result["columns"]
        assert "amount" in result["columns"]

        # 验证抽取结果 CSV 可以通过下载端点获取
        download_response = client.get(f"/api/files/{extracted_artifact_id}/download")
        assert download_response.status_code == 200
        assert download_response.headers.get("content-disposition", "").startswith("attachment")
        content = download_response.content.decode("utf-8")
        assert "carrier" in content
        assert "MSC" in content
        assert "COSCO" in content

    async def test_execute_extraction_code_missing_task(self) -> None:
        result = await execute_extraction_code(task_id="ext-nonexistent")
        assert "error" in result
