"""验证抽取结果是否符合目标。"""

from __future__ import annotations

import csv as csv_module
import logging
from io import StringIO
from typing import Any

from scaffold.infra.history.models import ValidationCheck, ValidationReport
from scaffold.plugins.tools._extraction_common import get_extraction_workspace

logger = logging.getLogger(__name__)


async def validate_extraction_result(task_id: str) -> dict[str, Any]:
    """验证抽取结果 CSV 是否满足 requirements。

    Args:
        task_id: 抽取任务 ID。

    Returns:
        包含 task_id、passed、summary、checks、suggestion、status 的字典。
    """
    logger.info("validate_extraction_result 被调用: task_id=%s", task_id)

    async with get_extraction_workspace() as ws:
        task = await ws.get_task(task_id)
        if task is None:
            return {"error": f"抽取任务 {task_id} 不存在"}
        if task.status not in ("validating", "success", "failed"):
            return {"error": f"任务 {task_id} 当前状态为 {task.status}，无法验证"}
        if task.extracted_artifact_id is None:
            return {"error": f"任务 {task_id} 尚未生成抽取结果"}

        extracted_artifact = await ws.get_artifact(task.extracted_artifact_id)
        if extracted_artifact is None:
            return {"error": f"抽取结果工件 {task.extracted_artifact_id} 不存在"}

        try:
            csv_bytes = await ws.read_artifact(task.extracted_artifact_id)
        except FileNotFoundError:
            return {"error": f"工件文件不存在：{extracted_artifact.stored_path}"}

        requirements = task.requirements or {}
        fields = requirements.get("fields", [])
        expected_samples = requirements.get("expected_samples", [])

        text = csv_bytes.decode("utf-8", errors="replace")
        reader = csv_module.DictReader(StringIO(text))
        columns = reader.fieldnames or []
        rows = list(reader)

        checks: list[ValidationCheck] = []

        # 1. 字段存在性
        for field in fields:
            exists = field["name"] in columns
            checks.append(
                ValidationCheck(
                    rule=f"字段 {field['name']} 存在",
                    status="pass" if exists else "fail",
                    details=None if exists else "CSV 中未找到该字段",
                )
            )

        # 2. 非空约束
        for field in fields:
            if not field.get("required"):
                continue
            if field["name"] not in columns:
                checks.append(
                    ValidationCheck(
                        rule=f"字段 {field['name']} 非空",
                        status="fail",
                        details="字段不存在",
                    )
                )
                continue
            empty_count = sum(1 for row in rows if not row.get(field["name"], "").strip())
            checks.append(
                ValidationCheck(
                    rule=f"字段 {field['name']} 非空",
                    status="pass" if empty_count == 0 else "fail",
                    details=None if empty_count == 0 else f"存在 {empty_count} 行空值",
                )
            )

        # 3. 类型检查
        for field in fields:
            field_type = field.get("type", "string")
            if field["name"] not in columns:
                continue
            invalid = _check_type(rows, field["name"], field_type)
            checks.append(
                ValidationCheck(
                    rule=f"字段 {field['name']} 类型为 {field_type}",
                    status="pass" if invalid == 0 else "fail",
                    details=None if invalid == 0 else f"存在 {invalid} 行无法转换为 {field_type}",
                )
            )

        # 4. 示例行一致性
        sample_check = _check_samples(rows, columns, fields, expected_samples)
        checks.append(sample_check)

        passed = all(check.status == "pass" for check in checks)
        pass_count = sum(1 for check in checks if check.status == "pass")
        summary = f"{pass_count}/{len(checks)} 项检查通过"

        suggestion = ""
        if not passed:
            failed = [check.rule for check in checks if check.status == "fail"]
            suggestion = f"以下检查未通过：{', '.join(failed)}；建议根据失败项调整 requirements 或重新生成脚本。"

        report = ValidationReport(
            passed=passed,
            summary=summary,
            checks=checks,
            suggestion=suggestion or None,
        )

        task.validation_report = report.model_dump()
        task.status = "success" if passed else "failed"
        await ws.update_task(task)

    return {
        "task_id": task_id,
        "passed": report.passed,
        "summary": report.summary,
        "checks": [check.model_dump() for check in report.checks],
        "suggestion": report.suggestion,
        "status": task.status,
    }


def _check_type(rows: list[dict[str, str]], column: str, field_type: str) -> int:
    """返回指定列中无法转换为目标类型的行数。"""
    invalid = 0
    for row in rows:
        value = row.get(column, "").strip()
        if not value:
            continue
        if field_type == "number":
            cleaned = value.replace(",", "").replace("$", "").replace("¥", "").replace("￥", "")
            try:
                float(cleaned)
            except ValueError:
                invalid += 1
        elif field_type == "integer":
            cleaned = value.replace(",", "").replace("$", "").replace("¥", "").replace("￥", "")
            try:
                int(float(cleaned))
            except ValueError:
                invalid += 1
        elif field_type == "boolean":
            if value.lower() not in ("true", "false", "yes", "no", "是", "否", "1", "0"):
                invalid += 1
        elif field_type == "date":
            from datetime import datetime  # noqa: PLC0415

            try:
                datetime.fromisoformat(value)
            except ValueError:
                invalid += 1
    return invalid


def _check_samples(
    rows: list[dict[str, str]],
    columns: list[str],
    fields: list[dict[str, Any]],
    expected_samples: list[dict[str, Any]],
) -> ValidationCheck:
    """检查示例行是否在结果中出现（MVP 仅做部分匹配）。"""
    if not expected_samples:
        return ValidationCheck(
            rule="示例行一致",
            status="pass",
            details="未提供示例行",
        )

    # 提取示例中已定义字段的值
    field_names = [f["name"] for f in fields]
    matched_count = 0
    details: list[str] = []

    for sample in expected_samples:
        sample_subset = {k: v for k, v in sample.items() if k in field_names and k in columns}
        if not sample_subset:
            continue
        found = any(all(_values_equal(row.get(k, ""), v) for k, v in sample_subset.items()) for row in rows)
        if found:
            matched_count += 1
        else:
            details.append(f"未找到示例行: {sample_subset}")

    total = len(expected_samples)
    status = "pass" if matched_count == total else "fail"
    detail_str = f"{matched_count}/{total} 条示例行匹配" + (f"; {', '.join(details)}" if details else "")
    return ValidationCheck(
        rule="示例行一致",
        status=status,  # type: ignore[arg-type]
        details=detail_str,
    )


def _values_equal(actual: str, expected: Any) -> bool:
    """比较实际值与期望值，忽略大小写与空格差异。"""
    actual_str = str(actual).strip().lower()
    expected_str = str(expected).strip().lower()
    if actual_str == expected_str:
        return True
    # 数值近似
    try:
        return abs(float(actual_str) - float(expected_str)) < 1e-6
    except ValueError:
        return False
