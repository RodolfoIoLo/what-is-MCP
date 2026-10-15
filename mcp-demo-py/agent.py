import asyncio
import json
import os

from openai import AsyncOpenAI

from mcp import Client, StdioServerParameters

SERVER = StdioServerParameters(command="python", args=["server.py"])

llm = AsyncOpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL"),   # 换成兼容 OpenAI 的其它端点
)

SYSTEM = (
    "你可以使用工具查询一个 SQLite 数据库."
    "需要数据时调用工具,不要凭空猜测数字."
)

def to_openai_tools(mcp_tools) -> list[dict]:
    """把 MCP 的工具定义翻译成 OpenAI function calling 的格式."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.input_schema,
            },
        }
        for t in mcp_tools
    ]


async def main() -> None:
    async with Client(SERVER) as client:
        # 1. 拿到 server 的工具清单
        listed = await client.list_tools()

        # 2. 翻译成模型 API 认识的格式
        tools = to_openai_tools(listed.tools)

        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "武汉的客户一共下了多少单?总金额是多少?"},
        ]

        # 3. 对话循环:模型可能要多轮才能答完
        for step in range(8):
            resp = await llm.chat.completions.create(
                model=os.environ.get("MODEL", "gpt-4o-mini"),
                messages=messages,
                tools=tools,
            )
            msg = resp.choices[0].message
            messages.append(msg)

            # 4. 模型不再调用工具了,说明它准备给最终答案
            if not msg.tool_calls:
                print("\n最终回答:", msg.content)
                return

            # 5. 这一轮模型要求调用的每个工具,逐个执行
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                print(f"[step {step}] 调用 {name}({args})")

                result = await client.call_tool(name, args)

                # 优先用结构化结果,没有就退回到文本内容
                if result.structured_content is not None:
                    payload = json.dumps(result.structured_content, ensure_ascii=False)
                else:
                    payload = "".join(
                        b.text for b in result.content if hasattr(b, "text")
                    )

                print(f"           -> {payload[:110]}")

                # 6. 把工具结果作为一条消息塞回对话
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": payload,
                })

        print("达到最大步数仍未得到最终答案")


if __name__ == "__main__":
    asyncio.run(main())