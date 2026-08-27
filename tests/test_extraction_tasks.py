"""抽取任务仓库测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from scaffold.infra.history.models import ExtractionTask
from scaffold.infra.history.repository import ExtractionTaskRepository, HistoryRepository


@pytest.fixture
async def task_repo():
    conn = await aiosqlite.connect(":memory:")
    history_repo = HistoryRepository(conn)
    await history_repo.migrate()
    repo = ExtractionTaskRepository(conn)
    await repo.migrate()  # 抽取任务表由 ExtractionTaskRepository 单独维护
    yield repo
    await conn.close()


class TestExtractionTaskRepository:
    async def test_create_and_get(self, task_repo: ExtractionTaskRepository) -> None:
        task = ExtractionTask(
            task_id="ext-001",
            thread_id="t-001",
            upload_artifact_id="art-001",
            status="goal_setting",
            requirements={"fields": [{"name": "amount", "type": "number"}]},
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        await task_repo.create(task)

        found = await task_repo.get("ext-001")
        assert found is not None
        assert found.thread_id == "t-001"
        assert found.status == "goal_setting"
        assert found.requirements is not None
        assert found.requirements["fields"][0]["name"] == "amount"

    async def test_update_status(self, task_repo: ExtractionTaskRepository) -> None:
        task = ExtractionTask(
            task_id="ext-002",
            thread_id="t-001",
            upload_artifact_id="art-002",
            status="goal_setting",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        await task_repo.create(task)

        task.status = "code_generated"
        task.script_artifact_id = "art-script"
        task.updated_at = "2025-01-02T00:00:00+00:00"
        updated = await task_repo.update(task)
        assert updated is True

        found = await task_repo.get("ext-002")
        assert found is not None
        assert found.status == "code_generated"
        assert found.script_artifact_id == "art-script"

    async def test_list_by_thread(self, task_repo: ExtractionTaskRepository) -> None:
        for i in range(2):
            await task_repo.create(
                ExtractionTask(
                    task_id=f"ext-t1-{i}",
                    thread_id="t-1",
                    upload_artifact_id=f"art-{i}",
                    status="goal_setting",
                    created_at=f"2025-01-0{i + 1}T00:00:00+00:00",
                    updated_at=f"2025-01-0{i + 1}T00:00:00+00:00",
                )
            )
        await task_repo.create(
            ExtractionTask(
                task_id="ext-t2-0",
                thread_id="t-2",
                upload_artifact_id="art-x",
                status="goal_setting",
                created_at="2025-01-01T00:00:00+00:00",
                updated_at="2025-01-01T00:00:00+00:00",
            )
        )

        tasks = await task_repo.list_by_thread("t-1")
        assert len(tasks) == 2
        assert all(t.thread_id == "t-1" for t in tasks)
