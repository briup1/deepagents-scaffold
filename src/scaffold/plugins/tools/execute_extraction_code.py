"""执行生成的抽取脚本。"""

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


async def execute_extraction_code(task_id: str, **kwargs: Any) -> dict[str, Any]:
    """在沙箱中执行抽取脚本并生成 CSV 工件。

    Args:
        task_id: 抽取任务 ID。

    Returns:
        包含 task_id、extracted_artifact_id、total_rows、columns、status 的字典。
    """
    logger.info("execute_extraction_code 被调用: task_id=%s", task_id)

    async with get_extraction_workspace() as ws:
        task = await ws.get_task(task_id)
        if task is None:
            return {"error": f"抽取任务 {task_id} 不存在"}
        error = ws.check_task_transition(task, allowed=("goal_setting", "code_generated"), action="执行")
        if error is not None:
            return error

        if task.script_artifact_id is None:
            return {"error": f"任务 {task_id} 尚未生成脚本"}

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

            if result.exit_code != 0:
                return await ws.fail_task(
                    task,
                    summary="脚本执行失败",
                    rule="脚本执行成功",
                    details=(result.stderr or result.stdout)[:1000],
                    suggestion="请检查 requirements 是否与文件结构匹配，或回到 generate_extraction_code 重新生成脚本",
                    extra={"stderr": result.stderr, "stdout": result.stdout},
                )

            csv_bytes = result.output_files.get("extracted.csv")
            if csv_bytes is None:
                return await ws.fail_task(
                    task,
                    summary="脚本未输出 CSV 文件",
                    rule="CSV 文件已生成",
                    details=result.stdout or "无输出",
                    suggestion="检查脚本是否正确写入 /mnt/output/extracted.csv",
                )

        extraction_artifact = await ws.save_artifact(
            thread_id=task.thread_id,
            artifact_type="extraction",
            filename=f"{task_id}.csv",
            content=csv_bytes,
            original_name=f"{task_id}.csv",
            mime_type="text/csv",
            metadata={"task_id": task_id, "upload_artifact_id": task.upload_artifact_id},
        )

        # 解析 CSV 元数据
        columns, total_rows = _parse_csv_meta(csv_bytes)

        task.extracted_artifact_id = extraction_artifact.artifact_id
        transition_error = await ws.transition_task(
            task, "validating", allowed=("goal_setting", "code_generated"), action="执行"
        )
        if transition_error is not None:
            return transition_error

    return {
        "task_id": task_id,
        "extracted_artifact_id": extraction_artifact.artifact_id,
        "total_rows": total_rows,
        "columns": columns,
        "status": task.status,
    }


def _parse_csv_meta(csv_bytes: bytes) -> tuple[list[str], int]:
    """解析 CSV 列名与行数。"""
    text = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(StringIO(text))
    columns = reader.fieldnames or []
    total_rows = sum(1 for _ in reader)
    return columns, total_rows
