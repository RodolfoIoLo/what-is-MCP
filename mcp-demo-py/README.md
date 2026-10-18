# 用 Python 写一个 MCP Server：从首次接入到自己扩展

这个项目把一个本地 SQLite 数据库接入 MCP。它有两个工具、两种资源，以及一个提示模板。你可以先用普通客户端查询数据库，再让模型决定调用什么工具。

本文面向有 Python 编程基础、但尚未使用过 MCP / MCP SDK 的开发者。重点是各层职责、SDK 接口与调用链路；异步调用、上下文和生命周期会结合示例简要说明，不从基础语法讲起。

第一次接触 MCP，不必先记协议报文。先抓住三个动作：

1. **写函数**：例如执行一条 SQL。
2. **注册函数**：用装饰器告诉 MCPServer，它是工具、资源还是提示模板。
3. **运行服务**：等待客户端发来请求，由 SDK 找到对应函数并把结果送回去。

MCPServer 不负责思考问题，也不会自动调用大模型。这里负责调用大模型的是 `agent.py`。

> 阅读环境：Python 3.11+，官方 Python SDK `mcp==2.3.0`。依赖固定在 [pyproject.toml](pyproject.toml)。这份 README 是 [第 6 册 Python 实践](../MCP-learning-guide/06-python.html)的配套手册。
>
> **前半程不需要 API Key。** 跑通 `client.py` 就能验证 MCP 服务；只有最后的 Agent 示例需要模型 API。

## 阅读路线

- 想先看到结果：读第 1、2 节。
- 想知道 MCPServer 怎么用：读第 3–6 节。
- 想看懂 Agent 如何接进来：读第 7 节。
- 想加功能、排查问题：读第 8–10 节。

## 1. 先跑通：让客户端查到 6 条订单

在终端进入本 README 所在的 `mcp-demo-py` 目录。下面两种安装方法选一种。

### 方法 A：使用 uv

```bash
uv sync
uv run python seed.py
uv run python client.py
```

### 方法 B：使用 Python 自带的 venv

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "mcp[cli]==2.3.0" "openai==3.31.0"
.\.venv\Scripts\python.exe seed.py
.\.venv\Scripts\python.exe client.py
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install "mcp[cli]==2.3.0" "openai==3.31.0"
.venv/bin/python seed.py
.venv/bin/python client.py
```

`seed.py` 创建学习用的 `demo.db`，里面有 4 位客户、6 条订单。**再次执行会重建 customers 和 orders 两张表**；它用于重置示例数据，不用于初始化已有业务库。

客户端输出中应包含：

```text
list_tables -> {'result': ['customers', 'orders']}
query -> {'columns': ['n'], 'rows': [[6]], 'row_count': 1, 'truncated': False}
非法查询 -> is_error = True
```

还会输出表结构和提示模板。SDK 日志、路径与其他展示字段可能随环境不同；先确认上面这三个结果即可。

**不需要另开终端启动 server。** `client.py` 会启动 `server.py` 子进程，通过标准输入、标准输出与它通信。这种传输方式叫 stdio。直接运行 server 后终端一直等待，也是正常现象：它正在等 MCP 请求，不是在等你输入自然语言。

## 2. 四个文件，各负责一段工作

| 文件 | 职责 | 是否调用大模型 |
| --- | --- | --- |
| [seed.py](seed.py) | 创建并填充学习数据库 | 否 |
| [server.py](server.py) | 注册能力，执行 SQL，返回数据 | 否 |
| [client.py](client.py) | 按写好的顺序发现和调用能力 | 否 |
| [agent.py](agent.py) | 把问题和工具定义交给模型，执行模型提出的调用，再回填结果 | 是 |

```text
准备数据：seed.py → demo.db

先验证：client.py ── MCP ── server.py → demo.db

接模型：用户 → agent.py ⇄ 模型 API
                  │
                  └── MCP Client ⇄ server.py → demo.db
