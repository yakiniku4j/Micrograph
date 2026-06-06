"""
契约解析层 — 将声明式 .md 文件解析为强类型 AgentDefinition。

对齐 Claude Code 的 Frontmatter 配置加载校验：
YAML 头部 → 硬性约束与路由元数据
Markdown 正文 → SystemMessage
"""

from __future__ import annotations

import logging
from pathlib import Path

import frontmatter
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class AgentDefinition(BaseModel):
    """子智能体声明式契约，1:1 映射 .md frontmatter。"""

    name: str
    description: str
    model: str = "deepseek-chat"
    tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)
    read_only: bool = False
    max_turns: int = 10
    system_prompt: str = ""

    @field_validator("max_turns")
    @classmethod
    def clamp_max_turns(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 50:
            return 50
        return v


def load_agent_definitions(agents_dir: str | Path) -> dict[str, AgentDefinition]:
    """
    扫描目录下所有 .md 文件，解析为 AgentDefinition 注册表。

    铁律：
    - disallowed_tools 始终包含 delegate_agent，防止递归扇出
    - 解析失败的文件跳过并记录警告，不阻塞整体加载
    """
    registry: dict[str, AgentDefinition] = {}
    agents_path = Path(agents_dir)

    if not agents_path.is_dir():
        logger.warning("agents 目录不存在: %s", agents_path)
        return registry

    for md_file in sorted(agents_path.glob("*.md")):
        try:
            post = frontmatter.load(str(md_file))

            # 防递归扇出：强制禁止 delegate_agent
            disallowed = set(post.metadata.get("disallowed_tools", []))
            disallowed.add("delegate_agent")

            definition = AgentDefinition(
                **{**post.metadata, "disallowed_tools": list(disallowed)},
                system_prompt=post.content.strip(),
            )
            registry[definition.name] = definition
            logger.info("已注册子智能体: %s (%s)", definition.name, md_file.name)

        except Exception as e:
            logger.warning("跳过无效配置 %s: %s", md_file.name, e)

    return registry
