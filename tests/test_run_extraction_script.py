"""run_extraction_script 工具测试。"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from scaffold.plugins.tools.run_extraction_script import run_extraction_script
from scaffold.plugins.tools.generate_extraction_code import generate_extraction_code


def _make_excel_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Quotes"
    ws.append(["carrier", "pol", "pod", "container_type", "amount"])
    ws.append(["MSC", "SHANGHAI", "LOS ANGELES", "40HQ", 3200])
    ws.append(["COSCO", "SHANGHAI", "LOS ANGELES", "20GP", 1800])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class TestRunExtractionScript:
    @pytest.fixture
    async def task_id(self, client: TestClient) -> str:
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-run-script"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 200
        upload_artifact_id = upload_response.json()["artifact_id"]

        gen_result = await generate_extraction_code(
            upload_artifact_id=upload_artifact_id,
            requirements={
                "description": "抽取运价",
                "fields": [
                    {"name": "carrier", "required": True},
                    {"name": "pol", "required": True},
                    {"name": "pod", "required": True},
                    {"name": "container_type", "required": True},
                    {"name": "amount", "type": "number", "required": True},
                ],
            },
        )
        assert "error" not in gen_result
        return gen_result["task_id"]

    async def test_run_extraction_script_iterate_success(self, task_id: str, client: TestClient) -> None:
        """迭代模式正常执行，返回完整结果。"""
        result = await run_extraction_script(task_id=task_id, mode="iterate")

        assert "error" not in result
        assert result["task_id"] == task_id
        assert result["exit_code"] == 0
        assert "stdout" in result
        assert "stderr" in result
        assert "output_files" in result
        assert "result_preview" in result
        assert "run_count" in result
        assert "execution_time_ms" in result

        # 验证结果预览包含列名和行数据
        preview = result["result_preview"]
        assert preview["has_output"] is True
        assert "extracted.csv" in preview["files"]
        assert "columns" in preview
        assert "carrier" in preview["columns"]
        assert "amount" in preview["columns"]
        assert len(preview["rows"]) == 2
        assert preview["rows"][0]["carrier"] == "MSC"
        assert preview["rows"][1]["carrier"] == "COSCO"

        # 第一次运行 run_count 应为 1
        assert result["run_count"] == 1

    async def test_run_extraction_script_run_count_increments(self, task_id: str) -> None:
        """多次调用时 run_count 累计增加。"""
        # 第一次运行
        result1 = await run_extraction_script(task_id=task_id, mode="iterate")
        assert result1["run_count"] == 1

        # 第二次运行
        result2 = await run_extraction_script(task_id=task_id, mode="iterate")
        assert result2["run_count"] == 2

        # 第三次运行
        result3 = await run_extraction_script(task_id=task_id, mode="iterate")
        assert result3["run_count"] == 3

    async def test_run_extraction_script_max_runs_rejected(self, task_id: str) -> None:
        """达到 8 次后拒绝执行。"""
        # 运行 8 次
        for i in range(8):
            result = await run_extraction_script(task_id=task_id, mode="iterate")
            assert result["run_count"] == i + 1

        # 第 9 次应该被拒绝
        result = await run_extraction_script(task_id=task_id, mode="iterate")
        assert "error" in result
        assert "最大运行次数限制" in result["error"]
        assert result["run_count"] == 8
        assert result["max_runs"] == 8

    async def test_run_extraction_script_invalid_mode(self, task_id: str) -> None:
        """非 iterate 模式返回错误。"""
        result = await run_extraction_script(task_id=task_id, mode="invalid")
        assert "error" in result
        assert "不支持的模式" in result["error"]

    async def test_run_extraction_script_missing_task(self) -> None:
        """不存在的任务返回错误。"""
        result = await run_extraction_script(task_id="ext-nonexistent", mode="iterate")
        assert "error" in result
        assert "不存在" in result["error"]

    async def test_run_extraction_script_missing_script(self, client: TestClient) -> None:
        """未生成脚本的任务返回错误。"""
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-no-script"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 200
        upload_artifact_id = upload_response.json()["artifact_id"]

        # 直接创建任务但不生成脚本（通过 generate_extraction_code 但不调用）
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        async with get_extraction_workspace() as ws:
            task = await ws.create_task(
                thread_id="t-no-script",
                upload_artifact_id=upload_artifact_id,
                requirements={"description": "test"},
            )
            task_id = task.task_id

        result = await run_extraction_script(task_id=task_id, mode="iterate")
        assert "error" in result
        assert "尚未生成脚本" in result["error"]

    async def test_run_extraction_script_script_error(self, task_id: str, client: TestClient) -> None:
        """脚本执行失败时返回 stderr 和非零 exit_code，但不改变任务状态。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        # 先获取当前脚本
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id)

        # 修改脚本使其失败并输出内容
        bad_script = b"import sys\nprint('stdout message')\nprint('stderr message', file=sys.stderr)\nsys.exit(1)\n"

        async with get_extraction_workspace() as ws:
            # 覆盖脚本工件
            artifact = await ws.save_artifact(
                thread_id=task.thread_id,
                artifact_type="script",
                filename="extract.py",
                content=bad_script,
                original_name="extract.py",
                mime_type="text/x-python",
                metadata={"task_id": task_id},
            )
            task.script_artifact_id = artifact.artifact_id
            await ws.update_task(task)

        # 执行应该失败但返回结果
        result = await run_extraction_script(task_id=task_id, mode="iterate")

        assert "error" not in result  # 工具本身不报错，返回执行结果
        assert result["exit_code"] != 0
        assert "stdout message" in result["stdout"]
        assert "stderr message" in result["stderr"]
        # run_count 仍然增加
        assert result["run_count"] >= 1


