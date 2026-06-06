"""
内置示例工具集 — 用于测试与验证的 Stub 工具，模拟真实工具的签名和行为。

生产环境中替换为真实业务实现即可，子图工厂通过 tool_pool 字典注入，
与具体的工具底层实现完全解耦。
"""

from langchain_core.tools import tool


# ── SQL 审计相关工具 ───────────────────────────────────────────


@tool
def inspect_pg_schema(table_name: str) -> str:
    """检查 PostgreSQL 表结构，返回列定义、索引和约束信息。"""
    return (
        f"表 `{table_name}` 结构:\n"
        f"  - id: BIGINT PRIMARY KEY (B-Tree index)\n"
        f"  - user_id: INT NOT NULL (索引: idx_{table_name}_user_id)\n"
        f"  - created_at: TIMESTAMP WITH TIME ZONE (无索引 [警告])\n"
        f"  - status: VARCHAR(32) (无索引)\n"
        f"  - payload: JSONB (GIN index: idx_{table_name}_payload)\n"
        f"  行数估算: ~2,400,000"
    )


@tool
def explain_query_plan(sql: str) -> str:
    """对 SQL 语句执行 EXPLAIN ANALYZE，返回查询计划和执行统计。"""
    return (
        f"EXPLAIN ANALYZE 结果 (模拟):\n"
        f"  SQL: {sql[:100]}...\n"
        f"  -> Seq Scan on orders  (cost=0.00..45123.00 rows=2400000 width=128)\n"
        f"     Filter: (created_at > '2024-01-01')\n"
        f"     Rows Removed by Filter: 1800000\n"
        f"  Planning Time: 0.3ms\n"
        f"  Execution Time: 1842.5ms\n"
        f"  [警告] 全表扫描，建议在 created_at 列上创建索引"
    )


@tool
def execute_write_sql(sql: str) -> str:
    """执行写入 SQL（INSERT/UPDATE/DELETE/DDL）。危险操作。"""
    return f"[已执行] {sql}"


# ── 代码审查相关工具 ──────────────────────────────────────────


@tool
def read_file_content(file_path: str) -> str:
    """读取指定文件内容。"""
    return (
        f"文件 `{file_path}` 内容 (模拟):\n"
        f"```python\n"
        f"def process_order(order_id: int, db):\n"
        f"    order = db.execute(f'SELECT * FROM orders WHERE id = {{order_id}}')\n"
        f"    # TODO: SQL injection vulnerability\n"
        f"    return order\n"
        f"```"
    )


@tool
def search_codebase(query: str) -> str:
    """在代码库中搜索匹配的代码片段。"""
    return (
        f"搜索 '{query}' 结果 (模拟):\n"
        f"  - src/handlers/order.py:42  → db.execute(f'SELECT...')\n"
        f"  - src/handlers/user.py:18   → db.execute(f'UPDATE...')\n"
        f"  - src/utils/migration.py:7  → db.execute('ALTER TABLE...')"
    )


@tool
def write_file_content(file_path: str, content: str) -> str:
    """写入文件内容。"""
    return f"[已写入] {file_path} ({len(content)} bytes)"


@tool
def validate_openapi_spec(spec_yaml: str) -> str:
    """校验 OpenAPI 3.1 规范文档。"""
    return (
        f"OpenAPI 规范校验结果 (模拟):\n"
        f"  [OK] 路径定义有效\n"
        f"  [OK] Schema 引用完整\n"
        f"  [警告] 缺少 security scheme 定义\n"
        f"  [警告] 部分 response 缺少 example"
    )


def get_tool_pool() -> dict:
    """返回所有可用工具的命名池。"""
    all_tools = [
        inspect_pg_schema,
        explain_query_plan,
        execute_write_sql,
        read_file_content,
        search_codebase,
        write_file_content,
        validate_openapi_spec,
    ]
    return {t.name: t for t in all_tools}
