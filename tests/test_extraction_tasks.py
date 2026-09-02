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


@pytest.fixture
async def legacy_task_repo():
    """创建一个没有 run_count 列的旧版 extraction_tasks 表，用于测试迁移。"""
    conn = await aiosqlite.connect(":memory:")
    history_repo = HistoryRepository(conn)
    await history_repo.migrate()
    repo = ExtractionTaskRepository(conn)
    await repo.migrate()  # 先创建标准表（含 run_count）
    # 然后手动删除并重建旧版 schema（无 run_count）
    await conn.execute("DROP TABLE extraction_tasks")
    await conn.executescript(
        """
        CREATE TABLE extraction_tasks (
            task_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            upload_artifact_id TEXT NOT NULL,
            status TEXT NOT NULL,
            requirements TEXT,
            script_artifact_id TEXT,
            extracted_artifact_id TEXT,
            validation_report TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id) ON DELETE CASCADE,
            FOREIGN KEY (upload_artifact_id) REFERENCES artifacts(artifact_id),
            FOREIGN KEY (script_artifact_id) REFERENCES artifacts(artifact_id),
            FOREIGN KEY (extracted_artifact_id) REFERENCES artifacts(artifact_id)
        );
        CREATE INDEX idx_extraction_tasks_thread_id ON extraction_tasks(thread_id);
        CREATE INDEX idx_extraction_tasks_user_id ON extraction_tasks(user_id);
        """
    )
    await conn.commit()
    # 现在再次调用 migrate，应该触发迁移添加 run_count 列
    await repo.migrate()
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

        found = await task_repo.get("ext-001", "default")
        assert found is not None
        assert found.thread_id == "t-001"
        assert found.status == "goal_setting"
        assert found.requirements is not None
        assert found.requirements["fields"][0]["name"] == "amount"
        assert found.run_count == 0  # 默认值为 0

    async def test_create_with_run_count(self, task_repo: ExtractionTaskRepository) -> None:
        """测试创建时指定 run_count。"""
        task = ExtractionTask(
            task_id="ext-002",
            thread_id="t-001",
            upload_artifact_id="art-002",
            status="goal_setting",
            run_count=3,
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        await task_repo.create(task)

        found = await task_repo.get("ext-002", "default")
        assert found is not None
        assert found.run_count == 3

    async def test_update_status(self, task_repo: ExtractionTaskRepository) -> None:
        task = ExtractionTask(
            task_id="ext-003",
            thread_id="t-001",
            upload_artifact_id="art-003",
            status="goal_setting",
            created_at="2025-01-01T00:00:00+00:00",
            updated_at="2025-01-01T00:00:00+00:00",
        )
        await task_repo.create(task)

        task.status = "code_generated"
        task.script_artifact_id = "art-script"
        task.run_count = 1
        task.updated_at = "2025-01-02T00:00:00+00:00"
        updated = await task_repo.update(task, "default")
        assert updated is True

        found = await task_repo.get("ext-003", "default")
        assert found is not None
        assert found.status == "code_generated"
        assert found.script_artifact_id == "art-script"
        assert found.run_count == 1

    async def test_list_by_thread(self, task_repo: ExtractionTaskRepository) -> None:
        for i in range(2):
            await task_repo.create(
                ExtractionTask(
                    task_id=f"ext-t1-{i}",
                    thread_id="t-1",
                    upload_artifact_id=f"art-{i}",
                    status="goal_setting",
                    run_count=i,
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

        tasks = await task_repo.list_by_thread("t-1", "default")
        assert len(tasks) == 2
        assert all(t.thread_id == "t-1" for t in tasks)
        assert tasks[0].run_count == 1  # 按 created_at DESC 排序，ext-t1-1 排在前面
        assert tasks[1].run_count == 0

    async def test_legacy_migration_adds_run_count(self, legacy_task_repo: ExtractionTaskRepository) -> None:
        """测试旧版数据库（无 run_count 列）迁移后可正常读写。"""
        # 先插入一条旧数据（模拟存量库）
        await legacy_task_repo._conn.execute(
            """
            INSERT INTO extraction_tasks
            (task_id, thread_id, user_id, upload_artifact_id, status, requirements,
             script_artifact_id, extracted_artifact_id, validation_report, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ext-legacy-001",
                "t-legacy",
                "default",
                "art-legacy",
                "success",
                "{}",
                "art-script-legacy",
                "art-extracted-legacy",
                "{}",
                "2025-01-01T00:00:00+00:00",
                "2025-01-01T00:00:00+00:00",
            ),
        )
        await legacy_task_repo._conn.commit()

        # 迁移已在 fixture 中执行，现在验证 run_count 列存在且默认值为 0
        found = await legacy_task_repo.get("ext-legacy-001", "default")
        assert found is not None
        assert found.run_count == 0  # 旧数据迁移后 run_count 默认为 0

        # 验证可更新 run_count
        found.run_count = 5
        found.updated_at = "2025-01-02T00:00:00+00:00"
        updated = await legacy_task_repo.update(found, "default")
        assert updated is True

        found2 = await legacy_task_repo.get("ext-legacy-001", "default")
        assert found2 is not None
        assert found2.run_count == 5

        # 验证新建任务也能正常工作
        new_task = ExtractionTask(
            task_id="ext-new-001",
            thread_id="t-legacy",
            upload_artifact_id="art-new",
            status="goal_setting",
            run_count=2,
            created_at="2025-01-03T00:00:00+00:00",
            updated_at="2025-01-03T00:00:00+00:00",
        )
        await legacy_task_repo.create(new_task)
        found3 = await legacy_task_repo.get("ext-new-001", "default")
        assert found3 is not None
        assert found3.run_count == 2
