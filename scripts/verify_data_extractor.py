#!/usr/bin/env python3
"""Data Extractor Agent 端到端人工验证脚本。

用法：
    1. 启动服务：bash scripts/dev.sh
    2. 确保 config.yaml 中第一个模型是真实模型且 API Key 已配置
    3. 运行：uv run python scripts/verify_data_extractor.py

本脚本会：
    - 生成一份包含运价字段的样例 Excel
    - 上传到 /api/files/upload 获取 artifact_id
    - 向 /agent/data_extractor 发送抽取请求
    - 打印 SSE 流中的文本消息与工具调用事件

注意：若服务使用 mock 模型（config.verify.yaml），模型不会真正调用工具，
只会返回固定文本。请使用配置真实模型的 config.yaml 进行验证。
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from urllib.parse import urljoin

import openpyxl
import requests

BASE_URL = "http://localhost:8000"
THREAD_ID = f"thread-verify-{uuid.uuid4().hex[:8]}"
RUN_ID = f"run-verify-{uuid.uuid4().hex[:8]}"


def _build_sample_excel() -> bytes:
    """构造一份运价样例 Excel 文件。"""
    buffer = io.BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Freight"
    ws.append(["carrier", "pol", "pod", "container_type", "amount", "valid_from"])
    ws.append(["MSC", "Shanghai", "Los Angeles", "20GP", 1200, "2026-08-01"])
    ws.append(["COSCO", "Ningbo", "Los Angeles", "40HQ", 2300, "2026-08-01"])
    ws.append(["ONE", "Qingdao", "Oakland", "20GP", 1350, "2026-08-05"])
    wb.save(buffer)
    return buffer.getvalue()


def _health_check() -> None:
    resp = requests.get(urljoin(BASE_URL, "/health"), timeout=10)
    resp.raise_for_status()
    print(f"[OK] 服务健康: {resp.json()}")


def _upload_file(content: bytes) -> str:
    resp = requests.post(
        urljoin(BASE_URL, "/api/files/upload"),
        data={"thread_id": THREAD_ID},
        files={
            "file": ("freight_quote.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    artifact_id = data["artifact_id"]
    print(f"[OK] 文件上传成功: artifact_id={artifact_id}, size={data['size_bytes']} bytes")
    return artifact_id


def _call_data_extractor(artifact_id: str) -> None:
    payload = {
        "threadId": THREAD_ID,
        "runId": RUN_ID,
        "messages": [
            {
                "id": f"msg-{uuid.uuid4().hex[:8]}",
                "role": "user",
                "content": (
                    f"请从 artifact_id={artifact_id} 的 Excel 报价单中抽取 "
                    "carrier、pol、pod、container_type、amount 字段，amount 必须是数字。"
                ),
            }
        ],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    print(f"\n[>] 调用 POST /agent/data_extractor (thread_id={THREAD_ID})")
    with requests.post(
        urljoin(BASE_URL, "/agent/data_extractor"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        data=json.dumps(payload, ensure_ascii=False),
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        _print_sse_stream(resp)


def _print_sse_stream(resp: requests.Response) -> None:
    """逐行解析 SSE 流并打印关键事件。"""
    buffer = ""
    for chunk in resp.iter_content(chunk_size=1024):
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            event_block, buffer = buffer.split("\n\n", 1)
            _print_event_block(event_block)
    if buffer.strip():
        _print_event_block(buffer)


def _print_event_block(block: str) -> None:
    """解析单个 SSE 事件块。"""
    lines = block.strip().splitlines()
    if not lines:
        return
    # 过滤掉心跳 comment
    if all(line.startswith(":") for line in lines):
        print("[heartbeat]")
        return

    data_lines = [line[len("data: ") :] for line in lines if line.startswith("data: ")]
    if not data_lines:
        return

    try:
        event = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        print(f"[raw] {' '.join(lines)}")
        return

    event_type = event.get("type") if isinstance(event, dict) else None
    if event_type is None:
        print(f"[event] {event}")
        return

    if event_type == "TEXT_MESSAGE_CONTENT":
        delta = event.get("delta", "")
        sys.stdout.write(delta)
        sys.stdout.flush()
    elif event_type == "TEXT_MESSAGE_START":
        print("\n[Assistant]", end=" ")
    elif event_type == "TEXT_MESSAGE_END":
        print("\n[消息结束]")
    elif event_type == "TOOL_CALL":
        print(f"\n[Tool Call] {event.get('toolName')} args={event.get('args')}")
    elif event_type == "TOOL_RESULT":
        result = event.get("result")
        summary = str(result)[:300]
        print(f"\n[Tool Result] {summary}{'...' if len(str(result)) > 300 else ''}")
    elif event_type == "RUN_FINISHED":
        print("\n[Run Finished]")
    elif event_type == "RUN_ERROR":
        print(f"\n[Run Error] {event.get('message')}")
    else:
        print(f"\n[{event_type}] {event}")


def main() -> int:
    try:
        _health_check()
        content = _build_sample_excel()
        artifact_id = _upload_file(content)
        _call_data_extractor(artifact_id)
        return 0
    except requests.HTTPError as exc:
        print(f"[ERROR] HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
