"""
主图挂载层 — 将所有子图封装为统一的 delegate_agent 工具。

对齐 Claude Code 的 AgentTool 单一工具入口设计：
主图只挂载 1 个 delegate_agent 工具，通过 subagent_type 参数路由到具体子图。
动态生成工具描述（子智能体目录），保持主图拓扑极简。
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from factory import build_subagent_graph
from loader import AgentDefinition

logger = logging.getLogger(__name__)


class DelegateInput(BaseModel):
    """delegate_agent 工具的输入 schema。"""

    subagent_type: str = Field(
        description="要委派的子智能体名称，必须是可用列表中的一个"
    )
    task_prompt: str = Field(description="委派给子智能体的具体任务描述")


def create_delegate_tool(
    registry: dict[str, AgentDefinition],
    tool_pool: dict[str, BaseTool],
    llm_resolver: Callable[[str], Any],
) -> BaseTool:
    """
    构建统一的 delegate_agent 工具。

    核心设计：
    1. 预编译所有声明式子图（启动时一次性完成）
    2. 动态生成子智能体目录描述，注入工具 description
    3. 每次调用创建全新隔离状态（Prototype 作用域）
    4. 仅回传子智能体最终结论，屏蔽中间工具调用噪音
    """

    # 预编译所有子图
    compiled_subagents: dict[str, Any] = {}
    for name, defn in registry.items():
        try:
            compiled_subagents[name] = build_subagent_graph(
                defn, tool_pool, llm_resolver
            )
            logger.info("子图预编译完成: %s", name)
        except Exception as e:
            logger.error("子图编译失败 %s: %s", name, e)

    # 动态生成子智能体目录
    catalog_lines = []
    for name, defn in registry.items():
        if name in compiled_subagents:
            mode = "[只读]" if defn.read_only else "[读写]"
            catalog_lines.append(f"- `{name}` {mode}: {defn.description}")

    catalog = "\n".join(catalog_lines)

    tool_description = (
        "将特定领域任务委派给专精子智能体执行并返回精简结论。\n"
        "每个子智能体拥有独立的工具集和安全约束，在隔离环境中运行。\n\n"
        f"可用子智能体列表：\n{catalog}"
    )

    async def _delegate(subagent_type: str, task_prompt: str) -> str:
        if subagent_type not in compiled_subagents:
            available = list(compiled_subagents.keys())
            return (
                f"错误：未知的 subagent_type '{subagent_type}'。\n"
                f"可选值：{available}"
            )

        logger.info("[Supervisor] 任务委派 -> 子智能体 [%s]: %s", subagent_type, task_prompt[:80])

        subgraph = compiled_subagents[subagent_type]

        # 全新隔离状态 — 每次调用互不干扰
        final_state = await subgraph.ainvoke(
            {
                "messages": [HumanMessage(content=task_prompt)],
                "turn_count": 0,
            }
        )

        # 记录子智能体执行轨迹（工具调用过程）
        for msg in final_state["messages"]:
            # 捕获 LLM 发起的工具调用
            if getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    logger.info("[%s] 调用工具: %s(%s)", subagent_type, tc["name"], tc["args"])
            # 捕获工具返回的结果摘要
            elif isinstance(msg, ToolMessage):
                summary = str(msg.content).strip().replace("\n", " ")[:90]
                logger.info("[%s] 工具返回: %s...", subagent_type, summary)

        logger.info("[%s] 推理完成", subagent_type)

        # 仅回传最终结论给主图
        result = final_state["messages"][-1].content
        logger.info("[%s] 执行完成，回传结果长度: %d 字符", subagent_type, len(result))
        return result

    return StructuredTool.from_function(
        coroutine=_delegate,
        name="delegate_agent",
        description=tool_description,
        args_schema=DelegateInput,
    )