class TestRunExtractionScriptFinalize:
    """收口模式测试。"""

    @pytest.fixture
    async def task_id_finalize(self, client: TestClient) -> str:
        """创建一个处于 code_generated 状态的任务，用于测试 finalize 模式。"""
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-finalize"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 200
        upload_artifact_id = upload_response.json()["artifact_id"]

        gen_result = await generate_extraction_code(
            upload_artifact_id=upload_artifact_id,
            requirements={
                "description": "抽取运价",
                "fields": [
                    {"name": "carrier", "required": True},
                    {"name": "pol", "required": True},
                    {"name": "pod", "required": True},
                    {"name": "container_type", "required": True},
                    {"name": "amount", "type": "number", "required": True},
                ],
            },
        )
        assert "error" not in gen_result
        task_id = gen_result["task_id"]

        # 显式将任务状态设为 code_generated（generate_extraction_code 可能设为 goal_setting）
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id)
            task.status = "code_generated"
            await ws.update_task(task)

        return task_id

    async def test_run_extraction_script_finalize_success(self, task_id_finalize: str) -> None:
        """收口模式正常执行，返回完整结果并迁移状态。"""
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")

        assert "error" not in result
        assert result["task_id"] == task_id_finalize
        assert result["exit_code"] == 0
        assert "stdout" in result
        assert "stderr" in result
        assert "extracted_artifact_id" in result
        assert "result_preview" in result
        assert "status" in result
        assert "execution_time_ms" in result

        # 验证状态已迁移到 validating
        assert result["status"] == "validating"

        # 验证结果预览包含列名和行数据
        preview = result["result_preview"]
        assert preview["has_output"] is True
        assert "extracted.csv" in preview["files"]
        assert "columns" in preview
        assert "carrier" in preview["columns"]
        assert "amount" in preview["columns"]
        assert len(preview["rows"]) == 2
        assert preview["rows"][0]["carrier"] == "MSC"
        assert preview["rows"][1]["carrier"] == "COSCO"

        # 验证 extracted_artifact_id 有效
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        async with get_extraction_workspace() as ws:
            artifact = await ws.get_artifact(result["extracted_artifact_id"])
            assert artifact is not None
            assert artifact.artifact_type == "extraction"
            content = await ws.read_artifact(result["extracted_artifact_id"])
            assert b"MSC" in content
            assert b"COSCO" in content

    async def test_run_extraction_script_finalize_state_transition(self, task_id_finalize: str) -> None:
        """收口模式迁移任务状态 code_generated -> validating。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        # 执行前验证状态
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            assert task.status == "code_generated"

        # 执行收口模式
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")
        assert "error" not in result
        assert result["status"] == "validating"

        # 执行后验证状态
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            assert task.status == "validating"
            assert task.extracted_artifact_id == result["extracted_artifact_id"]

    async def test_run_extraction_script_finalize_artifact_persisted(self, task_id_finalize: str) -> None:
        """收口模式落盘 extraction 工件并挂接 task.extracted_artifact_id。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")
        assert "error" not in result

        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            # 验证任务关联了 extraction 工件
            assert task.extracted_artifact_id is not None
            assert task.extracted_artifact_id == result["extracted_artifact_id"]

            # 验证工件内容
            artifact = await ws.get_artifact(task.extracted_artifact_id)
            assert artifact is not None
            assert artifact.artifact_type == "extraction"
            content = await ws.read_artifact(task.extracted_artifact_id)
            assert b"MSC" in content
            assert b"COSCO" in content
            assert b"carrier" in content
            assert b"pol" in content

    async def test_run_extraction_script_finalize_not_increment_run_count(self, task_id_finalize: str) -> None:
        """收口模式不计入 run_count。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        # 获取初始 run_count
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            initial_run_count = task.run_count

        # 执行收口模式
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")
        assert "error" not in result

        # 验证 run_count 未变
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            assert task.run_count == initial_run_count

    async def test_run_extraction_script_finalize_after_max_iterate(self, task_id_finalize: str) -> None:
        """迭代模式达到 8 次后，收口模式仍可执行。"""

        # 先运行 8 次迭代模式
        for i in range(8):
            result = await run_extraction_script(task_id=task_id_finalize, mode="iterate")
            assert "error" not in result
            assert result["run_count"] == i + 1

        # 第 9 次迭代应该被拒绝
        result = await run_extraction_script(task_id=task_id_finalize, mode="iterate")
        assert "error" in result
        assert "最大运行次数限制" in result["error"]

        # 但收口模式仍可执行
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")
        assert "error" not in result
        assert result["status"] == "validating"

    async def test_run_extraction_script_finalize_wrong_state(self, client: TestClient) -> None:
        """任务状态不是 code_generated 时，收口模式返回错误。"""
        excel_bytes = _make_excel_bytes()
        upload_response = client.post(
            "/api/files/upload",
            data={"thread_id": "t-wrong-state"},
            files={
                "file": (
                    "quote.xlsx",
                    io.BytesIO(excel_bytes),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert upload_response.status_code == 200
        upload_artifact_id = upload_response.json()["artifact_id"]

        gen_result = await generate_extraction_code(
            upload_artifact_id=upload_artifact_id,
            requirements={"description": "test", "fields": []},
        )
        assert "error" not in gen_result
        task_id = gen_result["task_id"]

        # 将任务状态改为 validating（不是 code_generated）
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id)
            task.status = "validating"
            await ws.update_task(task)

        # 此时任务状态为 validating，尝试 finalize 应该失败
        result = await run_extraction_script(task_id=task_id, mode="finalize")
        assert "error" in result
        assert "当前状态为 validating" in result["error"]

    async def test_run_extraction_script_finalize_script_error(self, task_id_finalize: str) -> None:
        """收口模式下脚本执行失败时返回错误并置任务为 failed。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        # 修改脚本使其失败
        bad_script = b"import sys\nprint('stdout message')\nprint('stderr message', file=sys.stderr)\nsys.exit(1)\n"

        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            artifact = await ws.save_artifact(
                thread_id=task.thread_id,
                artifact_type="script",
                filename="extract.py",
                content=bad_script,
                original_name="extract.py",
                mime_type="text/x-python",
                metadata={"task_id": task_id_finalize},
            )
            task.script_artifact_id = artifact.artifact_id
            await ws.update_task(task)

        # 执行收口模式
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")

        assert "error" in result
        assert "脚本执行失败" in result["error"]
        assert "stderr message" in result.get("stderr", "")
        assert "stdout message" in result.get("stdout", "")

        # 验证任务状态为 failed
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            assert task.status == "failed"

    async def test_run_extraction_script_finalize_no_csv_output(self, task_id_finalize: str) -> None:
        """收口模式下脚本未输出 CSV 时返回错误并置任务为 failed。"""
        from scaffold.plugins.tools._extraction_common import get_extraction_workspace

        # 修改脚本使其不输出 CSV
        bad_script = b"print('hello')\n"

        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            artifact = await ws.save_artifact(
                thread_id=task.thread_id,
                artifact_type="script",
                filename="extract.py",
                content=bad_script,
                original_name="extract.py",
                mime_type="text/x-python",
                metadata={"task_id": task_id_finalize},
            )
            task.script_artifact_id = artifact.artifact_id
            await ws.update_task(task)

        # 执行收口模式
        result = await run_extraction_script(task_id=task_id_finalize, mode="finalize")

        assert "error" in result
        assert "脚本未输出 CSV 文件" in result["error"]

        # 验证任务状态为 failed
        async with get_extraction_workspace() as ws:
            task = await ws.get_task(task_id_finalize)
            assert task.status == "failed"
