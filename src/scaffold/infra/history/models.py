"""历史消息数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["goal_setting", "code_generated", "validating", "success", "failed"]


class ExtractionGoal(BaseModel):
    """抽取目标定义。"""

    description: str = Field(default="", description="抽取需求描述")
    fields: list[dict[str, Any]] = Field(default_factory=list, description="字段定义列表")
    constraints: list[str] = Field(default_factory=list, description="约束条件")
    expected_samples: list[dict[str, Any]] = Field(default_factory=list, description="期望示例行")


class ValidationCheck(BaseModel):
    """单项验证结果。"""

    rule: str
    status: Literal["pass", "fail"]
    details: str | None = None


class ValidationReport(BaseModel):
    """抽取结果验证报告。"""

    passed: bool
    summary: str
    checks: list[ValidationCheck]
    suggestion: str | None = None


class ExtractionTask(BaseModel):
    """抽取任务记录。"""

    task_id: str
    thread_id: str
    user_id: str = "default"
    upload_artifact_id: str
    status: TaskStatus
    requirements: dict[str, Any] | None = None
    script_artifact_id: str | None = None
    extracted_artifact_id: str | None = None
    validation_report: dict[str, Any] | None = None
    run_count: int = 0
    created_at: str
    updated_at: str


class ExtractionTemplate(BaseModel):
    """抽取模板记录：验证通过的目标 + 脚本 + 结构指纹，归属用户。"""

    template_id: str
    user_id: str = "default"
    name: str
    goal: dict[str, Any]
    script: str
    fingerprint: dict[str, Any]
    source_file_name: str | None = None
    created_at: str
    updated_at: str


class ThreadCreate(BaseModel):
    """创建线程请求。"""

    thread_id: str | None = Field(default=None, description="可选显式线程 ID")
    agent_id: str = Field(default="default", description="绑定 Agent 名称")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadSummary(BaseModel):
    """线程列表项。"""

    thread_id: str
    agent_id: str
    title: str | None
    last_message_preview: str | None
    created_at: str
    updated_at: str


class ThreadMessage(BaseModel):
    """单条历史消息。"""

    thread_id: str
    message_id: str
    run_id: str | None
    role: str
    content: str | None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    created_at: str
