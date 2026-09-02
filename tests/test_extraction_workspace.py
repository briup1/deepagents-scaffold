"""ExtractionWorkspace 集成测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scaffold.infra.extraction.workspace import ExtractionWorkspace
from scaffold.infra.history.models import ExtractionTask


@pytest.fixture
def db_path() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
        return fh.name


@pytest.fixture
def artifacts_dir() -> Path:
    with tempfile.TemporaryDirectory() as tmpdir:
        return Path(tmpdir)


@pytest.fixture
async def workspace(db_path: str, artifacts_dir: Path) -> ExtractionWorkspace:
    ws = ExtractionWorkspace(db_path=db_path, artifacts_dir=artifacts_dir)
    await ws.__aenter__()
    yield ws
    await ws.__aexit__(None, None, None)


class TestExtractionWorkspace:
    async def test_create_and_get_task(self, workspace: ExtractionWorkspace) -> None:
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
            requirements={"fields": [{"name": "amount"}]},
        )
        assert task.task_id.startswith("ext-")
        assert task.status == "goal_setting"

        found = await workspace.get_task(task.task_id)
        assert found is not None
        assert found.thread_id == "t-001"
        assert found.upload_artifact_id == "art-upload-001"

    async def test_update_task(self, workspace: ExtractionWorkspace) -> None:
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
        )
        task.status = "code_generated"
        task.script_artifact_id = "art-script-001"
        updated = await workspace.update_task(task)
        assert updated is True

        found = await workspace.get_task(task.task_id)
        assert found is not None
        assert found.status == "code_generated"
        assert found.script_artifact_id == "art-script-001"
        assert found.updated_at > task.created_at

    async def test_save_and_read_artifact(self, workspace: ExtractionWorkspace) -> None:
        artifact = await workspace.save_artifact(
            thread_id="t-001",
            artifact_type="script",
            filename="extract.py",
            content=b"import pandas",
            original_name="extract.py",
            mime_type="text/x-python",
            metadata={"task_id": "ext-001"},
        )
        assert artifact.artifact_id.startswith("art-")
        assert artifact.artifact_type == "script"
        assert artifact.stored_path.startswith("t-001/scripts/")

        content = await workspace.read_artifact(artifact.artifact_id)
        assert content == b"import pandas"

    async def test_list_artifacts_by_thread(self, workspace: ExtractionWorkspace) -> None:
        await workspace.save_artifact(
            thread_id="t-001",
            artifact_type="upload",
            filename="quote.xlsx",
            content=b"fake excel",
        )
        await workspace.save_artifact(
            thread_id="t-001",
            artifact_type="script",
            filename="extract.py",
            content=b"code",
        )
        await workspace.save_artifact(
            thread_id="t-002",
            artifact_type="upload",
            filename="other.xlsx",
            content=b"other",
        )

        all_t1 = await workspace.list_artifacts("t-001")
        assert len(all_t1) == 2

        uploads = await workspace.list_artifacts("t-001", "upload")
        assert len(uploads) == 1
        assert uploads[0].artifact_type == "upload"

    async def test_context_manager_closes_connection(self, db_path: str, artifacts_dir: Path) -> None:
        async with ExtractionWorkspace(db_path=db_path, artifacts_dir=artifacts_dir) as ws:
            assert ws.get_artifact is not None
            task = await ws.create_task(thread_id="t-001", upload_artifact_id="art-001")
            assert task.task_id.startswith("ext-")


class _FakeTaskRepo:
    """只记录 update 调用的假仓库，用于状态机矩阵测试（不碰 SQLite）。"""

    def __init__(self) -> None:
        self.saved: list[ExtractionTask] = []

    async def update(self, task: ExtractionTask, user_id: str = "default") -> bool:
        self.saved.append(task)
        return True


ALL_STATUSES = ("goal_setting", "code_generated", "validating", "success", "failed")

#: 三个工具实际使用的流转声明：(目标状态, 允许的前置状态, 动作标签)
TOOL_TRANSITIONS = [
    ("code_generated", ("goal_setting",), "生成脚本"),
    ("validating", ("goal_setting", "code_generated"), "执行"),
    ("success", ("validating", "success", "failed"), "验证"),
    ("failed", ("validating", "success", "failed"), "验证"),
]


def _make_task(status: str) -> ExtractionTask:
    return ExtractionTask(
        task_id="ext-matrix",
        thread_id="t-matrix",
        upload_artifact_id="art-upload",
        status=status,  # type: ignore[arg-type]
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _make_workspace() -> tuple[ExtractionWorkspace, _FakeTaskRepo]:
    ws = ExtractionWorkspace(db_path=":memory:", artifacts_dir=Path("/tmp"))
    repo = _FakeTaskRepo()
    ws._task_repo = repo  # type: ignore[attr-defined]
    return ws, repo


class TestTaskStateMachine:
    """五个状态 × 合法/非法流转的穷尽矩阵。"""

    @pytest.mark.parametrize("status", ALL_STATUSES)
    @pytest.mark.parametrize("to,allowed,action", TOOL_TRANSITIONS)
    async def test_transition_matrix(self, status: str, to: str, allowed: tuple, action: str) -> None:
        ws, repo = _make_workspace()
        task = _make_task(status)
        error = await ws.transition_task(task, to, allowed=allowed, action=action)  # type: ignore[arg-type]
        if status in allowed:
            assert error is None
            assert task.status == to
            assert repo.saved == [task], "合法流转应持久化"
            assert task.updated_at != "2026-01-01T00:00:00+00:00", "合法流转应刷新时间戳"
        else:
            assert error is not None
            assert error == {"error": f"任务 ext-matrix 当前状态为 {status}，无法{action}"}
            assert task.status == status, "非法流转不得改变状态"
            assert repo.saved == [], "非法流转不得持久化"

    @pytest.mark.parametrize("status", ALL_STATUSES)
    def test_check_task_transition_is_pure(self, status: str) -> None:
        ws, repo = _make_workspace()
        task = _make_task(status)
        error = ws.check_task_transition(task, allowed=("goal_setting", "code_generated"), action="执行")
        if status in ("goal_setting", "code_generated"):
            assert error is None
        else:
            assert error is not None and "无法执行" in error["error"]
        assert task.status == status
        assert repo.saved == []

    @pytest.mark.parametrize("status", ALL_STATUSES)
    async def test_fail_task_response_structure(self, status: str) -> None:
        """报告内容、failed 状态、错误 dict 三者一致。"""
        ws, repo = _make_workspace()
        task = _make_task(status)
        result = await ws.fail_task(
            task,
            summary="脚本执行失败",
            rule="脚本执行成功",
            details="boom",
            suggestion="重新生成脚本",
            extra={"stderr": "boom"},
        )
        assert task.status == "failed"
        assert task.validation_report == {
            "passed": False,
            "summary": "脚本执行失败",
            "checks": [{"rule": "脚本执行成功", "status": "fail", "details": "boom"}],
            "suggestion": "重新生成脚本",
        }
        assert result == {
            "task_id": "ext-matrix",
            "error": "脚本执行失败",
            "stderr": "boom",
            "status": "failed",
        }
        assert repo.saved == [task]
        saved_report = repo.saved[0].validation_report
        assert saved_report == task.validation_report


class TestUpdateTaskScript:
    """update_task_script 方法测试。"""

    async def test_update_task_script_success(self, workspace: ExtractionWorkspace) -> None:
        """正常固化脚本到任务。"""
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
        )

        script_content = """