```

`agent.py` 是一个很小的 Host：它管理对话、使用 MCP Client 连接 server、调用模型 API。图里的模型和 server 没有直接连接。

## 3. 看懂 MCPServer：先分清“注册”和“执行”

下面是一个独立的最小示例。可以保存为另一目录里的 `mini_server.py`，不要覆盖本项目的 server。

```python
from mcp.server import MCPServer

mcp = MCPServer("calculator")

@mcp.tool()
def add(a: int, b: int) -> int:
    """把两个整数相加。"""
    return a + b

if __name__ == "__main__":
    mcp.run()
```

按 Python 执行文件的顺序看：

- `MCPServer(...)` 创建服务对象，集中管理服务信息和已注册的能力。
- Python 读到 `def add(...)` 时创建函数，`@mcp.tool()` 把它登记成可调用工具。**登记时没有计算加法。**
- `mcp.run()` 开始接收请求。等客户端调用 `add`，SDK 才检查参数并执行函数。
- 启动入口与注册代码分开，方便测试或调试工具导入服务对象，而不立即启动服务循环。

可以这样调用它：

```python
import asyncio
import sys
from pathlib import Path
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name("mini_server.py"))],
    )
    async with Client(server) as client:
        result = await client.call_tool("add", {"a": 2, "b": 3})
        print(result.structured_content)  # {'result': 5}

