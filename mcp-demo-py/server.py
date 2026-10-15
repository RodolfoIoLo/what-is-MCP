import sqlite3
from pathlib import Path

from pydantic import BaseModel

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

DB_PATH = Path(__file__).parent / "demo.db"

mcp = MCPServer(
    name = "sqlite-explorer", 
    instructions = (
        "查询本地 SQLite 数据库.写 SQL 之前先读取 schema://tables 资源"
        "确认表名和字段名,不要凭猜测写查询."
    ),
)

# MCPServer: name + title/description + instructions

@mcp.tool(title = "列出所有表")
def list_tables() -> list[str]:
    """列出数据库中所有表名"""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]

class QueryResult(BaseModel):
    """一次查询的结果"""
    columns: list[str]
    rows: list[list]
    row_count: int

# Pydantic BaseModel: Pydantic的核心基类,用于定义数据结构或者模型
# 核心作用有3个:用类来描述数据字段,自动校验输入数据类型,自动把输入转换成规范的Python对象
# 通常用于:API请求参数校验/配置文件读取/数据库模型/DTO

@mcp.tool(title="执行只读查询")
def query(sql: str) -> QueryResult:
    """对数据库执行一条只读 SQL 查询,返回结果集.只允许 SELECT."""
    head = sql.lstrip().lstrip("(").lower()
    if not head.startswith(("select", "with", "pragma")):
        raise ToolError("只允许只读查询(SELECT / WITH / PRAGMA).")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description]
            rows = [list(r) for r in cur.fetchall()]
    except sqlite3.Error as e:
        raise ToolError(f"SQL 执行失败: {e}") from e

    return QueryResult(columns=columns, rows=rows, row_count=len(rows))

@mcp.resource("schema://tables")
def schema_overview() -> str:
    """数据库的完整建表语句,供模型在写查询前参考."""
    with sqlite3.connect(DB_PATH) as conn:
        tables = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()
    return "\n\n".join(f"-- {name}\n{ddl}" for name, ddl in tables)

@mcp.resource("table://{name}/sample")
def table_sample(name: str) -> str:
    """某张表的前 5 行示例数据."""
    with sqlite3.connect(DB_PATH) as conn:
        try:
            cur = conn.execute(f'SELECT * FROM "{name}" LIMIT 5')
        except sqlite3.Error as e:
            raise ValueError(f"读不到表 {name}:{e}") from e
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()

    lines = [" | ".join(columns), "-" * 32]
    lines += [" | ".join(str(v) for v in r) for r in rows]
    return "\n".join(lines)

@mcp.prompt(title="写一条分析查询")
def write_analysis_query(question: str) -> str:
    """根据一句自然语言问题,引导模型写出正确的 SQL."""
    return (
        "你要为下面的问题写一条 SQLite 查询.\n"
        f"问题:{question}\n\n"
        "步骤:\n"
        "1. 先读取 schema://tables 资源,确认表名和字段名;\n"
        "2. 写一条只读 SELECT;\n"
        "3. 用 query 工具执行它;\n"
        "4. 用中文解释结果."
    )


if __name__ == "__main__":
    mcp.run()