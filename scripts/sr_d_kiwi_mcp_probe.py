from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ENDPOINT = "https://mcp.kiwi.com"


def _schema_args(schema: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties") or {}
    args: dict[str, Any] = {}

    def set_if(name: str, value: Any) -> None:
        if name in props:
            args[name] = value

    set_if("trip_type", "round-trip")
    set_if("origin", "TPE")
    set_if("destination", "NRT")
    set_if("departure_date", "2026-10-05")
    set_if("return_date", "2026-10-09")
    set_if("adults", 1)
    set_if("children", 0)
    set_if("infants", 0)
    set_if("cabin_class", "economy")
    set_if("currency", "TWD")

    if "flexibility" in props:
        p = props["flexibility"]
        args["flexibility"] = False if p.get("type") == "boolean" else 0
    if "passengers" in props:
        args["passengers"] = {"adults": 1, "children": 0, "infants": 0}
    if "dates" in props:
        args["dates"] = {"departure": "2026-10-05", "return": "2026-10-09"}

    for name in schema.get("required") or []:
        if name in args:
            continue
        p = props.get(name) or {}
        enum = p.get("enum") or []
        if enum:
            args[name] = enum[0]
        elif p.get("type") == "string":
            args[name] = ""
        elif p.get("type") in {"integer", "number"}:
            args[name] = 0
        elif p.get("type") == "boolean":
            args[name] = False
        elif p.get("type") == "array":
            args[name] = []
        elif p.get("type") == "object":
            args[name] = {}
        else:
            raise RuntimeError(f"cannot safely synthesize required MCP argument {name!r}")
    return args


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
            arguments = _schema_args(schema)
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


if __name__ == "__main__":
    asyncio.run(main())
