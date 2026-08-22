#!/usr/bin/env python3
"""Phase 3 分析能力端到端人工验证脚本（L2 层：真实模型全链路）。

用法：
    1. 启动服务：bash scripts/dev.sh（config.yaml 使用真实模型，API Key 已配置）
    2. 运行：uv run python scripts/verify_analysis.py

本脚本会：
    - 生成一份包含运价字段的样例 Excel
    - 上传到 /api/files/upload 获取 artifact_id
    - 第一轮向 /agent/data_extractor 发送抽取请求（走 preview → generate → execute → validate）
    - 等待抽取完成后，从 /api/files/?thread_id= 找到 extraction 工件
    - 第二轮发送分析请求（要求执行 SQL 分析并用 data_table 展示）
    - 断言 SSE 流中出现 query_extracted_data / analyze_extracted_data 的 TOOL_CALL
      与 render_ui 的 TOOL_CALL，且无 RUN_ERROR

退出码：0 = 验证通过；1 = 任一断言失败。
"""

from __future__ import annotations

import io
import json
import sys
import time
import uuid
from urllib.parse import urljoin

import openpyxl
import requests

BASE_URL = "http://localhost:8000"
THREAD_ID = f"thread-verify-{uuid.uuid4().hex[:8]}"
RUN_ID_PREFIX = f"run-verify-{uuid.uuid4().hex[:8]}"

RESULTS: list[str] = []


def _check(ok: bool, message: str) -> None:
    mark = "[PASS]" if ok else "[FAIL]"
    RESULTS.append(("PASS" if ok else "FAIL", message))
    print(f"{mark} {message}")
    if not ok:
        raise AssertionError(message)


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


