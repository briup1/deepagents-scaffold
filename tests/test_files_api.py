"""文件上传 API 端到端测试。"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook


def _unique_thread_id() -> str:
    return f"t-{uuid.uuid4().hex[:8]}"


def _make_excel_bytes() -> bytes:
    """生成一个最小可用的 .xlsx 文件。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"
    ws.append(["carrier", "pol", "pod", "container_type", "amount"])
    ws.append(["MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3200])
    ws.append(["COSCO", "SHANGHAI", "LOS ANGELES", "20GP", 1800])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def excel_bytes() -> bytes:
    return _make_excel_bytes()


class TestFilesUpload:
    def test_upload_excel_success(self, client: TestClient, excel_bytes: bytes) -> None:
        thread_id = _unique_thread_id()
        response = client.post(
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
        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == thread_id
        assert data["artifact_type"] == "upload"
        assert data["original_name"] == "quote.xlsx"
        assert data["size_bytes"] == len(excel_bytes)
        assert data["stored_path"].startswith(f"{thread_id}/uploads/")
        assert Path(data["stored_path"]).name.endswith("quote.xlsx")

    def test_upload_missing_thread_id(self, client: TestClient, excel_bytes: bytes) -> None:
        response = client.post(
            "/api/files/upload",
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 422

    def test_upload_empty_file(self, client: TestClient) -> None:
        response = client.post(
            "/api/files/upload",
            data={"thread_id": _unique_thread_id()},
            files={
                "file": (
                    "empty.xlsx",
                    io.BytesIO(b""),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 400

    def test_upload_non_excel_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/api/files/upload",
            data={"thread_id": _unique_thread_id()},
            files={"file": ("malicious.py", io.BytesIO(b"print('hack')"), "text/x-python")},
        )
        assert response.status_code == 415

    def test_upload_oversized_file(self, client: TestClient) -> None:
        large_content = b"x" * (21 * 1024 * 1024)  # 21MB
        response = client.post(
            "/api/files/upload",
            data={"thread_id": _unique_thread_id()},
            files={
                "file": (
                    "huge.xlsx",
                    io.BytesIO(large_content),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 413

    def test_thread_isolation(self, client: TestClient, excel_bytes: bytes) -> None:
        thread_1 = _unique_thread_id()
        thread_2 = _unique_thread_id()
        client.post(
            "/api/files/upload",
            data={"thread_id": thread_1},
            files={
                "file": (
                    "a.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        client.post(
            "/api/files/upload",
            data={"thread_id": thread_2},
            files={
                "file": (
                    "b.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        response = client.get(f"/api/files/?thread_id={thread_1}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["artifacts"][0]["original_name"] == "a.xlsx"

        response = client.get(f"/api/files/?thread_id={thread_2}")
        data = response.json()
        assert data["total"] == 1
        assert data["artifacts"][0]["original_name"] == "b.xlsx"

    def test_list_files_with_type_filter(self, client: TestClient, excel_bytes: bytes) -> None:
        thread_id = _unique_thread_id()
        client.post(
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

        response = client.get(f"/api/files/?thread_id={thread_id}&artifact_type=upload")
        data = response.json()
        assert data["total"] == 1

        response = client.get(f"/api/files/?thread_id={thread_id}&artifact_type=script")
        data = response.json()
        assert data["total"] == 0

    def test_get_file_metadata(self, client: TestClient, excel_bytes: bytes) -> None:
        thread_id = _unique_thread_id()
        response = client.post(
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
        artifact_id = response.json()["artifact_id"]

        response = client.get(f"/api/files/{artifact_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["artifact_id"] == artifact_id
        assert data["thread_id"] == thread_id

    def test_get_file_not_found(self, client: TestClient) -> None:
        response = client.get("/api/files/art-nonexistent")
        assert response.status_code == 404
