# What is MCP?

> 一套从概念、协议报文和 Host 配置，一直走到 Python / Go 可运行示例的中文 MCP 学习仓库。

[![MCP Spec](https://img.shields.io/badge/MCP-2026--07--28-6f42c1)](https://modelcontextprotocol.io/specification/2026-07-28)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white)](mcp-demo-py/README.md)
[![Go](https://img.shields.io/badge/Go-1.25%2B-00add8?logo=go&logoColor=white)](mcp-demo-go/server/main.go)

这个仓库回答三个问题：MCP 到底解决什么问题；Client、Server、Host 与模型之间怎样协作；一个 MCP server 如何从普通函数变成可发现、可调用、可验证的能力。

它不是只展示一段最小代码。教程会把注册与执行、工具 / 资源 / 提示、stdio / HTTP、协议错误 / 工具错误，以及模型 API 与 MCP 的边界串成一条完整链路。

## 从这里开始

| 入口 | 适合谁 | 能得到什么 |
| --- | --- | --- |
| [HTML 学习手册](MCP-learning-guide/index.html) | 第一次系统学习 MCP | 7 册教程：概念、架构、协议、生态、配置与两种 SDK 实践 |
| [Python SQLite demo](mcp-demo-py/README.md) | 有 Python 基础，第一次使用 MCP SDK | tools / resources / prompts、stdio Client、Agent loop |
| [Go filesystem demo](mcp-demo-go/server/main.go) | 有 Go 基础，第一次使用 Go SDK | 只读文件工具、结构化结果、路径边界与 stdio Client |

建议按手册 01 → 07 阅读。如果只想先跑通代码，可以直接选择下面任意一个 demo；二者都不需要模型 API Key。Python 的 `agent.py` 是唯一需要模型服务的可选步骤。

## 快速运行

### 在浏览器阅读手册

直接打开 `MCP-learning-guide/index.html`，或者在仓库根目录启动一个本地静态服务器：

```bash
python -m http.server 8000 --directory MCP-learning-guide
```

然后访问 `http://127.0.0.1:8000`。

### Python：查询 SQLite

要求 Python 3.11+，推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
cd mcp-demo-py
uv sync
uv run python client.py
```

仓库已带有学习数据库。需要恢复初始数据时再执行 `uv run python seed.py`；它会重建示例表。

预期可以看到两个表、6 条订单、一次被拒绝的写查询，以及资源和提示模板的读取结果。完整解释见 [Python demo README](mcp-demo-py/README.md)。

### Go：读取限定目录

要求 Go 1.25+。请在本机编译，不使用仓库中的预编译二进制。

Windows PowerShell / Git Bash：

```bash
cd mcp-demo-go
go build -o filesystem-server.exe ./server
go run ./client ./filesystem-server.exe ./workspace
```

macOS / Linux：

```bash
cd mcp-demo-go
go build -o filesystem-server ./server
go run ./client ./filesystem-server ./workspace
```

客户端会列出 `workspace`、读取 `hello.txt`，再验证 `../outside.txt` 被拒绝。

## MCP 调用链

```text
用户
  ↓
Host / Agent ─── 把工具描述交给模型 ───→ 模型提出 tool call
  │                                           │
  └──── MCP Client ← 工具名与参数 ────────────┘
             ↓  tools/call
         MCP Server
             ↓
       执行业务函数 / 访问数据
             ↓
       结构化结果或工具错误
             ↓
Host 把结果回填给模型 → 模型回答或继续调用
```

模型不会直接连接 MCP Server。Host 同时管理模型对话和 MCP Client；Server 负责声明能力、校验输入、执行业务逻辑并返回结果。

## 仓库结构

```text
.
├── MCP-learning-guide/   # 01–07 HTML 教程和索引
├── mcp-demo-py/          # SQLite Server、Client、Agent 与独立手册
│   ├── server.py
│   ├── client.py
│   ├── agent.py
│   └── README.md
├── mcp-demo-go/          # 只读 filesystem Server 与验证 Client
│   ├── server/main.go
│   ├── client/main.go
│   └── workspace/
└── README.md
```

两个 demo 故意选择不同问题：Python 示例覆盖 MCP 的三种核心原语和 Agent 回路；Go 示例聚焦工具、结构化输出与文件访问边界。它们互相补充，不是同一功能的机械翻译。

## 当前基线

- [x] 7 册中文教程，统一导航并适配桌面与移动端
- [x] Python SQLite MCP：tools、resources、prompts、stdio Client、可选 Agent
- [x] Go filesystem MCP：列目录、读 UTF-8 文本、大小限制和路径越界保护
- [x] 成功、业务失败、协议连接与结构化结果的讲解
- [x] Python / Go 本地调用验证
- [ ] 自动化 CI、跨平台测试与文档链接检查
- [ ] GitHub Pages 在线阅读入口

## 下一站：DocProof MCP

计划中的第一个独立项目是 **DocProof**：一个给编码 Agent 使用的、确定性的文档质量检查 MCP Server。它不是再做一遍文件系统 server，而是把“修改文档后如何证明没有破坏仓库”变成可调用能力。

首个可用版本准备覆盖：

- 扫描 Markdown / HTML 的相对链接、锚点、图片与引用文件；
- 检查代码块标注、重复标题、失效导航和跨目录搬迁后的旧路径；
- 返回结构化问题列表、定位和修复建议，而不直接修改文件；
- 提供清晰的允许目录、文件数量和大小上限；
- 带单元测试、stdio 配置示例、版本化发布和 `server.json`。

当它达到“陌生用户可以安装、5 分钟跑通、错误输出可操作、CI 有覆盖”的标准后，再向 [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) 提交收录 PR，并发布到官方 MCP Registry。

## 后续探索路线

DocProof 之后，这个仓库会逐步加入更接近 MCP 基础设施的实验：

1. **Protocol Trace Lab**：捕获并解释 stdio / Streamable HTTP 报文，对比协议版本和错误层次。
2. **Tool Contract Linter**：评估工具名、描述、JSON Schema、结构化输出与风险注解，减少模型误用。
3. **Host Compatibility Matrix**：用同一组 fixtures 验证不同 Host 对 tools、resources、prompts 和扩展的支持差异。
4. **Security Lab**：复现路径逃逸、stdout 污染、提示注入、过大结果、OAuth 配置错误等真实风险。
5. **Registry Explorer**：读取官方 Registry，分析元数据质量、版本、安装方式和生态空白。
6. **MCP Apps / Tasks**：实践交互式 UI 与长任务扩展，理解扩展协商和降级行为。
7. **Conformance CI**：接入官方 conformance suite，让“能跑”进一步变成“符合某一版规范”。

路线的目标不是堆 demo，而是逐层经历 Server、Client、Host、测试工具、注册发现、授权安全与扩展机制。

## 项目原则

- **可运行比代码截图重要**：文档中的完整示例应当能被实际执行和测试。
- **边界要写出来**：明确区分 MCP、模型 API、Host 逻辑和业务函数。
- **失败路径也是教程**：同时展示成功结果、工具错误与传输故障。
- **安全默认值优先**：最小权限、只读优先、限制输入输出范围，不把注解当安全控制。
- **版本事实可核对**：重要协议结论链接到规范、SDK 或官方项目。

## 参与与反馈

欢迎通过 Issue 提交：难以理解的段落、无法复现的命令、不同平台的差异，以及真正值得做成 MCP 工具的问题。提交代码前请让示例保持小而完整，并同时更新对应教程。

如果这个仓库帮你把 MCP 从“听说过”变成“能解释、能运行、能验证”，欢迎 Star；更有价值的是带着一个失败案例或改进建议回来。

## 参考

- [MCP Specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Go SDK](https://github.com/modelcontextprotocol/go-sdk)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
- [MCP Conformance Tests](https://github.com/modelcontextprotocol/conformance)
- [Official MCP Registry](https://github.com/modelcontextprotocol/registry)

