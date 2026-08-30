"""Artifact 存储与仓库测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest

from scaffold.infra.artifacts import Artifact, ArtifactRepository, ArtifactStorage


@pytest.fixture
def artifact_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ArtifactStorage(Path(tmpdir))


@pytest.fixture
async def artifact_repo():
    conn = await aiosqlite.connect(":memory:")
    repo = ArtifactRepository(conn)
    await repo.migrate()
    yield repo
    await conn.close()


@pytest.fixture
def sample_excel_bytes():
    return b"fake excel content for testing"


class TestArtifactStorage:
    def test_save_upload(self, artifact_storage: ArtifactStorage, sample_excel_bytes: bytes) -> None:
        artifact_id, stored_path = artifact_storage.save_upload(
            thread_id="t-001",
            filename="quote.xlsx",
            content=sample_excel_bytes,
        )

        assert artifact_id.startswith("art-")
        assert "t-001/uploads/" in stored_path
        assert stored_path.endswith("quote.xlsx")

        resolved = artifact_storage.resolve_path(stored_path)
        assert resolved.exists()
        assert resolved.read_bytes() == sample_excel_bytes

    def test_thread_isolation(self, artifact_storage: ArtifactStorage, sample_excel_bytes: bytes) -> None:
        _, path1 = artifact_storage.save_upload("t-1", "a.xlsx", sample_excel_bytes)
        _, path2 = artifact_storage.save_upload("t-2", "b.xlsx", sample_excel_bytes)

        assert "t-1/uploads/" in path1
        assert "t-2/uploads/" in path2

        abs1 = artifact_storage.resolve_path(path1)
        abs2 = artifact_storage.resolve_path(path2)
        assert abs1.parent != abs2.parent
        assert abs1.exists()
        assert abs2.exists()

    def test_read(self, artifact_storage: ArtifactStorage, sample_excel_bytes: bytes) -> None:
        _, stored_path = artifact_storage.save_upload("t-001", "quote.xlsx", sample_excel_bytes)
        content = artifact_storage.read(stored_path)
        assert content == sample_excel_bytes

    def test_read_not_found(self, artifact_storage: ArtifactStorage) -> None:
        with pytest.raises(FileNotFoundError):
            artifact_storage.read("t-001/uploads/nonexistent.xlsx")

    def test_path_traversal_blocked(self, artifact_storage: ArtifactStorage) -> None:
        with pytest.raises(ValueError):
            artifact_storage.resolve_path("../secret.txt")

    def test_write_generated_artifact(self, artifact_storage: ArtifactStorage) -> None:
        content = b"extracted data"
        artifact_id, stored_path = artifact_storage.write(
            thread_id="t-001",
            artifact_type="extraction",
            filename="result.csv",
            content=content,
        )
        assert "t-001/extractions/" in stored_path
        assert artifact_storage.read(stored_path) == content


class TestArtifactRepository:
    async def test_create_and_get(self, artifact_repo: ArtifactRepository) -> None:
        artifact = Artifact(
            artifact_id="art-001",
            thread_id="t-001",
            artifact_type="upload",
            original_name="quote.xlsx",
            stored_path="t-001/uploads/art-001-quote.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=1024,
            created_at="2025-01-01T00:00:00+00:00",
            metadata={"task_id": "ext-001"},
        )
        await artifact_repo.create(artifact)

        found = await artifact_repo.get("art-001")
        assert found is not None
        assert found.thread_id == "t-001"
        assert found.metadata["task_id"] == "ext-001"

    async def test_get_not_found(self, artifact_repo: ArtifactRepository) -> None:
        found = await artifact_repo.get("art-missing")
        assert found is None

    async def test_list_by_thread(self, artifact_repo: ArtifactRepository) -> None:
        for i in range(3):
            await artifact_repo.create(
                Artifact(
                    artifact_id=f"art-{i}",
                    thread_id="t-001",
                    artifact_type="upload",
                    stored_path=f"t-001/uploads/art-{i}.xlsx",
                    created_at=f"2025-01-0{i + 1}T00:00:00+00:00",
                )
            )
        await artifact_repo.create(
            Artifact(
                artifact_id="art-other",
                thread_id="t-002",
                artifact_type="upload",
                stored_path="t-002/uploads/art-other.xlsx",
                created_at="2025-01-01T00:00:00+00:00",
            )
        )

        t1_artifacts = await artifact_repo.list_by_thread("t-001", "default")
        assert len(t1_artifacts) == 3
        assert all(a.thread_id == "t-001" for a in t1_artifacts)

    async def test_list_by_thread_and_type(self, artifact_repo: ArtifactRepository) -> None:
        await artifact_repo.create(
            Artifact(
                artifact_id="art-upload",
                thread_id="t-001",
                artifact_type="upload",
                stored_path="t-001/uploads/u.xlsx",
                created_at="2025-01-01T00:00:00+00:00",
            )
        )
        await artifact_repo.create(
            Artifact(
                artifact_id="art-script",
                thread_id="t-001",
                artifact_type="script",
                stored_path="t-001/scripts/s.py",
                created_at="2025-01-02T00:00:00+00:00",
            )
        )

        uploads = await artifact_repo.list_by_thread("t-001", "default", "upload")
        assert len(uploads) == 1
        assert uploads[0].artifact_type == "upload"
