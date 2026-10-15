import anyio

from mcp import Client, StdioServerParameters
from mcp.types import TextContent, TextResourceContents

# 告诉 SDK:把 server.py 当子进程启动,用 stdio 通信
SERVER = StdioServerParameters(command="python", args=["server.py"])


async def main() -> None:
    async with Client(SERVER) as client:
        # 1. 连接建立后,这些信息已经填好了
        print("服务器:", client.server_info)
        print("协议版本:", client.protocol_version)

        # 2. 列出工具
        tools = await client.list_tools()
        print("\n工具:")
        for t in tools.tools:
            print(" -", t.name, "|", t.title)

        # 3. 调用工具
        res = await client.call_tool("list_tables", {})
        print("\nlist_tables ->", res.structured_content)

        res = await client.call_tool(
            "query", {"sql": "SELECT count(*) AS n FROM orders"}
        )
        print("query ->", res.structured_content)

        # 4. 故意写一条非法查询,看失败长什么样
        bad = await client.call_tool("query", {"sql": "DROP TABLE orders"})
        print("\n非法查询 -> is_error =", bad.is_error)
        for block in bad.content:
            if isinstance(block, TextContent):
                print("   错误信息:", block.text)

        # 5. 资源
        listed = await client.list_resources()
        print("\n资源:", [r.uri for r in listed.resources])

        templates = await client.list_resource_templates()
        print("资源模板:", [t.uri_template for t in templates.resource_templates])

        content = await client.read_resource("schema://tables")
        for c in content.contents:
            if isinstance(c, TextResourceContents):
                print("\nschema 前 100 字:", c.text[:100].replace("\n", " "))

        # 6. 提示模板
        prompts = await client.list_prompts()
        print("\n提示模板:", [p.name for p in prompts.prompts])

        rendered = await client.get_prompt(
            "write_analysis_query", {"question": "每个城市的订单总金额"}
        )
        for m in rendered.messages:
            print("   ", m.role, "->", m.content.text[:50])


if __name__ == "__main__":
    anyio.run(main)