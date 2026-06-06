"""
Micrograph — 交互式命令行运行入口

基于 LangGraph 的多 Agent 编排：
  1. 声明式 .md 配置 -> AgentDefinition 注册表
  2. AgentDefinition -> 微图工厂编译（StateGraph）
  3. 统一 delegate_agent 工具 -> 主图 Supervisor

运行方式：
  export OPENAI_API_KEY=sk-xxx  # 或其他 LLM provider
  python main.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from loader import load_agent_definitions
from registry_tool import create_delegate_tool
from supervisor import build_supervisor_graph
from tools import get_tool_pool

# ── 日志配置 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ── LLM 解析器 ───────────────────────────────────────────────
def llm_resolver(model_name: str) -> ChatOpenAI:
    """
    根据模型名称返回对应的 LLM 实例。

    支持通过环境变量配置：
      LLM_BASE_URL — API base URL（兼容 DeepSeek / vLLM / Ollama 等）
      LLM_API_KEY  — API key
    """
    base_url = os.environ.get("LLM_BASE_URL", None)
    api_key = os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

    return ChatOpenAI(
        model=model_name,
        temperature=0,
        api_key=api_key,
        base_url=base_url,
    )


def safe_input(prompt: str = "") -> str:
    """解决部分终端粘贴中文多字节字符时的 UnicodeDecodeError。"""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        line_bytes = sys.stdin.buffer.readline()
        if not line_bytes:
            raise EOFError
        return line_bytes.decode("utf-8", errors="replace").strip()
    except UnicodeDecodeError:
        return input().strip()


async def main():
    agents_dir = Path(__file__).parent / "agents"

    # ── Layer 1: 声明式配置加载 ──────────────────────────────
    logger.info("=" * 60)
    logger.info("Layer 1: 加载声明式 Agent 配置")
    logger.info("=" * 60)

    registry = load_agent_definitions(agents_dir)

    if not registry:
        logger.error("未找到任何 Agent 配置，请检查 agents/ 目录")
        sys.exit(1)

    for name, defn in registry.items():
        logger.info(
            "Agent [%s] | model=%s | tools=%s | read_only=%s | max_turns=%d",
            name,
            defn.model,
            defn.tools or "[全部]",
            defn.read_only,
            defn.max_turns,
        )

    # ── Layer 2: 工具池 + 子图工厂 ───────────────────────────
    logger.info("=" * 60)
    logger.info("Layer 2: 构建工具池与编译子图")
    logger.info("=" * 60)

    tool_pool = get_tool_pool()
    logger.info("已注册工具池: %s", list(tool_pool.keys()))

    # ── Layer 3: 主图挂载 ────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Layer 3: 构建 Supervisor 主图")
    logger.info("=" * 60)

    delegate_tool = create_delegate_tool(registry, tool_pool, llm_resolver)
    supervisor = build_supervisor_graph(delegate_tool, llm_resolver)

    logger.info("主图构建完成，delegate_agent 工具已成功挂载")
    logger.info("=" * 60)

    logger.info("Micrograph 交互终端已就绪。输入 'quit' 退出。")

    while True:
        try:
            user_input = safe_input("\nUser: ")
        except (EOFError, KeyboardInterrupt):
            logger.info("检测到退出信号，程序结束。")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            logger.info("用户退出，程序结束。")
            break

        logger.info("接收用户输入，开始执行图调度...")

        try:
            result = await supervisor.ainvoke(
                {"messages": [HumanMessage(content=user_input)]}
            )

            final_msg = result["messages"][-1]
            logger.info("Supervisor 输出结果:\n%s", final_msg.content)

        except Exception as e:
            logger.error("执行异常: %s", e, exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
