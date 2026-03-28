import json

BANNER = r"""
   ▄     ▄▀  ▄███▄      ▄     ▄   █▀▄▀█ ▄█▄    █ ▄▄
    █  ▄▀    █▀   ▀      █     █  █ █ █ █▀ ▀▄  █   █
██   █ █ ▀▄  ██▄▄    ██   █ █   █ █ ▄ █ █   ▀  █▀▀▀
█ █  █ █   █ █▄   ▄▀ █ █  █ █   █ █   █ █▄  ▄▀ █
█  █ █  ███  ▀███▀   █  █ █ █▄ ▄█    █  ▀███▀   █
█   ██               █   ██  ▀▀▀    ▀            ▀
                        MCP ENUMERATOR & FUZZ TOOL
"""


def print_server_info(info: dict):
    si    = info.get("serverInfo", {})
    caps  = info.get("capabilities", {})
    proto = info.get("protocolVersion", "?")

    print(f"\n  Server  : {si.get('name', 'unknown')} v{si.get('version', '?')}")
    print(f"  Protocol: MCP {proto}")

    if caps:
        parts = []
        if "tools" in caps:
            parts.append(f"tools (listChanged={caps['tools'].get('listChanged', '?')})")
        if "prompts" in caps:
            parts.append(f"prompts (listChanged={caps['prompts'].get('listChanged', '?')})")
        if "resources" in caps:
            parts.append(
                f"resources (subscribe={caps['resources'].get('subscribe', '?')}, "
                f"listChanged={caps['resources'].get('listChanged', '?')})"
            )
        if parts:
            print(f"  Capabilities: {', '.join(parts)}")

    instructions = info.get("instructions", "")
    if instructions:
        print(f"  Instructions: {instructions}")


def print_tool_verbose(tool: dict):
    print(f"    Name       : {tool.get('name')}")
    print(f"    Description: {tool.get('description', '-')}")
    schema   = tool.get("inputSchema", {})
    props    = schema.get("properties", {})
    required = schema.get("required", [])
    if props:
        print("    Parameters :")
        for param, meta in props.items():
            req   = " (required)" if param in required else " (optional)"
            ptype = meta.get("type", "any")
            pdesc = meta.get("description", "")
            print(f"      - {param} [{ptype}]{req}" + (f": {pdesc}" if pdesc else ""))


def print_prompt_verbose(prompt: dict):
    print(f"    Name       : {prompt.get('name')}")
    print(f"    Description: {prompt.get('description', '-')}")
    args = prompt.get("arguments", [])
    if args:
        print("    Arguments  :")
        for a in args:
            req = " (required)" if a.get("required") else " (optional)"
            print(f"      - {a['name']}{req}" + (f": {a.get('description', '')}" if a.get("description") else ""))


def print_resource_verbose(resource: dict):
    print(f"    Name       : {resource.get('name', '-')}")
    print(f"    URI        : {resource.get('uri') or resource.get('uriTemplate')}")
    print(f"    MIME       : {resource.get('mimeType', '-')}")
    print(f"    Description: {resource.get('description', '-')}")


def print_results(results: dict, verbose: set):
    for category, methods in results.items():
        print(f"\n[{category.upper()}]")
        for method, response in methods.items():
            if "error" in response:
                print(f"  {method}  ERROR: {response['error']}")
                continue

            result    = response.get("result", {})
            tools     = result.get("tools", [])
            prompts   = result.get("prompts", [])
            resources = result.get("resources", [])
            templates = result.get("resourceTemplates", [])
            items     = tools or prompts or resources or templates

            print(f"  {method}  ({len(items)} item{'s' if len(items) != 1 else ''})")

            v_tools     = "tools"     in verbose or "all" in verbose
            v_prompts   = "prompts"   in verbose or "all" in verbose
            v_resources = "resources" in verbose or "all" in verbose

            for item in tools:
                if v_tools:
                    print_tool_verbose(item)
                else:
                    name, desc = item.get("name", str(item)), item.get("description", "")
                    print(f"    - {name}" + (f": {desc}" if desc else ""))

            for item in prompts:
                if v_prompts:
                    print_prompt_verbose(item)
                else:
                    name, desc = item.get("name", str(item)), item.get("description", "")
                    print(f"    - {name}" + (f": {desc}" if desc else ""))

            for item in resources + templates:
                if v_resources:
                    print_resource_verbose(item)
                else:
                    name = item.get("name") or item.get("uri") or item.get("uriTemplate") or str(item)
                    desc = item.get("description", "")
                    print(f"    - {name}" + (f": {desc}" if desc else ""))


def print_resource_content(resp: dict, indent: str = "  "):
    res = resp.get("result", {})
    for item in res.get("contents", []):
        uri  = item.get("uri", "")
        mime = item.get("mimeType", "")
        print(f"{indent}[{uri}]" + (f" ({mime})" if mime else ""))
        if "text" in item:
            for line in item["text"].splitlines():
                print(f"{indent}{line}")
        elif "blob" in item:
            print(f"{indent}[binary blob, base64 encoded]")
        else:
            print(f"{indent}{json.dumps(item, indent=2)}")


def print_call_result(result: dict, call_type: str):
    if "error" in result:
        err = result["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        print(f"  [error] {msg}")
        return

    res = result.get("result", {})

    if call_type == "tool":
        if res.get("isError"):
            print("  [tool error]")
        for item in res.get("content", []):
            itype = item.get("type")
            if itype == "text":
                print(item.get("text", ""))
            elif itype == "image":
                print(f"  [image/{item.get('mimeType', '?')}] (base64 data omitted)")
            else:
                print(json.dumps(item, indent=2))

    elif call_type == "prompt":
        desc = res.get("description")
        if desc:
            print(f"  Description: {desc}")
        for msg in res.get("messages", []):
            role    = msg.get("role", "?")
            content = msg.get("content", {})
            if isinstance(content, dict) and content.get("type") == "text":
                print(f"  [{role}] {content.get('text', '')}")
            else:
                print(f"  [{role}] {json.dumps(content, indent=2)}")

    elif call_type == "resource":
        print_resource_content(result)


def print_fuzz_summary(results: list):
    hits   = sum(1 for _, s, _ in results if s == "HIT")
    maybes = sum(1 for _, s, _ in results if s == "MAYBE")
    misses = sum(1 for _, s, _ in results if s == "miss")
    print(f"\n  done — [HIT] {hits} | [MAYBE] {maybes} | [miss] {misses}")
    if not hits and not maybes:
        print("  No hits found.")