asyncio.run(main())
```

这段客户端代码的 MCP 要点是：`StdioServerParameters` 描述如何启动服务进程；`Client` 管理连接、协议协商与请求；`call_tool` 按注册名调用工具。业务代码不需要自己读写 stdin/stdout 或拼接 JSON-RPC。

这里也顺手理解三个异步用法：`async with Client(...)` 在进入时建立连接、退出时释放连接；`await client.call_tool(...)` 等待服务响应，等待期间事件循环可以处理其他任务；`asyncio.run(main())` 启动事件循环。`await` 不等于“自动并行调用多个工具”，本例仍按代码顺序逐次调用。

### SDK 自动处理了什么？

| 你写的内容 | SDK 怎么使用 |
| --- | --- |
| 函数名 `add` | 默认工具名，客户端按名字调用 |
| `a: int, b: int` | 生成输入结构说明，并检查传入参数 |
| 三引号里的 docstring | 工具描述，帮助调用方理解用途 |
| `-> int` | 生成输出结构说明，并转换返回结果 |
| `return a + b` | 业务代码，只有实际调用时才运行 |

输入、输出结构说明叫 JSON Schema。它能描述“需要哪些字段、字段是什么类型”，但业务规则仍然需要自己写：例如查询最多返回多少行、哪些目录允许读取。

### name、title、instructions 有什么区别？

- `name`：服务或工具的标识。调用工具时使用注册名。
- `title`：适合给人看的显示标题，不替代工具名。
- `instructions`：整个服务的使用建议，例如“先查看表结构，再写查询”。

`instructions` 不会自动变成模型的系统消息。Host 要读取它并决定如何使用；本项目在 `agent.py` 中显式加入对话。具体工具的 docstring、参数说明也同样重要，不存在一个包办全部提示的参数。

## 4. 从一次 query 调用看清来回链路

以客户端的这行代码为起点：

```python
result = await client.call_tool(
    "query", {"sql": "SELECT count(*) AS n FROM orders"}
)
```

完整过程如下：

1. Client SDK 将工具名和参数组成 `tools/call` 请求，通过 stdio 发给 server。
2. Server SDK 根据协议方法 `tools/call` 进入工具调用处理流程。
3. MCPServer 根据工具名 `query` 找到注册的 Python 函数。
4. SDK 检查输入，并补上默认参数 `max_rows=100`。
5. `query` 执行 SQL，得到一个 `QueryResult` 对象。
6. SDK 将这个对象转换为 MCP 结果，通过 stdio 返回。
7. Client SDK 解析响应，得到 Python 结果对象，赋给变量 `result`。

为了看清字段，下面只展示请求的业务部分，省略协议版本元数据等字段；它不是用于手工发送的完整报文：

```json
{
  "method": "tools/call",
  "params": {
    "name": "query",
    "arguments": {"sql": "SELECT count(*) AS n FROM orders"}
  }
}
```

注意这两个名字不在同一层：`tools/call` 是协议规定的方法，`query` 是自己注册的工具名。返回结果用请求 ID 与原请求对应，不需要再通过函数名猜测是哪一次调用。

### 函数返回值不等于客户端收到的整个对象

`query` 返回的是：

```python
QueryResult(
    columns=["n"],
    rows=[[6]],
    row_count=1,
    truncated=False,
)
```

客户端收到的外层对象还包含：

| Python 属性 | 含义 |
| --- | --- |
| `result.is_error` | 工具执行是否失败 |
| `result.structured_content` | 可直接取字段的数据，例如 `{'columns': ['n'], ...}` |
| `result.content` | 内容块列表，可能有文本、图片等 |

`row_count=1` 表示返回了 1 行汇总结果，订单数量是 `rows[0][0]` 中的 6。

线上的 JSON 字段叫 `isError`、`structuredContent`；这里使用的 Python 类型属性叫 `is_error`、`structured_content`。这是协议序列化名称与 Python 属性的区别，不是“服务端用一套命名、客户端用另一套”。

`QueryResult` 继承 Pydantic 的 `BaseModel`，作用是描述并校验数据结构。这里说的“模型”是数据模型，不是 LLM。

### 常见返回值怎么选？

| 函数返回注解 | 本示例版本的结构化结果 |
| --- | --- |
| `-> str` / `-> int` | 简单值放在 `result` 字段中 |
| `-> list[str]` | 例如 `{'result': ['customers', 'orders']}` |
| `-> QueryResult` | 直接使用类定义的字段 |
| `-> dict[str, int]` | 字典本身作为结构化内容 |
| 没有返回注解或裸 `dict` | 不要假定一定有自动生成的结构化结果 |

刚开始写工具时：返回一句话就用 `str`；返回多个有含义的字段，就定义一个 `BaseModel`。不要让客户端从一大段自然语言里重新提取数字。

## 5. 工具、资源、提示模板，什么时候选哪个？

| 需求 | 服务端注册方式 | 客户端用法 | 本项目示例 |
| --- | --- | --- | --- |
| 做一件事，传参数并取得结果 | `@mcp.tool()` | `call_tool(name, arguments)` | 执行查询 |
| 按地址读取一份上下文 | `@mcp.resource(uri)` | `read_resource(uri)` | 读取表结构 |
| 生成可复用的一组对话消息 | `@mcp.prompt()` | `get_prompt(name, arguments)` | 生成查询步骤 |

三种方式最终都可能执行 Python 函数。区别是对外约定：工具按名字和参数调用，资源按 URI 读取，提示模板返回消息。

### 工具：既要告诉它做什么，也要告诉它边界

本项目的 `query(sql: str, max_rows: int = 100)` 支持默认参数。调用时可以省略 `max_rows`；如果传了 0 或 1001，函数会抛出友好的 `ToolError`。

查询返回最多指定数量的行，并通过 `truncated` 告知是否还有未返回的数据。行数限制控制结果体积，**不等于查询耗时限制**；复杂 SQL 仍可能很慢。

数据库使用 `mode=ro` 和 `PRAGMA query_only=ON`。SQL 前缀检查只是帮助读者理解允许的查询入口，不能单独承担只读保证。

### 资源：地址不是网页链接

`schema://tables` 是这个 server 约定的资源标识，不需要有一个能在浏览器里打开的网页。

```python
@mcp.resource("schema://tables")
def schema_overview() -> str:
    # 完整实现见 server.py。
    ...
```

资源模板把 URI 的一部分变成参数：

