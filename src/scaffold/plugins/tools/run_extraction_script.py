"""双模式执行抽取脚本：
- iterate: 在沙箱中运行，返回 stdout/stderr/退出码/输出文件/结果预览，不迁移状态不落盘工件，计入 run_count
- finalize: 执行脚本后迁移状态 code_generated -> validating，落盘 extraction 工件并挂接 task.extracted_artifact_id，不计入 run_count
"""

from __future__ import annotations

import csv
import logging
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any

from scaffold.infra.sandbox import get_sandbox
from scaffold.plugins.tools._extraction_common import get_extraction_workspace

logger = logging.getLogger(__name__)

# 结果预览的最大行数
PREVIEW_MAX_ROWS = 10
# 迭代模式最大运行次数
MAX_RUN_COUNT = 8


async def run_extraction_script(
    task_id: str,
    mode: str = "iterate",
    **kwargs: Any,
) -> dict[str, Any]:
    """在沙箱中执行抽取脚本，支持迭代模式和收口模式。

    Args:
        task_id: 抽取任务 ID。
        mode: 执行模式，支持 "iterate"（迭代）或 "finalize"（收口）。
        **kwargs: 兼容性参数（忽略）。

    Returns:
        iterate 模式: 包含 stdout、stderr、exit_code、output_files、result_preview、run_count 的字典。
        finalize 模式: 包含 task_id、extracted_artifact_id、stdout、stderr、exit_code、
            result_preview、status 的字典。
        超过 8 次运行限制时（仅 iterate）返回 error。
    """
    if mode not in ("iterate", "finalize"):
        return {"error": f"不支持的模式: {mode}，仅支持 'iterate' 或 'finalize'"}

    logger.info("run_extraction_script 被调用: task_id=%s, mode=%s", task_id, mode)

    async with get_extraction_workspace() as ws:
        task = await ws.get_task(task_id)
        if task is None:
            return {"error": f"抽取任务 {task_id} 不存在"}

        if task.script_artifact_id is None:
            return {"error": f"任务 {task_id} 尚未生成脚本"}

        # 读取脚本和上传文件
        script_bytes = await ws.read_artifact(task.script_artifact_id)
        upload_bytes = await ws.read_artifact(task.upload_artifact_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            input_dir = tmp_root / "input"
            output_dir = tmp_root / "output"
            input_dir.mkdir(parents=True, exist_ok=True)
            output_dir.mkdir(parents=True, exist_ok=True)

            input_file = input_dir / f"{task.upload_artifact_id}.xlsx"
            input_file.write_bytes(upload_bytes)

            script_path = tmp_root / "extract.py"
            script_path.write_bytes(script_bytes)

            sandbox = get_sandbox()
            result = await sandbox.run(
                script_path=script_path,
                input_dir=input_dir,
                output_dir=output_dir,
                timeout=60,
                memory_limit_mb=512,
                extra_env={
                    "INPUT_FILE": str(input_file),
                    "OUTPUT_FILE": str(output_dir / "extracted.csv"),
                },
            )

        if mode == "iterate":
            return await _handle_iterate_mode(ws, task, result)
        else:
            return await _handle_finalize_mode(ws, task, task_id, result)


async def _handle_iterate_mode(ws: Any, task: Any, result: Any) -> dict[str, Any]:
    """处理迭代模式：增加 run_count，返回执行结果，不持久化工件、不迁移状态。"""
    # 检查运行次数限制
    if task.run_count >= MAX_RUN_COUNT:
        return {
            "error": "已达到最大运行次数限制 (8 次)",
            "run_count": task.run_count,
            "max_runs": MAX_RUN_COUNT,
        }

    # 增加运行计数（仅计数，不持久化其他状态变更）
    task.run_count += 1
    await ws.update_task(task)

    # 准备结果预览
    result_preview = _build_result_preview(result)

    return {
        "task_id": task.task_id,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "output_files": {name: len(content) for name, content in result.output_files.items()},
        "result_preview": result_preview,
        "run_count": task.run_count,
        "execution_time_ms": result.execution_time_ms,
    }


async def _handle_finalize_mode(ws: Any, task: Any, task_id: str, result: Any) -> dict[str, Any]:
    """处理收口模式：校验执行结果、落盘 extraction 工件、迁移状态 code_generated -> validating，不计入 run_count。"""
    # 校验当前状态必须为 code_generated
    error = ws.check_task_transition(task, allowed=("code_generated",), action="收口")
    if error is not None:
        return error

    if result.exit_code != 0:
        return await ws.fail_task(
            task,
            summary="脚本执行失败",
            rule="脚本执行成功",
            details=(result.stderr or result.stdout)[:1000],
            suggestion="请检查 requirements 是否与文件结构匹配，或回到 generate_extraction_code 重新生成脚本",
            extra={"stderr": result.stderr, "stdout": result.stdout, "mode": "finalize"},
        )

    csv_bytes = result.output_files.get("extracted.csv")
    if csv_bytes is None:
        return await ws.fail_task(
            task,
            summary="脚本未输出 CSV 文件",
            rule="CSV 文件已生成",
            details=result.stdout or "无输出",
            suggestion="检查脚本是否正确写入 /mnt/output/extracted.csv",
            extra={"mode": "finalize"},
        )

    # 落盘 extraction 工件
    extraction_artifact = await ws.save_artifact(
        thread_id=task.thread_id,
        artifact_type="extraction",
        filename=f"{task_id}.csv",
        content=csv_bytes,
        original_name=f"{task_id}.csv",
        mime_type="text/csv",
        metadata={"task_id": task_id, "upload_artifact_id": task.upload_artifact_id, "mode": "finalize"},
    )

    task.extracted_artifact_id = extraction_artifact.artifact_id

    # 迁移状态 code_generated -> validating
    transition_error = await ws.transition_task(task, "validating", allowed=("code_generated",), action="收口")
    if transition_error is not None:
        return transition_error

    # 准备结果预览
    result_preview = _build_result_preview(result)

    return {
        "task_id": task_id,
        "extracted_artifact_id": extraction_artifact.artifact_id,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "result_preview": result_preview,
        "status": task.status,
        "execution_time_ms": result.execution_time_ms,
    }


def _build_result_preview(result: Any) -> dict[str, Any]:
    """从沙箱结果构建结果预览。"""
    preview: dict[str, Any] = {
        "has_output": bool(result.output_files),
        "files": list(result.output_files.keys()),
    }

    # 尝试解析 CSV 输出文件
    for filename, content in result.output_files.items():
        if filename.endswith(".csv"):
            columns, rows = _parse_csv_preview(content)
            preview["columns"] = columns
            preview["rows"] = rows
            preview["total_rows_estimate"] = len(rows)  # 这里只显示预览行数
            break

    return preview


def _parse_csv_preview(csv_bytes: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """解析 CSV 前 N 行用于预览。"""
    text = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(text))
    columns = reader.fieldnames or []
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        if i >= PREVIEW_MAX_ROWS:
            break
        rows.append(row)
    return columns, rows
