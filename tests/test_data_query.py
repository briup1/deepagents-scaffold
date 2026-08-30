"""data_query module 测试：覆盖 query / analyze 共享的全部机制。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scaffold.infra.extraction.data_query import (
    TableRef,
    fetch_result,
    run_data_query,
    validate_select_only,
)
from scaffold.infra.extraction.workspace import ExtractionWorkspace

CSV_A = b"carrier,amount\nMSC,3200\nCOSCO,1800\n"
CSV_B = b"carrier,amount\nMSC,3000\nCMA,2900\n"


@pytest.fixture
async def workspace(tmp_path: Path):
    ws = ExtractionWorkspace(db_path=tmp_path / "history.db", artifacts_dir=tmp_path / "artifacts")
    async with ws:
        yield ws


async def _save_csv(ws: ExtractionWorkspace, thread_id: str, content: bytes, name: str) -> str:
    artifact = await ws.save_artifact(
        thread_id=thread_id,
        artifact_type="extraction",
        filename=name,
        content=content,
        mime_type="text/csv",
    )
    return artifact.artifact_id


class TestValidateSelectOnly:
    def test_select_accepted(self) -> None:
        checked, error = validate_select_only("SELECT * FROM data;")
        assert error is None
        assert checked == "SELECT * FROM data"

    def test_non_select_rejected(self) -> None:
        checked, error = validate_select_only("DROP TABLE data")
        assert checked is None
        assert error is not None
        assert "SELECT" in error

    def test_multi_statement_rejected(self) -> None:
        checked, error = validate_select_only("SELECT 1; SELECT 2")
        assert checked is None
        assert error is not None
        assert "分号" in error


class TestRunDataQuery:
    async def test_simple_query(self, workspace: ExtractionWorkspace) -> None:
        artifact_id = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=artifact_id, table_name="data")],
            lambda con: fetch_result(con, "SELECT carrier, amount FROM data ORDER BY amount", limit=100),
        )
        assert "error" not in result
        assert result["columns"] == ["carrier", "amount"]
        assert result["rows"] == [["COSCO", 1800], ["MSC", 3200]]
        assert result["truncated"] is False

    async def test_multi_table_join(self, workspace: ExtractionWorkspace) -> None:
        id_a = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        id_b = await _save_csv(workspace, "t-1", CSV_B, "b.csv")
        result = await run_data_query(
            workspace,
            [
                TableRef(artifact_id=id_a, table_name="data_a"),
                TableRef(artifact_id=id_b, table_name="data_b"),
            ],
            lambda con: fetch_result(
                con,
                "SELECT a.carrier, a.amount AS price_a, b.amount AS price_b "
                "FROM data_a a JOIN data_b b ON a.carrier = b.carrier",
                limit=100,
            ),
        )
        assert "error" not in result
        assert result["rows"] == [["MSC", 3200, 3000]]

    async def test_unknown_artifact(self, workspace: ExtractionWorkspace) -> None:
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id="art-nonexistent", table_name="data")],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
        )
        assert result == {"error": "工件 art-nonexistent 不存在"}

    async def test_wrong_artifact_type_rejected(self, workspace: ExtractionWorkspace) -> None:
        upload = await workspace.save_artifact(
            thread_id="t-1", artifact_type="upload", filename="q.xlsx", content=b"fake"
        )
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=upload.artifact_id, table_name="data")],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
        )
        assert "error" in result
        assert "不是抽取结果" in result["error"]

    async def test_cross_thread_rejected(self, workspace: ExtractionWorkspace) -> None:
        artifact_id = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=artifact_id, table_name="data")],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
            thread_id="t-other",
        )
        assert "error" in result
        assert "不属于会话" in result["error"]

    async def test_csv_read_failure(self, workspace: ExtractionWorkspace) -> None:
        artifact_id = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            # 非法表名使 DuckDB 加载阶段抛错，确定性触发 CSV 读取失败路径
            [TableRef(artifact_id=artifact_id, table_name="bad-name")],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
        )
        assert "error" in result
        assert "CSV 读取失败" in result["error"]

    async def test_sql_execution_failure(self, workspace: ExtractionWorkspace) -> None:
        artifact_id = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=artifact_id, table_name="data")],
            lambda con: fetch_result(con, "SELECT * FORM data", limit=100),
        )
        assert "error" in result
        assert "SQL 执行失败" in result["error"]

    async def test_temp_files_cleaned_on_success(
        self, workspace: ExtractionWorkspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def spy_mkstemp(*args, **kwargs):  # type: ignore[no-untyped-def]
            fd, path = real_mkstemp(*args, **kwargs)
            created.append(path)
            return fd, path

        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        artifact_id = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=artifact_id, table_name="data")],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
        )
        assert "error" not in result
        assert created, "应创建过临时文件"
        assert all(not Path(p).exists() for p in created)

    async def test_temp_files_cleaned_on_callback_error(
        self, workspace: ExtractionWorkspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def spy_mkstemp(*args, **kwargs):  # type: ignore[no-untyped-def]
            fd, path = real_mkstemp(*args, **kwargs)
            created.append(path)
            return fd, path

        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        id_a = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        id_b = await _save_csv(workspace, "t-1", CSV_B, "b.csv")
        result = await run_data_query(
            workspace,
            [TableRef(artifact_id=id_a, table_name="data_a"), TableRef(artifact_id=id_b, table_name="data_b")],
            lambda con: fetch_result(con, "SELECT * FORM data_a", limit=100),
        )
        assert "error" in result
        assert len(created) == 2
        assert all(not Path(p).exists() for p in created)

    async def test_temp_files_cleaned_when_later_artifact_invalid(
        self, workspace: ExtractionWorkspace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """第二个工件校验失败时，第一个工件产生的临时文件也被清理。"""
        created: list[str] = []
        real_mkstemp = tempfile.mkstemp

        def spy_mkstemp(*args, **kwargs):  # type: ignore[no-untyped-def]
            fd, path = real_mkstemp(*args, **kwargs)
            created.append(path)
            return fd, path

        monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
        id_a = await _save_csv(workspace, "t-1", CSV_A, "a.csv")
        result = await run_data_query(
            workspace,
            [
                TableRef(artifact_id=id_a, table_name="data_a"),
                TableRef(artifact_id="art-nonexistent", table_name="data_b"),
            ],
            lambda con: fetch_result(con, "SELECT 1", limit=100),
        )
        assert "error" in result
        assert len(created) == 1
        assert not Path(created[0]).exists()
