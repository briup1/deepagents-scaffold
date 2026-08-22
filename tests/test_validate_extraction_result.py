"""validate_extraction_result 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.execute_extraction_code import execute_extraction_code
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code
from scaffold.plugins.tools.validate_extraction_result import validate_extraction_result


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


class TestValidateExtractionResult:
    @pytest.fixture
    async def task_id(self, client: TestClient) -> str:
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-validate"},
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
                "expected_samples": [
                    {
                        "carrier": "MSC",
                        "pol": "SHANGHAI",
                        "pod": "LOS ANGELES",
                        "container_type": "40HQ",
                        "amount": 3200,
                    }
                ],
            },
        )
        assert "error" not in gen_result
        task_id = gen_result["task_id"]

        exec_result = await execute_extraction_code(task_id=task_id)
        assert "error" not in exec_result
        return task_id

    async def test_validate_success(self, task_id: str) -> None:
        result = await validate_extraction_result(task_id=task_id)

        assert "error" not in result
        assert result["passed"] is True
        assert result["status"] == "success"
        assert any(check["rule"].startswith("字段 amount") for check in result["checks"])

    async def test_validate_missing_task(self) -> None:
        result = await validate_extraction_result(task_id="ext-nonexistent")
        assert "error" in result
