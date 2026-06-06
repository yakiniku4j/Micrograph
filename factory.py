"""
统一生命周期子图工厂 — 将 AgentDefinition 编译为标准 LangGraph StateGraph。

对齐 Claude Code 的 runAgent.ts "万能母机"：
  上下文裁剪 → 工具池过滤 → 环境注入 → 最大步数守卫
全部固化在标准模板中，每个子智能体实例共享同一套生命周期管线。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from loader import AgentDefinition

logger = logging.getLogger(__name__)


# ── 隔离的子智能体状态 ──────────────────────────────────────────
# 独立于主图 State，防止中间推理消息上溢污染主对话
class SubAgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    turn_count: int


def build_subagent_graph(
    defn: AgentDefinition,
    tool_pool: dict[str, BaseTool],
    llm_resolver: Callable[[str], Any],
) -> Any:
    """
    根据 AgentDefinition 编译一个完整的 ReAct 子图。

    生命周期阶段：
      1. 工具白名单 + 黑名单过滤（纵深防御）
      2. 系统提示词组装（只读模式自动追加约束）
      3. 推理节点（agent_node）
      4. 路由 + 最大轮次守卫
      5. 编译为 CompiledGraph
    """

    # ── Step 1: 工具过滤 ─────────────────────────────────────
    # defn.tools 为空 → 允许 tool_pool 中所有未被禁止的工具
    # defn.tools 非空 → 仅允许白名单中且未被禁止的工具
    disallowed = set(defn.disallowed_tools)
    allowed_tools: list[BaseTool] = []

    for name, t in tool_pool.items():
        if name in disallowed:
            continue
        if defn.tools and name not in defn.tools:
            continue
        allowed_tools.append(t)

    tool_names = [t.name for t in allowed_tools]
    logger.info(
        "[%s] 工具过滤完成: 允许 %s, 禁止 %s",
        defn.name,
        tool_names,
        list(disallowed),
    )

    # ── Step 2: 系统提示词组装 ─────────────────────────────────
    sys_content = defn.system_prompt
    if defn.read_only:
        sys_content += (
            "\n\n[系统约束：当前处于只读隔离模式，禁止任何写入或破坏性操作。"
            "如果你的工具列表中出现了写入类工具，拒绝调用并报告异常。]"
        )

    # ── Step 3: 解析 LLM 并绑定工具 ──────────────────────────
    llm = llm_resolver(defn.model)
    if allowed_tools:
        llm = llm.bind_tools(allowed_tools)

    # ── 推理节点 ──────────────────────────────────────────────
    async def agent_node(state: SubAgentState) -> dict:
        """核心推理：注入 SystemMessage + 历史消息 → LLM 调用。"""
        msgs = [SystemMessage(content=sys_content)] + list(state["messages"])
        response = await llm.ainvoke(msgs)
        return {
            "messages": [response],
            "turn_count": state.get("turn_count", 0) + 1,
        }

    # ── Step 4: 路由 + 最大轮次守卫 ───────────────────────────
    def should_continue(state: SubAgentState) -> str:
        """
        路由判定：
        - 达到 max_turns → 强制终止，防止死循环烧干 Token
        - 最后一条消息包含 tool_calls → 继续工具执行
        - 否则 → 推理结束
        """
        if state.get("turn_count", 0) >= defn.max_turns:
            logger.warning(
                "[%s] 达到最大轮次 %d，强制终止", defn.name, defn.max_turns
            )
            return END

        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if tool_calls:  # 非 None 且非空列表
            return "tools"
        return END

    # ── Step 5: 组装并编译子图 ────────────────────────────────
    workflow = StateGraph(SubAgentState)
    workflow.add_node("agent", agent_node)

    if allowed_tools:
        workflow.add_node("tools", ToolNode(allowed_tools))
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")
    else:
        # 无工具可用 → 纯推理，无 ReAct 循环
        workflow.add_edge(START, "agent")
        workflow.add_edge("agent", END)

    compiled = workflow.compile()
    logger.info("[%s] 子图编译完成 (工具数=%d)", defn.name, len(allowed_tools))
    return compiled