```python
@mcp.resource("table://{name}/sample")
def table_sample(name: str) -> str:
    ...
```

读取 `table://orders/sample` 时，SDK 提取 `name='orders'`。URI 中的变量名要和函数参数对应。完整实现还会检查表是否存在，并正确转义 SQL 标识符。

资源与资源模板分开列出：`list_resources()` 列固定资源，`list_resource_templates()` 列模板；二者都使用 `read_resource()` 读取。

### 提示模板：取到的是消息，还没有执行任务

```python
prompt = await client.get_prompt(
    "write_analysis_query",
    {"question": "每个城市的订单总金额"},
)
```

这一步只取得查询步骤。它不会执行 SQL，也不会自己调用模型。`client.py` 只把模板打印出来；`agent.py` 才把模板消息加入对话。

如果一个 Host 没有主动读取资源、获取提示模板，它们就不会因为“注册过”而自动参与模型回答。

## 6. 工具失败了，应该返回什么？

预期内的业务失败使用 `ToolError`，例如参数超出范围、SQL 语法不正确：

```python
from mcp.server.mcpserver.exceptions import ToolError

if not 1 <= max_rows <= 1000:
    raise ToolError("max_rows 必须在 1 到 1000 之间。")
```

通过本项目的 MCP Client 调用时，工具失败会表现为 `result.is_error=True`，可读的错误文字在内容块里：

```python
from mcp.types import TextContent

if result.is_error:
    for block in result.content:
        if isinstance(block, TextContent):
            print(block.text)
```

这里“收到响应”不代表“业务成功”。Agent 必须把失败状态一起交给模型，模型才有机会修正参数。项目中的 `tool_payload()` 就负责保留这个状态。

也不要把所有异常都解释为工具失败：

| 情况 | 从哪一层排查 |
| --- | --- |
| SQL 错误，拿到 `is_error=True` | 工具参数或业务逻辑 |
| 连接关闭、启动失败、超时 | 解释器、进程、传输层 |
| JSON-RPC 协议错误 | 协议方法或请求格式 |
| 普通程序异常 | 查看 server 的 stderr 日志，定位代码问题 |

SDK 可能隐藏意外异常的内部细节；不要依赖把 Python traceback 直接显示给模型来调试。

另一个常见区别：`query(...)` 是普通 Python 调用；`await mcp.call_tool(...)` 是进程内的服务对象调用；`await client.call_tool(...)` 才经过客户端与协议处理。前两种失败可能直接抛异常，不能照搬第三种的结果处理方式。

## 7. 接入模型：为什么还需要 agent.py？

MCP 已经可以查数据，但到目前为止，“查什么”由客户端代码写死。Agent 把这个选择交给模型，同时负责实际执行调用。

本项目的执行顺序是：

```text
启动并连接 server
  → list_tools：获取工具名、描述、参数结构
  → read_resource：读取 schema://tables
  → get_prompt：取得查询步骤
  → Host 将 instructions、表结构、提示消息和工具定义交给模型
  → 模型返回 tool_calls（名字 + JSON 参数）
  → Host 调用 client.call_tool
  → server 执行函数，返回结果
  → Host 用 role=tool、tool_call_id 回填结果
  → 再请求模型，直到得到回答或达到轮数上限
```

几个对应关系值得看清：

| agent.py 中的代码 | 负责什么 |
| --- | --- |
| `to_openai_tools()` | 把 MCP 工具定义转换成模型 API 要的格式 |
| `client.read_resource(...)` | 让模型获得实际的数据库结构 |
| `client.instructions` | 取得 server 的使用建议，由 Host 加入对话 |
| `llm.chat.completions.create(...)` | 调用模型，不是发 MCP 请求 |
| `client.call_tool(...)` | 代模型执行一次 MCP 工具调用 |
| `tool_call_id` | 让模型知道这份结果对应自己提出的哪次调用 |

先设置环境变量，再启动 Agent。`MODEL` 填当前账户可用、支持工具调用的模型名。

