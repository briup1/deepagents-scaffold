"""ExtractionWorkspace 集成测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scaffold.infra.extraction.workspace import ExtractionWorkspace


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
