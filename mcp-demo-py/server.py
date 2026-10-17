import sqlite3
from pathlib import Path

from pydantic import BaseModel

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DB_PATH = Path(__file__).parent / "demo.db"

mcp = MCPServer(
    name="sqlite-explorer",
    instructions=(
        "查询本地 SQLite 数据库。写 SQL 之前先读取 schema://tables 资源，"
        "确认表名和字段名，不要凭猜测写查询。"
    ),
)

# MCPServer: name 标识服务；instructions 提供使用建议。
# Host 需要读取并使用这些说明；它们不会自动进入模型的对话。


def connect_readonly() -> sqlite3.Connection:
    """以只读方式打开已有数据库；文件不存在时不会悄悄创建空库。"""
    conn = sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


# 工具函数的四条约定：
# 1. 参数与类型注解 -> inputSchema
# 2. docstring -> 工具描述
# 3. 函数名 -> 默认工具名
# 4. 返回注解 -> outputSchema（能生成结构时）
@mcp.tool(title="列出所有表")
def list_tables() -> list[str]:
    """列出数据库中所有表名。"""
    conn = connect_readonly()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


class QueryResult(BaseModel):
    """一次查询的结果；最多返回 max_rows 行。"""

    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool


# BaseModel 用一个类描述结果的结构，也会校验构造它时传入的数据。
# 这里的模型是“数据模型”，与生成回答的 LLM 不是同一件事。
@mcp.tool(title="执行只读查询")
def query(sql: str, max_rows: int = 100) -> QueryResult:
    """执行 SELECT 或 WITH 查询。max_rows 为 1–1000，truncated 表示还有未返回的行。"""
    if not sql.strip().lower().startswith(("select", "with")):
        raise ToolError("只接受 SELECT / WITH 查询。")
    if not 1 <= max_rows <= 1000:
        raise ToolError("max_rows 必须在 1 到 1000 之间。")

    # 前缀检查用于给出友好提示；真正的只读限制由数据库连接负责。
    try:
        conn = connect_readonly()
        try:
            cur = conn.execute(sql)
            if cur.description is None:
                raise ToolError("这条语句没有返回结果集。")
            columns = [column[0] for column in cur.description]
            fetched = cur.fetchmany(max_rows + 1)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise ToolError(f"SQL 执行失败：{exc}") from exc

    rows = [list(row) for row in fetched[:max_rows]]
    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(fetched) > max_rows,
    )


@mcp.resource("schema://tables")
def schema_overview() -> str:
    """数据库的完整建表语句，供写查询前参考。"""
    conn = connect_readonly()
    try:
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()
        return "\n\n".join(f"-- {name}\n{ddl}" for name, ddl in tables)
    finally:
        conn.close()


@mcp.resource("table://{name}/sample")
def table_sample(name: str) -> str:
    """某张表的前 5 行示例数据。"""
    conn = connect_readonly()
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        if exists is None:
            raise ValueError(f"表不存在：{name}")
        # SQL 的 ? 占位符不能代替表名；校验存在后还要转义标识符。
        quoted_name = '"' + name.replace('"', '""') + '"'
        cur = conn.execute(f"SELECT * FROM {quoted_name} LIMIT 5")
        columns = [column[0] for column in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    lines = [" | ".join(columns), "-" * 32]
    lines += [" | ".join(str(value) for value in row) for row in rows]
    return "\n".join(lines)


@mcp.prompt(title="写一条分析查询")
def write_analysis_query(question: str) -> str:
    """把分析问题组织成一份查询步骤；调用它本身不会执行 SQL。"""
    return (
        "请根据下面的问题分析 SQLite 数据库。\n"
        f"问题：{question}\n\n"
        "1. 使用 Host 提供的 schema://tables 表结构，确认表名和字段名；\n"
        "2. 编写只读 SELECT；\n"
        "3. 用 query 工具执行；\n"
        "4. 根据实际结果用中文回答；truncated 为 true 时说明结果被截断。"
    )


if __name__ == "__main__":
    mcp.run()
