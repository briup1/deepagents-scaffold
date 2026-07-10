"""用于在 VS Code 中直接调试 agent 执行的入口脚本。

不经过 HTTP/SSE，直接调用 ``create_agent()`` 并单步运行，方便在 middleware、
worker 和工具实现中打断点。

用法::

    PYTHONPATH=src uv run python scripts/debug_agent.py --message "hello"

或在 VS Code 的运行与调试面板中选择 "Debug: Run Agent Directly"。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 确保 src 在 Python 路径中（VS Code 的 launch.json 也会设置 PYTHONPATH，
# 这里做双重保险，方便命令行直接运行）。
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langchain_core.messages import HumanMessage

from scaffold.core.agents import create_agent
from scaffold.infra.config.app_config import get_app_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_agent(message: str, thread_id: str | None = None) -> None:
    """创建 agent 并以流式模式运行，便于逐轮观察 ReAct 循环。

    使用 ``stream_mode="updates"`` 输出每个节点产生增量状态，并标注节点名，
    方便直接看出中间件链与模型节点的执行顺序。
    """
    app_config = get_app_config()

    # 这里会触发 create_agent() 内的所有装配逻辑，是观察 agent 构建过程
    # （模型、工具、中间件链、子 agent、记忆）的好断点。
    agent = create_agent(name="default")

    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id or "debug-thread"},
        # 与 HTTP 入口保持一致，使用 config.yaml 中的迭代预算
        "recursion_limit": app_config.agent.max_iterations,
    }
    input_state = {"messages": [HumanMessage(content=message)]}

    print(f"\n>>> User: {message}\n")

    # stream_mode="updates" 返回 {node_name: partial_state_update}。
    # 我们一边累积完整状态，一边在输出中标注当前 chunk 来自哪个节点，
    # 这样可以直接看到 ReAct 循环中每个中间件/模型节点的执行顺序与副作用。
    accumulated_state: dict[str, Any] = {}
    async for chunk in agent.astream(input_state, config=config, stream_mode="updates"):
        node_name, update = _extract_node_update(chunk)
        if update is not None:
            _deep_merge(accumulated_state, update)

        print(f"--- chunk (node: {node_name}) ---")
        print(
            json.dumps(
                {"node": node_name, "update": _serialize_chunk(update), "state": _serialize_chunk(accumulated_state)},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        print()

    print("\n<<< Agent run finished\n")


def _serialize_chunk(chunk: object) -> object:
    """尽力将流式 chunk 序列化为可打印的字典。"""
    if chunk is None:
        return None
    if hasattr(chunk, "model_dump"):
        try:
            return chunk.model_dump()
        except Exception:
            pass
    if hasattr(chunk, "to_json"):
        try:
            return chunk.to_json()
        except Exception:
            pass
    if isinstance(chunk, dict):
        return {k: _serialize_chunk(v) for k, v in chunk.items()}
    if isinstance(chunk, list):
        return [_serialize_chunk(v) for v in chunk]
    if hasattr(chunk, "__dict__"):
        return {k: _serialize_chunk(v) for k, v in chunk.__dict__.items()}
    return chunk


def _extract_node_update(chunk: object) -> tuple[str, Any]:
    """从 stream_mode='updates' 的 chunk 中提取节点名称与状态更新。

    LangGraph ``updates`` 模式会产出形如 ``{node_name: partial_state}`` 的字典。
    对于特殊事件（如 ``__start__``、``__end__``、``__interrupt__``），
    键名保留原样，更新内容可能为空。
    """
    if isinstance(chunk, dict) and chunk:
        # 取第一个键作为节点名；updates 模式下单个 chunk 通常只含一个节点
        node_name = next(iter(chunk.keys()))
        update = chunk[node_name]
        return node_name, update
    return "<unknown>", chunk


def _deep_merge(target: dict[str, Any], source: Any) -> None:
    """将 source 递归合并进 target，列表直接覆盖（因为消息列表需要整体替换）。"""
    if not isinstance(source, dict):
        return
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug agent execution directly from VS Code.")
    parser.add_argument(
        "--message",
        "-m",
        default="hello",
        help="User message to send to the agent.",
    )
    parser.add_argument(
        "--thread-id",
        "-t",
        default="debug-thread",
        help="Thread ID for the conversation.",
    )
    args = parser.parse_args()

    asyncio.run(run_agent(args.message, args.thread_id))


if __name__ == "__main__":
    main()
