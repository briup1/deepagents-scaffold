"""生成 Excel 抽取脚本。"""

from __future__ import annotations

import json
import logging
from typing import Any

from scaffold.plugins.tools._extraction_common import get_extraction_workspace

logger = logging.getLogger(__name__)


def _build_extraction_script(requirements: dict[str, Any], upload_artifact_id: str) -> str:
    """基于抽取目标生成可执行的 Python 脚本。"""
    requirements_json = json.dumps(requirements, ensure_ascii=False)
    return f'''from __future__ import annotations

"""自动生成的 Excel 抽取脚本。"""

import json
import os
import re

import pandas as pd

INPUT_FILE = os.environ.get("INPUT_FILE", "/mnt/input/{upload_artifact_id}.xlsx")
OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "/mnt/output/extracted.csv")
REQUIREMENTS = json.loads(r'{requirements_json}')


def _normalize(value: str) -> str:
    """将列名归一化以便模糊匹配。"""
    return re.sub(r"\\s+", "_", str(value).strip().lower()).replace("-", "_")


def _find_column(df: pd.DataFrame, field: dict[str, Any]) -> str | None:
    """在 DataFrame 列中查找与字段定义匹配的列。"""
    name = field["name"]
    aliases = [name] + field.get("aliases", [])
    aliases = aliases + field.get("description", "").replace(",", " ").split()
    normalized_aliases = {{_normalize(a) for a in aliases if a}}

    for col in df.columns:
        if _normalize(col) in normalized_aliases:
            return col

    # 模糊包含匹配
    for col in df.columns:
        norm_col = _normalize(col)
        for alias in normalized_aliases:
            if alias and (alias in norm_col or norm_col in alias):
                return col
    return None


def _convert_type(series: pd.Series, field: dict[str, Any]) -> pd.Series:
    """按字段类型转换数据。"""
    field_type = field.get("type", "string")
    if field_type == "number":
        # 移除常见货币符号和逗号后转数值
        cleaned = series.astype(str).str.replace(r"[,$￥¥]", "", regex=True)
        return pd.to_numeric(cleaned, errors="coerce")
    if field_type == "integer":
        cleaned = series.astype(str).str.replace(r"[,$￥¥]", "", regex=True)
        return pd.to_numeric(cleaned, errors="coerce").astype("Int64")
    if field_type == "boolean":
        return series.map({{"是": True, "否": False, "yes": True, "no": False, "true": True, "false": False}})
    if field_type == "date":
        return pd.to_datetime(series, errors="coerce")
    return series.astype(str)


def _apply_constraints(df: pd.DataFrame, constraints: list[str]) -> pd.DataFrame:
    """应用约束条件（MVP 仅支持跳过前 N 行说明文字）。"""
    skip_rows = 0
    for constraint in constraints:
        constraint = constraint.lower()
        match = re.search(r"(?:跳过|跳过前|skip|ignore first)\\s+(\\d+)\\s*(?:行|rows?)", constraint)
        if match:
            skip_rows = max(skip_rows, int(match.group(1)))
    if skip_rows > 0:
        df = df.iloc[skip_rows:].reset_index(drop=True)
    return df


def main() -> None:
    """主入口。"""
    # 读取第一个 sheet；若 requirements 指定 sheet_name 则使用之
    sheet_name = REQUIREMENTS.get("sheet_name", 0)
    df = pd.read_excel(INPUT_FILE, sheet_name=sheet_name, engine="openpyxl")

    df = _apply_constraints(df, REQUIREMENTS.get("constraints", []))

    result = pd.DataFrame()
    field_errors = []
    for field in REQUIREMENTS.get("fields", []):
        col = _find_column(df, field)
        if col is None:
            if field.get("required", False):
                field_errors.append(f"缺少必要字段: {{field['name']}}")
            result[field["name"]] = None
        else:
            result[field["name"]] = _convert_type(df[col], field)

    if field_errors:
        raise ValueError("; ".join(field_errors))

    # 过滤非空约束
    for field in REQUIREMENTS.get("fields", []):
        if field.get("required") and field["name"] in result.columns:
            missing = result[field["name"]].isna().sum()
            if missing > 0:
                raise ValueError(f"字段 {{field['name']}} 存在 {{missing}} 行空值")

    output_dir = os.path.dirname(OUTPUT_FILE)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    result.to_csv(OUTPUT_FILE, index=False)
    print(f"抽取完成，共 {{len(result)}} 行，{{len(result.columns)}} 列")


if __name__ == "__main__":
    main()
'''


async def generate_extraction_code(
    upload_artifact_id: str,
    requirements: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """根据上传文件和抽取目标生成抽取脚本。

    Args:
        upload_artifact_id: 上传的 Excel 工件 ID。
        requirements: 抽取目标，包含 description、fields、constraints、expected_samples。

    Returns:
        包含 task_id、script_artifact_id、script_content、status 的字典。
    """
    logger.info(
        "generate_extraction_code 被调用: upload_artifact_id=%s requirements_keys=%s",
        upload_artifact_id,
        list(requirements.keys()) if isinstance(requirements, dict) else "n/a",
    )

    async with get_extraction_workspace() as ws:
        upload_artifact = await ws.get_artifact(upload_artifact_id)
        if upload_artifact is None:
            return {"error": f"上传工件 {upload_artifact_id} 不存在"}
        if upload_artifact.artifact_type != "upload":
            return {"error": f"工件 {upload_artifact_id} 不是上传文件"}

        task = await ws.create_task(
            thread_id=upload_artifact.thread_id,
            upload_artifact_id=upload_artifact_id,
            requirements=requirements,
        )
        task_id = task.task_id

        script_content = _build_extraction_script(requirements, upload_artifact_id)
        script_artifact = await ws.save_artifact(
            thread_id=upload_artifact.thread_id,
            artifact_type="script",
            filename=f"{task_id}.py",
            content=script_content.encode("utf-8"),
            original_name=f"{task_id}.py",
            mime_type="text/x-python",
            metadata={"task_id": task_id, "upload_artifact_id": upload_artifact_id},
        )

        task.script_artifact_id = script_artifact.artifact_id
        task.status = "code_generated"
        await ws.update_task(task)

    return {
        "task_id": task_id,
        "script_artifact_id": script_artifact.artifact_id,
        "script_content": script_content,
        "status": task.status,
    }
