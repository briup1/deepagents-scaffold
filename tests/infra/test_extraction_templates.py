"""抽取模板生命周期与用户隔离测试（R4）。"""

from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path

import aiosqlite
import openpyxl
import pytest

from scaffold.infra.context import user_id_ctx
from scaffold.infra.extraction.fingerprint import compute_fingerprint
from scaffold.infra.extraction.workspace import ExtractionWorkspace
from scaffold.infra.history.models import ExtractionTask, ExtractionTemplate
from scaffold.infra.history.repository import ExtractionTemplateRepository, HistoryRepository


def make_xlsx(sheet: str, headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


QUOTE_XLSX = make_xlsx("报价单", ["品名", "单价", "数量"], [["螺丝", 1.2, 100], ["螺母", 0.3, 500]])
OTHER_XLSX = make_xlsx("报价单", ["品名", "备注"], [["螺丝", "A类"]])


# ---------------------------------------------------------------------------
# 指纹
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_signature_stable_for_same_structure(self) -> None:
        a = compute_fingerprint(QUOTE_XLSX)
        b = compute_fingerprint(QUOTE_XLSX)
        assert a["signature"] == b["signature"]
        assert len(a["signature"]) == 16
        assert a["sheets"] == ["报价单"]
        assert a["columns"]["报价单"] == ["品名", "单价", "数量"]

    def test_different_columns_different_signature(self) -> None:
        a = compute_fingerprint(QUOTE_XLSX)
        b = compute_fingerprint(OTHER_XLSX)
        assert a["signature"] != b["signature"]

    def test_column_order_matters(self) -> None:
        a = compute_fingerprint(make_xlsx("s", ["a", "b"], []))
        b = compute_fingerprint(make_xlsx("s", ["b", "a"], []))
        assert a["signature"] != b["signature"]


# ---------------------------------------------------------------------------
# 仓储层
# ---------------------------------------------------------------------------


@pytest.fixture
async def template_repo():
    conn = await aiosqlite.connect(":memory:")
    await HistoryRepository(conn).migrate()
    repo = ExtractionTemplateRepository(conn)
    await repo.migrate()
    yield repo
    await conn.close()


def _template(tid: str, user: str = "alice", sig: str = "sig-1") -> ExtractionTemplate:
    return ExtractionTemplate(
        template_id=tid,
        user_id=user,
        name=f"模板{tid}",
        goal={"fields": [{"name": "amount"}]},
        script="print('hi')",
        fingerprint={"sheets": ["s"], "columns": {"s": ["a"]}, "signature": sig},
        source_file_name="quote.xlsx",
        created_at="2026-08-30T00:00:00+00:00",
        updated_at="2026-08-30T00:00:00+00:00",
    )


class TestTemplateRepository:
    async def test_crud_roundtrip(self, template_repo: ExtractionTemplateRepository) -> None:
        await template_repo.create(_template("tpl-1"))
        found = await template_repo.get("tpl-1", "alice")
        assert found is not None
        assert found.name == "模板tpl-1"
        assert found.goal["fields"][0]["name"] == "amount"

        assert await template_repo.rename("tpl-1", "alice", "新名字", "2026-08-31T00:00:00+00:00") is True
        assert (await template_repo.get("tpl-1", "alice")).name == "新名字"

        assert await template_repo.delete("tpl-1", "alice") is True
        assert await template_repo.get("tpl-1", "alice") is None

    async def test_find_by_signature_returns_latest(self, template_repo: ExtractionTemplateRepository) -> None:
        await template_repo.create(_template("tpl-old", sig="sig-x", user="alice"))
        await template_repo.create(_template("tpl-new", sig="sig-x", user="alice"))
        found = await template_repo.find_by_signature("sig-x", "alice")
        assert found.template_id == "tpl-new"

    async def test_user_isolation(self, template_repo: ExtractionTemplateRepository) -> None:
        await template_repo.create(_template("tpl-a", user="alice"))
        assert await template_repo.get("tpl-a", "bob") is None
        assert await template_repo.find_by_signature("sig-1", "bob") is None
        assert await template_repo.list_by_user("bob") == []
        assert await template_repo.rename("tpl-a", "bob", "x", "2026-08-31T00:00:00+00:00") is False
        assert await template_repo.delete("tpl-a", "bob") is False
        assert (await template_repo.get("tpl-a", "alice")).name == "模板tpl-a"


# ---------------------------------------------------------------------------
# Workspace 工具层（user_id_ctx）
# ---------------------------------------------------------------------------


@pytest.fixture
async def ws() -> ExtractionWorkspace:
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    w = ExtractionWorkspace(db_path=db.name, artifacts_dir=Path(tempfile.mkdtemp()))
    await w.__aenter__()
    yield w
    await w.__aexit__(None, None, None)


def _run_as(user: str):
    return user_id_ctx.set(user)


class TestWorkspaceTemplates:
    async def _success_task(self, ws: ExtractionWorkspace, user: str = "alice") -> ExtractionTask:
        token = _run_as(user)
        try:
            upload = await ws.save_artifact("t-1", "upload", "quote.xlsx", QUOTE_XLSX, original_name="quote.xlsx")
            script = await ws.save_artifact("t-1", "script", "extract.py", b"print('ok')", original_name="extract.py")
            task = await ws.create_task("t-1", upload.artifact_id)
            task.script_artifact_id = script.artifact_id
            task.requirements = {"fields": [{"name": "品名"}]}
            task.status = "success"
            await ws.update_task(task)
            return task
        finally:
            user_id_ctx.reset(token)

    async def test_save_requires_success(self, ws: ExtractionWorkspace) -> None:
        token = _run_as("alice")
        try:
            task = await self._success_task(ws)
            task.status = "code_generated"
            await ws.update_task(task)
            result = await ws.save_template_from_task(task.task_id, "报价单模板")
            assert "error" in result and "success" in result["error"]
        finally:
            user_id_ctx.reset(token)

    async def test_save_and_match_roundtrip(self, ws: ExtractionWorkspace) -> None:
        token = _run_as("alice")
        try:
            task = await self._success_task(ws)
            saved = await ws.save_template_from_task(task.task_id, "报价单模板")
            assert "template_id" in saved

            # 同结构文件命中
            new_upload = await ws.save_artifact("t-2", "upload", "quote2.xlsx", QUOTE_XLSX, original_name="quote2.xlsx")
            hit = await ws.match_template(new_upload.artifact_id)
            assert hit["matched"] is True
            assert hit["template"]["name"] == "报价单模板"
            assert "script" in hit["template"]

            # 列名不同的文件不命中
            other = await ws.save_artifact("t-2", "upload", "other.xlsx", OTHER_XLSX, original_name="other.xlsx")
            miss = await ws.match_template(other.artifact_id)
            assert miss["matched"] is False
            assert "reason" in miss

            # 列表可见
            templates = await ws.list_templates()
            assert len(templates) == 1 and templates[0]["template_id"] == saved["template_id"]
        finally:
            user_id_ctx.reset(token)

    async def test_cross_user_invisible(self, ws: ExtractionWorkspace) -> None:
        token = _run_as("alice")
        try:
            task = await self._success_task(ws)
            saved = await ws.save_template_from_task(task.task_id, "alice模板")
        finally:
            user_id_ctx.reset(token)

        token = _run_as("bob")
        try:
            assert await ws.list_templates() == []
            assert "error" in await ws.rename_template(saved["template_id"], "hack")
            assert "error" in await ws.delete_template(saved["template_id"])
            new_upload = await ws.save_artifact("t-9", "upload", "q.xlsx", QUOTE_XLSX, original_name="q.xlsx")
            miss = await ws.match_template(new_upload.artifact_id)
            assert miss["matched"] is False  # 同结构也看不到 alice 的模板
        finally:
            user_id_ctx.reset(token)

        # alice 的模板未被 bob 动过
        token = _run_as("alice")
        try:
            assert len(await ws.list_templates()) == 1
        finally:
            user_id_ctx.reset(token)
