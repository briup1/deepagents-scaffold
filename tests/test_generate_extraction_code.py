"""generate_extraction_code 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

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


class TestGenerateExtractionCode:
    @pytest.fixture
    def upload_artifact_id(self, client: TestClient) -> str:
        excel_bytes = _make_excel_bytes()
        response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-generate"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200
        return response.json()["artifact_id"]

    async def test_generate_extraction_code_success(self, upload_artifact_id: str) -> None:
        requirements = {
            "description": "抽取运价信息",
            "fields": [
                {"name": "carrier", "required": True},
                {"name": "pol", "required": True},
                {"name": "pod", "required": True},
                {"name": "container_type", "required": True},
                {"name": "amount", "type": "number", "required": True},
            ],
        }
        result = await generate_extraction_code(
            upload_artifact_id=upload_artifact_id,
            requirements=requirements,
        )

        assert "error" not in result
        assert result["status"] == "code_generated"
        assert result["task_id"].startswith("ext-")
        assert result["script_artifact_id"].startswith("art-")
        assert "import pandas" in result["script_content"]

    async def test_generate_extraction_code_invalid_artifact(self) -> None:
        result = await generate_extraction_code(
            upload_artifact_id="art-nonexistent",
            requirements={"fields": []},
        )
        assert "error" in result