Windows PowerShell：

```powershell
$env:OPENAI_API_KEY = "替换为你的 API Key"
$env:MODEL = "替换为可用的模型名"
uv run python agent.py
```

macOS / Linux：

```bash
export OPENAI_API_KEY="替换为你的 API Key"
export MODEL="替换为可用的模型名"
uv run python agent.py
```

使用 venv 时，将最后一行替换为相应解释器运行 `agent.py`。只有使用兼容服务时才需要另设 `OPENAI_BASE_URL`；接口格式、模型名和工具调用支持都要与该服务匹配。

示例问题是“武汉的客户一共下了多少单？总金额是多少？”。按 `seed.py` 的数据，核对答案应为 **3 单、988.50**；模型如何措辞、用了几次调用不固定。

这里有两个 ID：模型 API 的 `tool_call_id` 对应模型提出的调用；MCP 的 JSON-RPC ID 对应 Client 与 Server 的请求响应。Host 负责衔接这两段，不能把它们当成同一个协议。

## 8. 扩展一个工具：输入、输出与注册

假设需要“统计某座城市的订单”。先想清楚输入是城市名，输出是订单数，再把 SQL 写好，最后注册工具。

将下面代码放到 `server.py` 中，位置在 `if __name__ == '__main__'` 之前：

```python
@mcp.tool()
def count_city_orders(city: str) -> int:
    """统计指定城市客户的订单数量，例如 city='武汉'。"""
    conn = connect_readonly()
    try:
        row = conn.execute(
            "SELECT count(*) FROM orders AS o "
            "JOIN customers AS c ON c.id = o.customer_id "
            "WHERE c.city = ?",
            (city,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()
```

重启 server，或重新运行会拉起子进程的 client，然后调用：

```python
result = await client.call_tool("count_city_orders", {"city": "武汉"})
assert result.structured_content == {"result": 3}
```

这个例子还展示了 SQL 参数绑定：城市名作为数据传给 `?`，不拼接进 SQL。

### 什么时候需要 async def 或 Context？

SDK 同时支持同步和异步处理函数；按业务依赖选择即可，调用方看到的仍然是同一种 MCP 工具接口。耗时的同步 I/O 不应直接塞进异步处理函数。

`Context` 用来取得当前请求相关的能力。下面是一个可选例子：在工具内部读取本 server 的资源。

```python
from mcp.server.mcpserver.context import Context

@mcp.tool()
async def show_schema(ctx: Context) -> str:
    """读取并返回数据库表结构。"""
    parts = await ctx.read_resource("schema://tables")
    return "\n".join(str(part.content) for part in parts)
```

SDK 通过类型注解注入 `ctx`，它不会出现在模型需要填写的工具参数里。需要请求信息或发送进度时，应通过真实客户端测试；不要假定直接在 Python 中调用函数也拥有请求上下文。

更大的项目可以把业务函数分到其他模块，通过 `mcp.add_tool(function)` 注册。需要在服务启动时建立共享连接、退出时释放资源，再学习 `lifespan`；本例逐次打开并关闭 SQLite 连接，暂时不需要它。

可以把两者的范围这样区分：`lifespan` 管服务级资源的建立与释放，`Context` 提供当前请求的上下文。连接池适合按服务生命周期管理；本次调用的进度、请求信息则属于请求上下文。二者都不是额外传给模型填写的业务参数。

## 9. 换一种连接方式：从 stdio 到本地 HTTP

保持所有注册函数不变，只替换 server 最后的启动入口：

```python
if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8000,
    )
```

终端 A 启动 server：

```bash
uv run python server.py
```

终端 B 的客户端连接改为：

```python
async with Client("http://127.0.0.1:8000/mcp") as client:
    result = await client.call_tool("list_tables", {})
    print(result.structured_content)
```

URL 形式连接的是已经启动的 HTTP 服务；stdio 形式由 Client 启动子进程。两种方式里，查询函数都不用重写。本节是本机实验，监听本机地址。

