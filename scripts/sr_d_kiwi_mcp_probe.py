from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ENDPOINT = "https://mcp.kiwi.com"


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


async def main() -> None:
    async with streamable_http_client(ENDPOINT) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            listed = await session.list_tools()
            tools = list(listed.tools)
            target = next((tool for tool in tools if tool.name in {"search-flight", "search_flight"}), None)
            if target is None:
                raise RuntimeError(f"Kiwi search tool absent: {[tool.name for tool in tools]}")
            schema = _jsonable(target.inputSchema)
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            expected = {"flyFrom", "flyTo", "departureDate"}
            if not expected.issubset(required):
                raise RuntimeError(f"unexpected live Kiwi MCP required fields: {sorted(required)}")
            arguments: dict[str, Any] = {
                "flyFrom": "TPE",
                "flyTo": "NRT",
                "departureDate": "05/10/2026",
                "returnDate": "09/10/2026",
                "adults": 1,
                "children": 0,
                "infants": 0,
                "cabinClass": "M",
                "currency": "TWD",
                "allow_self_transfer": True,
                "sort": "price",
            }
            arguments = {k: v for k, v in arguments.items() if k in props}
            result = await session.call_tool(target.name, arguments=arguments)
            payload = {
                "endpoint": ENDPOINT,
                "server": _jsonable(init.serverInfo),
                "protocol_version": getattr(init, "protocolVersion", None),
                "tool_names": [tool.name for tool in tools],
                "search_tool_schema": schema,
                "arguments": arguments,
                "result": _jsonable(result),
            }
            print("SR_D_KIWI_RESULT=" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
            if getattr(result, "isError", False):
                raise RuntimeError("Kiwi MCP search-flight returned an error result")


if __name__ == "__main__":
    asyncio.run(main())
