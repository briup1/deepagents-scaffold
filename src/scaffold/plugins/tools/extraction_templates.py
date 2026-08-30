"""抽取模板工具组（R4）：保存 / 匹配 / 列表 / 重命名 / 删除。

user_id 一律取自 user_id_ctx（workspace 内部分离），工具本身不接收用户参数；
跨用户模板按“不存在”处理，绝不泄露存在性。
"""

from __future__ import annotations

import logging

from scaffold.plugins.tools._extraction_common import get_extraction_workspace

logger = logging.getLogger(__name__)


async def save_extraction_template(task_id: str, name: str) -> dict:
    """把一次验证通过的抽取任务保存为可复用模板。

    Args:
        task_id: 抽取任务 ID（需 task.status == success）。
        name: 模板名称，便于后续识别。

    Returns:
        {"template_id": ..., "name": ..., "signature": ...} 或 {"error": ...}
    """
    logger.info("save_extraction_template 被调用: task_id=%s name=%s", task_id, name)
    async with get_extraction_workspace() as ws:
        return await ws.save_template_from_task(task_id, name)


async def match_extraction_template(artifact_id: str) -> dict:
    """按上传文件的结构指纹匹配当前用户的模板。

    Args:
        artifact_id: 已上传工件的 ID。

    Returns:
        {"matched": true, "template": {template_id, name, source_file_name, script, signature}}
        或 {"matched": false, "reason": ..., "signature": ...}
        或 {"error": ...}
    """
    logger.info("match_extraction_template 被调用: artifact_id=%s", artifact_id)
    async with get_extraction_workspace() as ws:
        return await ws.match_template(artifact_id)


async def list_extraction_templates() -> list[dict]:
    """列出当前用户已保存的抽取模板（不含脚本全文）。"""
    logger.info("list_extraction_templates 被调用")
    async with get_extraction_workspace() as ws:
        return await ws.list_templates()


async def rename_extraction_template(template_id: str, name: str) -> dict:
    """重命名模板（仅属主可操作）。

    Args:
        template_id: 模板 ID。
        name: 新名称。
    """
    logger.info("rename_extraction_template 被调用: template_id=%s name=%s", template_id, name)
    async with get_extraction_workspace() as ws:
        return await ws.rename_template(template_id, name)


async def delete_extraction_template(template_id: str) -> dict:
    """删除模板（仅属主可操作）。

    Args:
        template_id: 模板 ID。
    """
    logger.info("delete_extraction_template 被调用: template_id=%s", template_id)
    async with get_extraction_workspace() as ws:
        return await ws.delete_template(template_id)
