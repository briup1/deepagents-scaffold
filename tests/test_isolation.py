"""用户级数据隔离测试（R1-2 / R1-3 / R1-4）。

测试环境 auth 未启用（config.test.yaml），HTTP 层请求者一律为 "default"，
因此 alice 的数据通过仓储层直接播种，HTTP 层断言 default 用户访问被拒。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from scaffold.infra.artifacts import Artifact, ArtifactRepository, ArtifactStorage
from scaffold.infra.context import user_id_ctx
from scaffold.infra.extraction.workspace import ExtractionWorkspace
from scaffold.infra.history.models import ExtractionTask
from scaffold.infra.history.repository import ExtractionTaskRepository, HistoryRepository


# ---------------------------------------------------------------------------
# REST 层隔离（R1-2）
# ---------------------------------------------------------------------------


class TestRestIsolation:
    @staticmethod
    def _seed_alice(client: TestClient) -> tuple[str, str]:
        """以 alice 身份直接在仓储层播种一个会话 + 一个工件 + 一个抽取任务，返回 (thread_id, artifact_id)。"""
        import uuid

        suffix = uuid.uuid4().hex[:8]
        thread_id = f"alice-thread-{suffix}"
        task_id = f"alice-task-{suffix}"

        async def _seed() -> str:
            history_repo: HistoryRepository = client.app.state.history_repo
            await history_repo.ensure_thread(thread_id, "default", "alice")

            storage = ArtifactStorage(Path("./tmp_tests/data/artifacts"))
            artifact_id, stored_path = storage.save_upload(
                thread_id=thread_id, filename="alice.xlsx", content=b"fake-xlsx"
            )
            artifact_repo: ArtifactRepository = client.app.state.artifact_repo
            await artifact_repo.create(
                Artifact(
                    artifact_id=artifact_id,
                    thread_id=thread_id,
                    user_id="alice",
                    artifact_type="upload",
                    original_name="alice.xlsx",
                    stored_path=stored_path,
                    mime_type="application/vnd.ms-excel",
                    size_bytes=9,
                    created_at="2026-08-30T00:00:00+00:00",
                )
            )
            task_repo = ExtractionTaskRepository(history_repo._conn)
            await task_repo.migrate()
            await task_repo.create(
                ExtractionTask(
                    task_id=task_id,
                    thread_id=thread_id,
                    user_id="alice",
                    upload_artifact_id=artifact_id,
                    status="success",
                    created_at="2026-08-30T00:00:00+00:00",
                    updated_at="2026-08-30T00:00:00+00:00",
                )
            )
            return artifact_id

        return thread_id, asyncio.run(_seed())

    def test_cross_user_thread_access_forbidden(self, client: TestClient):
        tid, _ = self._seed_alice(client)
        assert client.get(f"/api/threads/{tid}").status_code == 403
        assert client.get(f"/api/threads/{tid}/messages").status_code == 403
        assert client.delete(f"/api/threads/{tid}").status_code == 403

    def test_cross_user_list_shows_nothing(self, client: TestClient):
        tid, _ = self._seed_alice(client)
        resp = client.get("/api/threads/")
        assert resp.status_code == 200
        assert all(t["thread_id"] != tid for t in resp.json()["threads"])

        resp = client.get("/api/files/", params={"thread_id": tid})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_cross_user_artifact_access_forbidden(self, client: TestClient):
        _, aid = self._seed_alice(client)
        assert client.get(f"/api/files/{aid}").status_code == 403
        assert client.get(f"/api/files/{aid}/download").status_code == 403

    def test_cross_user_upload_to_others_thread_forbidden(self, client: TestClient):
        tid, _ = self._seed_alice(client)
        resp = client.post(
            "/api/files/upload",
            data={"thread_id": tid},
            files={"file": ("evil.xlsx", b"fake", "application/vnd.ms-excel")},
        )
        assert resp.status_code == 403

    def test_own_resources_unaffected(self, client: TestClient):
        """default 用户创建自己的会话与文件，正常工作。"""
        resp = client.post("/api/threads/", json={"agent_id": "default"})
        assert resp.status_code == 200
        tid = resp.json()["thread_id"]
        assert client.get(f"/api/threads/{tid}").status_code == 200
        resp = client.post(
            "/api/files/upload",
            data={"thread_id": tid},
            files={"file": ("mine.xlsx", b"fake", "application/vnd.ms-excel")},
        )
        assert resp.status_code == 200
        aid = resp.json()["artifact_id"]
        assert client.get(f"/api/files/{aid}/download").status_code == 200


# ---------------------------------------------------------------------------
# 仓储层隔离（R1-3 数据面）
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn(tmp_path):
    async with aiosqlite.connect(str(tmp_path / "test.db")) as c:
        # extraction_tasks 表由独立 migrate 创建，delete_thread 级联删除依赖它
        await HistoryRepository(c).migrate()
        await ExtractionTaskRepository(c).migrate()
        yield c


class TestRepoIsolation:
    async def test_history_repo_user_filtering(self, conn):
        repo = HistoryRepository(conn)
        await repo.ensure_thread("t-a", "default", "alice")
        await repo.ensure_thread("t-b", "default", "bob")

        threads_a, total_a = await repo.list_threads("alice")
        assert total_a == 1 and threads_a[0].thread_id == "t-a"

        # 属主信息可读
        row = await repo.get_thread("t-a")
        assert row is not None and row["user_id"] == "alice"

        # bob 删不了 alice 的会话
        assert await repo.delete_thread("t-a", "bob") is False
        assert await repo.get_thread("t-a") is not None
        # alice 可以删
        assert await repo.delete_thread("t-a", "alice") is True

    async def test_ensure_thread_does_not_change_owner(self, conn):
        repo = HistoryRepository(conn)
        await repo.migrate()
        await repo.ensure_thread("t-a", "default", "alice")
        await repo.ensure_thread("t-a", "default", "bob")  # bob 撞同 id
        row = await repo.get_thread("t-a")
        assert row["user_id"] == "alice"  # 属主不变

    async def test_artifact_repo_user_filtering(self, conn):
        from scaffold.infra.artifacts import Artifact

        repo = ArtifactRepository(conn)
        await repo.migrate()
        for aid, owner in (("art-a", "alice"), ("art-b", "bob")):
            await repo.create(
                Artifact(
                    artifact_id=aid,
                    thread_id="t-1",
                    user_id=owner,
                    artifact_type="upload",
                    stored_path=f"t-1/{aid}.xlsx",
                    created_at="2026-08-30T00:00:00+00:00",
                )
            )
        alice_arts = await repo.list_by_thread("t-1", "alice")
        assert [a.artifact_id for a in alice_arts] == ["art-a"]
        assert await repo.delete("art-a", "bob") is False
        assert await repo.delete("art-a", "alice") is True

    async def test_task_repo_user_filtering(self, conn):
        repo = ExtractionTaskRepository(conn)
        await repo.migrate()
        for tid, owner in (("ext-a", "alice"), ("ext-b", "bob")):
            await repo.create(
                ExtractionTask(
                    task_id=tid,
                    thread_id="t-1",
                    user_id=owner,
                    upload_artifact_id="up-1",
                    status="goal_setting",
                    created_at="2026-08-30T00:00:00+00:00",
                    updated_at="2026-08-30T00:00:00+00:00",
                )
            )
        tasks = await repo.list_by_thread("t-1", "alice")
        assert [t.task_id for t in tasks] == ["ext-a"]


# ---------------------------------------------------------------------------
# 工具层隔离（R1-3 工具面，经 user_id_ctx）
# ---------------------------------------------------------------------------


class TestWorkspaceIsolation:
    async def _workspace(self, tmp_path) -> ExtractionWorkspace:
        ws = ExtractionWorkspace(tmp_path / "ws.db", tmp_path / "artifacts")
        await ws.__aenter__()
        return ws

    async def test_cross_user_task_invisible_and_logged(self, tmp_path, caplog):
        import logging

        ws = await self._workspace(tmp_path)
        token = user_id_ctx.set("alice")
        task = await ws.create_task("t-1", "up-1")
        user_id_ctx.reset(token)

        token = user_id_ctx.set("bob")
        try:
            with caplog.at_level(logging.WARNING):
                assert await ws.get_task(task.task_id) is None
            assert "cross-user access denied" in caplog.text
            assert "alice" in caplog.text and "bob" in caplog.text
            # 列表同样不可见
            assert await ws.list_tasks("t-1") == []
        finally:
            user_id_ctx.reset(token)
            await ws.__aexit__(None, None, None)

    async def test_cross_user_artifact_invisible(self, tmp_path):
        ws = await self._workspace(tmp_path)
        token = user_id_ctx.set("alice")
        artifact = await ws.save_artifact("t-1", "upload", "a.xlsx", b"data")
        user_id_ctx.reset(token)

        token = user_id_ctx.set("bob")
        try:
            assert await ws.get_artifact(artifact.artifact_id) is None
            assert await ws.list_artifacts("t-1") == []
        finally:
            user_id_ctx.reset(token)
            await ws.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# 旧版 schema 守卫（R1-4：存量数据不迁移）
# ---------------------------------------------------------------------------


class TestLegacySchemaGuard:
    async def test_old_threads_table_raises_readable_error(self, tmp_path):
        db = str(tmp_path / "legacy.db")
        async with aiosqlite.connect(db) as c:
            await c.execute(
                "CREATE TABLE threads (thread_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, "
                "title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            await c.commit()

        async with aiosqlite.connect(db) as c:
            repo = HistoryRepository(c)
            with pytest.raises(RuntimeError, match="删除 data/"):
                await repo.migrate()

    async def test_fresh_db_migrates_cleanly(self, tmp_path):
        async with aiosqlite.connect(str(tmp_path / "fresh.db")) as c:
            repo = HistoryRepository(c)
            await repo.migrate()
            await repo.ensure_thread("t-1", "default", "alice")
            assert (await repo.get_thread("t-1"))["user_id"] == "alice"