import pandas as pd

def extract(data: pd.DataFrame) -> pd.DataFrame:
    return data[['amount', 'date']]
"""
        result = await workspace.update_task_script(task.task_id, script_content)

        assert "error" not in result
        assert result["task_id"] == task.task_id
        assert "script_artifact_id" in result
        assert result["script_artifact_id"].startswith("art-")

        updated_task = await workspace.get_task(task.task_id)
        assert updated_task is not None
        assert updated_task.script_artifact_id == result["script_artifact_id"]

        saved_content = await workspace.read_artifact(result["script_artifact_id"])
        assert b"import pandas" in saved_content
        assert b"def extract" in saved_content

    async def test_update_task_script_syntax_error(self, workspace: ExtractionWorkspace) -> None:
        """语法错误的脚本被拒绝。"""
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
        )

        invalid_script = """
import pandas as pd

def extract(data: pd.DataFrame) -> pd.DataFrame
    return data[['amount', 'date']]
"""

        result = await workspace.update_task_script(task.task_id, invalid_script)

        assert "error" in result
        assert "语法错误" in result["error"]

        updated_task = await workspace.get_task(task.task_id)
        assert updated_task is not None
        assert updated_task.script_artifact_id is None

    async def test_update_task_script_bytes_input(self, workspace: ExtractionWorkspace) -> None:
        """支持 bytes 类型输入。"""
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
        )

        script_bytes = b"print('hello')\n"
        result = await workspace.update_task_script(task.task_id, script_bytes)

        assert "error" not in result
        assert result["script_artifact_id"].startswith("art-")

    async def test_update_task_script_nonexistent_task(self, workspace: ExtractionWorkspace) -> None:
        """不存在的任务返回错误。"""
        result = await workspace.update_task_script("ext-nonexistent", "print('hello')")

        assert "error" in result
        assert "不存在" in result["error"]

    async def test_update_task_script_overwrites_existing(self, workspace: ExtractionWorkspace) -> None:
        """覆盖已有脚本。"""
        task = await workspace.create_task(
            thread_id="t-001",
            upload_artifact_id="art-upload-001",
        )

        first_script = "print('first')\n"
        result1 = await workspace.update_task_script(task.task_id, first_script)
        assert "error" not in result1
        first_artifact_id = result1["script_artifact_id"]

        second_script = "print('second')\n"
        result2 = await workspace.update_task_script(task.task_id, second_script)
        assert "error" not in result2
        second_artifact_id = result2["script_artifact_id"]

        assert second_artifact_id != first_artifact_id

        updated_task = await workspace.get_task(task.task_id)
        assert updated_task.script_artifact_id == second_artifact_id

        saved_content = await workspace.read_artifact(second_artifact_id)
        assert saved_content == b"print('second')\n"