这版 SDK 的 `host`、`port` 参数属于 `run()`，不要放进 `MCPServer(...)` 构造函数。

### SDK 版本与协议版本分开看

`mcp 2.3.0` 是 Python 包版本；`2026-07-28` 是协议版本。SDK 还包含旧版协议兼容支持。判断一次连接实际使用哪个版本，打印 `client.protocol_version`，不要根据用了 stdio 还是 HTTP 来猜。

本项目本地 stdio 验证协商到 `2026-07-28`。旧版教程中的 `initialize` 握手属于另一代协议流程；使用高层 Client 时让 SDK 负责发现与协商即可。

## 10. 遇到问题，按这个顺序检查

| 现象 | 先检查什么 |
| --- | --- |
| `No module named mcp` | 当前解释器是否装了依赖；客户端启动 server 是否用了同一个解释器 |
| 导入 `MCPServer` 失败 | 是否安装了本教程固定的 SDK 版本 |
| server 启动后一直等 | stdio 正在等请求；运行 client 来验证 |
| `unable to open database file` | 是否已经执行 seed.py；数据库路径和权限是否正确 |
| 工具名找不到 | 先打印 list_tools；确认已注册、已重启、调用的是 name 而不是 title |
| 参数报错 | 看工具的 input_schema；区分缺字段、类型错误和业务范围错误 |
| 模型不知道表结构 | 确认 Host 已读取资源，并把内容加入模型上下文 |
| 模型没有使用 prompt | 获取模板不等于发送消息；检查 messages 的组装 |
| 协议解析异常 | server 是否向 stdout 打印了调试信息 |
| 想读结果却发生 AttributeError | 确认属性名称，并在读 text 前判断内容块类型 |

server 的调试日志用 `logging`，或明确写到 stderr；stdio 的 stdout 留给协议。client 直接 `print` 输出结果没有这个限制。

### 从学习示例走向实际项目

本例便于看清调用链，尚未覆盖生产环境的全部要求。继续扩展时，优先补上这几项：

- **调用边界**：数据库只读不等于查询不会耗尽资源；还要考虑超时、结果体积和允许执行的操作。
- **Agent 容错**：当前示例假定模型返回合法 JSON 参数；实际接入还要处理参数解析失败、模型 API 超时，以及轮数耗尽后的退出策略。
- **远程服务**：本机 HTTP 跑通之后，才考虑鉴权、TLS 和部署；不要直接把学习用服务暴露到公网。
- **回归测试**：修改参数或返回类型时，同时测试工具发现、成功结果和失败结果；不能只验证普通 Python 函数能调用。

### 怎样验证自己真的学会了？

完成这三件事即可：

1. 不调用模型，使用 client 成功读取一个资源、调用一个工具。
2. 为工具增加一个参数和一个返回字段，观察 schema 与结果的变化。
3. 故意传错参数，分清“工具报告失败”和“进程根本没启动”这两类问题。

本项目的工具列表、查询结果、错误返回、资源与提示模板可以通过本地测试验证。模型最终如何选择工具受模型服务影响，不应把某一次回答当成 MCP 本身的保证。

## 继续查阅

- [Python SDK v2.3.0](https://github.com/modelcontextprotocol/python-sdk/tree/v2.3.0)：核对本教程使用的版本。
- [官方入门文档](https://py.sdk.modelcontextprotocol.io/get-started/)：按当前 SDK 文档学习更多能力。
- [SDK API 参考](https://py.sdk.modelcontextprotocol.io/api/mcp/)：需要 Context、lifespan 等进阶接口时查阅。
- [OpenAI 工具调用说明](https://developers.openai.com/api/docs/guides/function-calling)：核对 Agent 如何接收工具调用并回填结果；这段交互属于模型 API，不属于 MCP。
- [返回教程索引](../MCP-learning-guide/index.html)。
