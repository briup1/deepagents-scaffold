"""Data Extractor Agent 第二阶段验收测试。

验证以下验收点：
1. data_extractor Agent 能加载目标 extraction skills。
2. data_extractor Agent 具备访问上传文件内容的工具能力（preview_excel）。
3. 上传文件后，工具链可以正确读取文件结构，为 Agent 理解任务目标提供条件。

注意：本测试不依赖真实 LLM 调用，因此无法验证模型是否真的决定调用工具；
它验证的是"Agent 已具备正确技能和工具、文件内容可被工具读取"这些前提条件。
真实模型下的端到端调用可使用 scripts/verify_data_extractor.py 手动验证。
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from scaffold.core.skills import load_skills
from scaffold.infra.config.app_config import get_app_config
from scaffold.plugins.tools.preview_excel import preview_excel
from scaffold.runtime.agents import _agent_registry


class TestExtractionSkillLoading:
    """验收点 1：目标 skills 被正确发现并可被 Agent 加载。"""

    def test_extraction_skills_are_discovered(self, _reset_app_config: Any) -> None:
        app_config = get_app_config()
        skills = load_skills(app_config)
        names = {s["name"] for s in skills}

        assert "extraction-goal" in names, f"未发现 extraction-goal skill，实际 skills: {names}"
        assert "extraction-code" in names, f"未发现 extraction-code skill，实际 skills: {names}"
        assert "extraction-validate" in names, f"未发现 extraction-validate skill，实际 skills: {names}"

    def test_data_extractor_agent_receives_extraction_skills(self, _reset_app_config: Any) -> None:
        """通过 mock _create_deep_agent 捕获 skills 参数，证明创建 data_extractor 时传入了技能目录。"""
        from scaffold.runtime import agents as agents_module

        captured_skills: list[str] | None = None

        def _fake_create_deep_agent(*, skills: list[str] | None, **kwargs: Any) -> Any:
            nonlocal captured_skills
            captured_skills = skills
            mock_agent = type("MockCompiledGraph", (), {"name": "data_extractor"})()
            _agent_registry["data_extractor"] = mock_agent
            return mock_agent

        with patch.object(agents_module, "_create_deep_agent", side_effect=_fake_create_deep_agent):
            agents_module.create_agent(name="data_extractor", harness_profile="data_extractor")

        assert captured_skills is not None, "创建 Agent 时未传入 skills 参数"
        assert len(captured_skills) > 0, "skills 参数为空列表"
        # skills 是包含 SKILL.md 父目录的路径
        assert any("skills" in str(path) for path in captured_skills), "skills 路径不包含 skills 目录"


class TestDataExtractorAgentTooling:
    """验收点 2：data_extractor Agent 拥有正确的工具集。"""

    def test_data_extractor_agent_has_extraction_tools_only(self, _reset_app_config: Any) -> None:
        """验证 data_extractor 只保留抽取相关工具，排除了代码审查类工具。"""
        from scaffold.runtime import agents as agents_module

        captured_tools: list[Any] = []

        def _fake_create_deep_agent(*, tools: list[Any], **kwargs: Any) -> Any:
            captured_tools.extend(tools)
            mock_agent = type("MockCompiledGraph", (), {"name": "data_extractor"})()
            _agent_registry["data_extractor"] = mock_agent
            return mock_agent

        with patch.object(agents_module, "_create_deep_agent", side_effect=_fake_create_deep_agent):
            agents_module.create_agent(name="data_extractor", harness_profile="data_extractor")

        tool_names = {getattr(t, "name", None) for t in captured_tools}

        assert "preview_excel" in tool_names
        assert "generate_extraction_code" in tool_names
        assert "execute_extraction_code" in tool_names
        assert "validate_extraction_result" in tool_names

        assert "read_file" not in tool_names, "data_extractor 不应拥有 read_file 工具"
        assert "write_file" not in tool_names, "data_extractor 不应拥有 write_file 工具"
        assert "run_ruff" not in tool_names, "data_extractor 不应拥有 run_ruff 工具"
        assert "generate_patch" not in tool_names, "data_extractor 不应拥有 generate_patch 工具"


class TestFileContentAccessibility:
    """验收点 3：上传文件后，Agent 可获取文件内容以理解任务目标。"""

    @pytest.fixture
    def sample_xlsx_bytes(self) -> bytes:
        """生成一个包含运价样例的 Excel 文件字节流。"""
        buffer = io.BytesIO()
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Freight"
        ws.append(["carrier", "pol", "pod", "container_type", "amount"])
        ws.append(["MSC", "Shanghai", "Los Angeles", "20GP", 1200])
        ws.append(["COSCO", "Ningbo", "Los Angeles", "40HQ", 2300])
        wb.save(buffer)
        return buffer.getvalue()

    @pytest.mark.asyncio
    async def test_uploaded_file_is_persisted_and_accessible(
        self,
        client: TestClient,
        sample_xlsx_bytes: bytes,
    ) -> None:
        """上传 Excel 文件后，应返回 artifact_id，且 preview_excel 能读取其结构。"""
        response = client.post(
            "/api/files/upload",
            data={"thread_id": "thread-acceptance-001"},
            files={
                "file": (
                    "freight_quote.xlsx",
                    sample_xlsx_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200, f"上传失败: {response.text}"
        data = response.json()
        assert "artifact_id" in data, f"响应缺少 artifact_id: {data}"
        artifact_id = data["artifact_id"]

        result = await preview_excel(artifact_id=artifact_id)
        assert "error" not in result, f"preview_excel 返回错误: {result}"
        sheet_names = {name for name in result["sheet_names"]}
        assert "Freight" in sheet_names, f"未找到 Freight sheet，实际: {sheet_names}"

        # 进一步验证列名被正确识别，说明文件内容确实被读取
        columns = {str(col) for col in result["columns"]}
        assert {"carrier", "pol", "pod", "container_type", "amount"}.issubset(columns)

    def test_data_extractor_endpoint_is_registered(self, client: TestClient) -> None:
        """data_extractor Agent 的 SSE 端点已注册并可访问健康检查。"""
        response = client.get("/agent/data_extractor/health")
        assert response.status_code == 200, f"健康检查失败: {response.text}"
        assert response.json()["agent"]["name"] == "data_extractor"
