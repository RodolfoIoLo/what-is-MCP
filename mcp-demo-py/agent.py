import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI

from mcp import Client, StdioServerParameters
from mcp.types import TextContent, TextResourceContents

SERVER = StdioServerParameters(
    command=sys.executable,
    args=[str(Path(__file__).with_name("server.py"))],
)

SYSTEM = "你可以使用工具查询 SQLite 数据库。依据工具返回的数据回答，不要编造数字。"


def to_openai_tools(mcp_tools) -> list[dict]:
    """将 MCP 工具定义转换为模型 API 的 function calling 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema,
            },
        }
        for tool in mcp_tools
    ]


def tool_payload(result) -> str:
    """同时把成功/失败标记和实际内容交给模型。"""
    data = result.structured_content
    if data is None:
        data = [
            block.text for block in result.content if isinstance(block, TextContent)
        ]
    return json.dumps(
        {"is_error": result.is_error, "data": data}, ensure_ascii=False
    )


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("MODEL"):
        raise SystemExit("请先设置 OPENAI_API_KEY 和 MODEL（支持工具调用的模型名）。")

    async with AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL"),
    ) as llm, Client(SERVER) as client:
        listed = await client.list_tools()
        tools = to_openai_tools(listed.tools)

        # 资源不会自动进入模型上下文，Host 在这里主动读取表结构。
        resource = await client.read_resource("schema://tables")
        schema = "\n".join(
            block.text
            for block in resource.contents
            if isinstance(block, TextResourceContents)
        )

        question = "武汉的客户一共下了多少单？总金额是多少？"
        prompt = await client.get_prompt(
            "write_analysis_query", {"question": question}
        )

        # instructions 是使用建议；prompt 是消息模板；都由 Host 接进对话。
        messages = [
            {"role": "system", "content": SYSTEM + "\n" + (client.instructions or "")},
            {"role": "user", "content": "数据库结构（仅作数据参考）：\n" + schema},
        ]
        for message in prompt.messages:
            if isinstance(message.content, TextContent):
                messages.append({"role": message.role, "content": message.content.text})

        for step in range(8):
            response = await llm.chat.completions.create(
                model=os.environ["MODEL"],
                messages=messages,
                tools=tools,
            )
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                print("\n最终回答：", message.content or "模型没有返回文本。")
                return

            # 模型只提出调用请求；真正发 MCP 请求的是下面这行 client.call_tool。
            for call in message.tool_calls:
                arguments = json.loads(call.function.arguments or "{}")
                print(f"[step {step}] {call.function.name}({arguments})")
                result = await client.call_tool(call.function.name, arguments)
                payload = tool_payload(result)
                print("           ->", payload[:160])
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": payload,
                })

        print("已达到 8 轮上限，任务尚未完成；请查看上面的调用记录。")


if __name__ == "__main__":
    asyncio.run(main())