def _list_extraction_id() -> str | None:
    """列出本会话工件，找到 extraction 类型的最新工件。"""
    resp = requests.get(urljoin(BASE_URL, "/api/files/"), params={"thread_id": THREAD_ID}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    for artifact in data.get("artifacts", []):
        if artifact.get("artifact_type") == "extraction":
            return artifact["artifact_id"]
    return None


def _agent_payload(run_id: str, message_id: str, content: str) -> dict:
    return {
        "threadId": THREAD_ID,
        "runId": run_id,
        "messages": [{"id": message_id, "role": "user", "content": content}],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def _call_agent(content: str) -> list[dict]:
    run_id = f"{RUN_ID_PREFIX}-{uuid.uuid4().hex[:8]}"
    message_id = f"msg-{uuid.uuid4().hex[:8]}"
    payload = _agent_payload(run_id, message_id, content)
    print(f"\n[>] 调用 POST /agent/data_extractor (thread_id={THREAD_ID})")
    print(f"    消息: {content[:120]}")
    with requests.post(
        urljoin(BASE_URL, "/agent/data_extractor"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        data=json.dumps(payload, ensure_ascii=False),
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        events = _collect_events(resp)
    return events


def _collect_events(resp: requests.Response) -> list[dict]:
    """逐块解析 SSE 流，返回事件列表，同时打印文本流与工具调用。"""
    events: list[dict] = []
    buffer = ""
    args_buffer: dict[str, str] = {}  # toolCallId -> 累积 args delta
    tool_names: dict[str, str] = {}  # toolCallId -> toolCallName

    def _emit(block: str) -> None:
        event = _parse_block(block, args_buffer, tool_names)
        if event:
            events.append(event)

    for chunk in resp.iter_content(chunk_size=4096):
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            _emit(block)
    if buffer.strip():
        _emit(buffer)
    return events


def _parse_block(block: str, args_buffer: dict[str, str], tool_names: dict[str, str]) -> dict | None:
    """解析单个 SSE 事件块，返回事件 dict（无内容或心跳返回 None）。"""
    lines = block.strip().splitlines()
    if not lines:
        return None
    if all(line.startswith(":") for line in lines):
        return None  # heartbeat
    data_lines = [line[len("data: ") :] for line in lines if line.startswith("data: ")]
    if not data_lines:
        return None
    try:
        event = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return None

    event_type = event.get("type") if isinstance(event, dict) else None
    if event_type == "TEXT_MESSAGE_CONTENT":
        sys.stdout.write(event.get("delta", ""))
        sys.stdout.flush()
    elif event_type == "TEXT_MESSAGE_START":
        print("\n[Assistant]", end=" ")
    elif event_type == "TEXT_MESSAGE_END":
        print("\n[消息结束]")
    elif event_type == "REASONING_MESSAGE_CONTENT":
        pass  # 思考过程不打印
    elif event_type == "TOOL_CALL_START":
        name = event.get("toolCallName", "?")
        call_id = event.get("toolCallId", "")
        tool_names[call_id] = name
        args_buffer[call_id] = ""
        print(f"\n[Tool Call] {name}")
    elif event_type == "TOOL_CALL_ARGS":
        call_id = event.get("toolCallId", "")
        args_buffer[call_id] = args_buffer.get(call_id, "") + str(event.get("delta", ""))
    elif event_type == "TOOL_CALL_END":
        call_id = event.get("toolCallId", "")
        name = tool_names.get(call_id, "?")
        print(f"  args: {args_buffer.get(call_id, '')[:200]}")
    elif event_type == "TOOL_CALL_RESULT":
        content = event.get("content", "")
        print(f"\n[Tool Result] {str(content)[:250]}{'...' if len(str(content)) > 250 else ''}")
    elif event_type in ("RUN_FINISHED", "RUN_ERROR"):
        print(f"\n[{event_type}]")
    return event


def _wait_for_extraction(max_wait: int = 90) -> str:
    """轮询本会话工件，等待 extraction 工件出现（抽取链路完成）。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        extraction_id = _list_extraction_id()
        if extraction_id:
            print(f"[OK] 抽取结果工件已生成: {extraction_id}")
            return extraction_id
        time.sleep(2)
    raise AssertionError("等待抽取结果工件超时（90s）")


def main() -> int:
    try:
        _health_check()
        content = _build_sample_excel()
        upload_id = _upload_file(content)

        # 第一轮：抽取
        events1 = _call_agent(
            f"请从 artifact_id={upload_id} 的 Excel 报价单中抽取 carrier、pol、pod、container_type、amount 字段，amount 必须是数字。"
        )
        types1 = {e.get("type") for e in events1}
        tool_names_1 = {
            e.get("toolCallName")
            for e in events1
            if e.get("type") == "TOOL_CALL_START" and e.get("toolCallName")
        }
        _check(bool(tool_names_1), f"第一轮出现工具调用: {sorted(tool_names_1)}")
        _check("RUN_ERROR" not in types1, "第一轮无 RUN_ERROR")

        # 等抽取完成，拿到 extraction 工件
        extraction_id = _wait_for_extraction()
        _check(extraction_id.startswith("art-"), f"extraction_id 格式正确: {extraction_id}")

        # 第二轮：分析 + 生成式 UI
        events2 = _call_agent(
            f"请对抽取结果 extraction_id={extraction_id} 执行分析：到 Los Angeles 的航线中哪个最便宜？"
            "请先调用 query_extracted_data 或 analyze_extracted_data，然后用 render_ui 的 data_table 展示结果，并给出结论。"
        )
        types2 = {e.get("type") for e in events2}
        tool_names = {
            e.get("toolCallName")
            for e in events2
            if e.get("type") == "TOOL_CALL_START" and e.get("toolCallName")
        }

        _check("RUN_ERROR" not in types2, "第二轮无 RUN_ERROR")
        _check(
            bool(tool_names & {"query_extracted_data", "analyze_extracted_data"}),
            f"Agent 调用了分析工具: {sorted(tool_names)}",
        )
        _check("render_ui" in tool_names, "Agent 调用了 render_ui 渲染结果")
        _check("RUN_FINISHED" in types2, "第二轮正常结束 RUN_FINISHED")

        # 汇总
        print("\n" + "=" * 60)
        print("Phase 3 端到端验证结果:")
        for status, msg in RESULTS:
            print(f"  [{status}] {msg}")
        print("=" * 60)
        failed = [m for s, m in RESULTS if s == "FAIL"]
        if failed:
            print(f"结论: 验证失败（{len(failed)} 项）")
            return 1
        print("结论: 验证全部通过 ✅  Phase 3 分析链路（抽取 → SQL 分析 → render_ui）在真实模型下可用")
        return 0
    except requests.HTTPError as exc:
        print(f"[ERROR] HTTP {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        return 1
    except AssertionError as exc:
        print(f"[ERROR] 断言失败: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
