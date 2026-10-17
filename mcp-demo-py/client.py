import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.types import TextContent, TextResourceContents

# 使用与 client 相同的 Python；脚本路径不依赖当前工作目录。
SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(Path(__file__).with_name("server.py"))],
)


async def main() -> None:
    # 进入时启动 server 子进程；离开时关闭连接并清理子进程。
    async with Client(SERVER) as client:
        print("服务器：", client.server_info)
        print("协议版本：", client.protocol_version)

        tools = await client.list_tools()
        print("\n工具：")
        for tool in tools.tools:
            print(" -", tool.name, "|", tool.title)

        result = await client.call_tool("list_tables", {})
        print("\nlist_tables ->", result.structured_content)

        result = await client.call_tool(
            "query", {"sql": "SELECT count(*) AS n FROM orders"}
        )
        print("query ->", result.structured_content)

        # 失败也是需要查看的结果：这次调用应被 server 拒绝。
        bad = await client.call_tool("query", {"sql": "DROP TABLE orders"})
        print("\n非法查询 -> is_error =", bad.is_error)
        for block in bad.content:
            if isinstance(block, TextContent):
                print("   错误信息：", block.text)

        listed = await client.list_resources()
        print("\n资源：", [str(resource.uri) for resource in listed.resources])
        templates = await client.list_resource_templates()
        print("资源模板：", [item.uri_template for item in templates.resource_templates])

        resource = await client.read_resource("schema://tables")
        for block in resource.contents:
            if isinstance(block, TextResourceContents):
                print("\nschema 前 100 字：", block.text[:100].replace("\n", " "))

        rendered = await client.get_prompt(
            "write_analysis_query", {"question": "每个城市的订单总金额"}
        )
        for message in rendered.messages:
            if isinstance(message.content, TextContent):
                print("提示模板：", message.role, "->", message.content.text[:80])


if __name__ == "__main__":
    asyncio.run(main())
