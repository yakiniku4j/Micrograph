# Micrograph

基于 LangGraph 的声明式多 Agent 编排框架。

## 概述

Micrograph 提供了一种声明式的多智能体编排方案。系统将每个专精子智能体封装为独立的微子图（Subgraph），主协调器（Supervisor）通过统一的结构化委托工具进行任务分发与结果聚合，实现配置驱动的智能体管理与上下文隔离。

---

## 核心特性

- **声明式配置管理**：通过 Markdown 文件的 Frontmatter 元数据定义子智能体的工具白名单、权限与运行参数，正文作为系统提示词，支持热插拔加载。
- **状态物理隔离**：每个子智能体运行于独立的 `SubAgentState`，内部多轮推理与工具调用轨迹不侵入主图上下文。
- **单工具委托协议**：主图仅暴露一个结构化委托工具，保持主图拓扑结构恒定，最大化复用大模型前缀缓存（Prompt KV Cache）。
- **静态权限拦截**：在图编译期完成工具白名单过滤、黑名单拦截（默认禁止子图递归派生）及只读模式约束。

---

## 架构设计

```text
agents/*.md          -> 声明式定义 (Frontmatter 元数据 + System Prompt)
     │
loader.py            -> 契约解析层 (Pydantic 校验与参数解析)
     │
factory.py           -> 子图工厂层 (编译隔离的 StateGraph 子图)
     │
registry_tool.py     -> 统一委托层 (封装为 delegate_agent 结构化工具)
     │
supervisor.py        -> 协调器主图 (意图识别与任务分发)
     │
main.py              -> CLI 运行入口
```

---

## 目录结构

```text
micrograph/
├── agents/                  # 声明式子智能体配置目录
│   ├── api_designer.md      # API 设计专家
│   ├── code_reviewer.md     # 代码审查专家
│   └── sql_auditor.md       # SQL 审计专家
├── loader.py                # 配置解析与注册
├── factory.py               # 子图编译工厂
├── registry_tool.py         # 委托工具封装
├── supervisor.py            # 主图协调器
├── tools.py                 # 工具池定义
├── main.py                  # CLI 入口
├── pyproject.toml           # 项目配置
├── .env.example             # 环境变量模版
└── README.md
```

---

## 快速开始

### 1. 安装依赖

推荐使用 `uv`：

```bash
uv sync
```

或使用 `pip`：

```bash
pip install -e .
```

### 2. 配置环境变量

参考 `.env.example` 配置模型访问凭据：

```bash
# OpenAI 兼容接口
export OPENAI_API_KEY="sk-..."

# 或第三方服务商 (如 DeepSeek、vLLM)
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
```

### 3. 运行

```bash
uv run python main.py
```

---

## 配置规范

在 `agents/` 目录下添加 `.md` 文件即可注册新的子智能体：

```markdown
---
name: security_auditor
description: 审计系统鉴权与认证逻辑的专家，当涉及权限校验时调用。
model: deepseek-chat
tools:
  - read_file_content
  - search_codebase
disallowed_tools:
  - execute_write_sql
read_only: true
max_turns: 8
---
你是一名专注于网络安全与身份认证的审计专家。
重点检查 Token 校验逻辑、CORS 配置与潜在越权漏洞。
输出须给出风险等级判定并附带修改代码建议。
```
