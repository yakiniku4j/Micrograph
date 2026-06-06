"""
主图 — Supervisor 协调者。

拓扑极简：只包含 supervisor_node + delegate_agent 工具。
主 LLM 通过 delegate_agent 的描述感知所有可用子智能体，
根据用户意图自主决策路由。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)

SUPERVISOR_SYSTEM_PROMPT = """\
你是一个智能协调者（Supervisor），负责将用户请求路由到合适的专精子智能体。

工作流程：
1. 分析用户请求，判断需要哪个（或哪些）子智能体处理
2. 使用 delegate_agent 工具将任务委派给对应的子智能体
3. 整合子智能体返回的结论，生成最终回复

原则：
- 如果用户请求涉及多个领域，可以串行或并行调用多个子智能体
- 不要自己尝试回答专业领域问题，始终委派给对应专家
- 整合结论时保持精炼，标注每个结论的来源子智能体
"""


class SupervisorState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def build_supervisor_graph(
    delegate_tool: BaseTool,
    llm_resolver: Callable[[str], Any],
    supervisor_model: str = "deepseek-chat",
) -> Any:
    """
    构建主图（Supervisor Graph）。

    极简拓扑：
      START → supervisor → [tools] → supervisor → ... → END

    delegate_agent 是唯一挂载的工具。
    ToolNode 在收到多个并行 tool_calls 时自动 asyncio.gather，
    天然支持并发扇出到多个子智能体。
    """

    tools = [delegate_tool]
    llm = llm_resolver(supervisor_model).bind_tools(tools)

    async def supervisor_node(state: SupervisorState) -> dict:
        msgs = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + list(
            state["messages"]
        )
        response = await llm.ainvoke(msgs)
        return {"messages": [response]}

    def should_continue(state: SupervisorState) -> str:
        last_msg = state["messages"][-1]
        tool_calls = getattr(last_msg, "tool_calls", None)
        if tool_calls:
            return "tools"
        return END

    workflow = StateGraph(SupervisorState)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "supervisor")
    workflow.add_conditional_edges(
        "supervisor", should_continue, {"tools": "tools", END: END}
    )
    workflow.add_edge("tools", "supervisor")

    return workflow.compile()
