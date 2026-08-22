"""preview_excel 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.preview_excel import preview_excel


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


class TestPreviewExcel:
    @pytest.fixture
    def excel_bytes(self) -> bytes:
        return _make_excel_bytes()

    @pytest.fixture
    def artifact_id(self, client: TestClient, excel_bytes: bytes) -> str:
        response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-preview"},
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

    async def test_preview_excel_success(self, artifact_id: str) -> None:
        result = await preview_excel(artifact_id=artifact_id, limit=2)

        assert "error" not in result
        assert result["sheet_names"] == ["Quotes"]
        assert result["columns"] == ["carrier", "pol", "pod", "container_type", "amount"]
        assert len(result["sample_rows"]) == 2
        assert result["total_rows"] == 3

    async def test_preview_excel_invalid_sheet(self, artifact_id: str) -> None:
        result = await preview_excel(artifact_id=artifact_id, sheet_index=5)
        assert "error" in result
        assert "超出范围" in result["error"]

    async def test_preview_excel_not_found(self) -> None:
        result = await preview_excel(artifact_id="art-nonexistent")
        assert "error" in result
        assert "不存在" in result["error"]
