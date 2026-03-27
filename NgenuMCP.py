import argparse
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from httpx import ConnectError, ConnectTimeout, ReadTimeout, TimeoutException

from NgenuMCP.client import EnumClient


BANNER = r"""
   ▄     ▄▀  ▄███▄      ▄     ▄   █▀▄▀█ ▄█▄    █ ▄▄
    █  ▄▀    █▀   ▀      █     █  █ █ █ █▀ ▀▄  █   █
██   █ █ ▀▄  ██▄▄    ██   █ █   █ █ ▄ █ █   ▀  █▀▀▀
█ █  █ █   █ █▄   ▄▀ █ █  █ █   █ █   █ █▄  ▄▀ █
█  █ █  ███  ▀███▀   █  █ █ █▄ ▄█    █  ▀███▀   █
█   ██               █   ██  ▀▀▀    ▀            ▀
                                    MCP ENUMERATOR
"""


def print_server_info(info: dict):
    si = info.get("serverInfo", {})
    caps = info.get("capabilities", {})
    proto = info.get("protocolVersion", "?")
    instructions = info.get("instructions", "")

    print(f"\n  Server  : {si.get('name', 'unknown')} v{si.get('version', '?')}")
    print(f"  Protocol: MCP {proto}")

    if caps:
        advertised = []
        if "tools" in caps:
            advertised.append(f"tools (listChanged={caps['tools'].get('listChanged', '?')})")
        if "prompts" in caps:
            advertised.append(f"prompts (listChanged={caps['prompts'].get('listChanged', '?')})")
        if "resources" in caps:
            advertised.append(
                f"resources (subscribe={caps['resources'].get('subscribe', '?')}, "
                f"listChanged={caps['resources'].get('listChanged', '?')})"
            )
        if advertised:
            print(f"  Capabilities: {', '.join(advertised)}")

    if instructions:
        print(f"  Instructions: {instructions}")


def print_tool_verbose(tool: dict):
    print(f"    Name       : {tool.get('name')}")
    print(f"    Description: {tool.get('description', '-')}")
    schema = tool.get("inputSchema", {})
    props = schema.get("properties", {})
    required = schema.get("required", [])
    if props:
        print(f"    Parameters :")
        for param, meta in props.items():
            req = " (required)" if param in required else " (optional)"
            ptype = meta.get("type", "any")
            pdesc = meta.get("description", "")
            print(f"      - {param} [{ptype}]{req}" + (f": {pdesc}" if pdesc else ""))


def print_prompt_verbose(prompt: dict):
    print(f"    Name       : {prompt.get('name')}")
    print(f"    Description: {prompt.get('description', '-')}")
    args = prompt.get("arguments", [])
    if args:
        print(f"    Arguments  :")
        for a in args:
            req = " (required)" if a.get("required") else " (optional)"
            print(f"      - {a['name']}{req}" + (f": {a.get('description', '')}" if a.get('description') else ""))


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

            result = response.get("result", {})
            tools = result.get("tools", [])
            prompts = result.get("prompts", [])
            resources = result.get("resources", [])
            templates = result.get("resourceTemplates", [])
            items = tools or prompts or resources or templates

            print(f"  {method}  ({len(items)} item{'s' if len(items) != 1 else ''})")

            v_tools = "tools" in verbose or "all" in verbose
            v_prompts = "prompts" in verbose or "all" in verbose
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


def parse_headers(raw: list) -> dict:
    headers = {}
    for h in raw or []:
        if ":" not in h:
            print(f"Invalid header '{h}', expected KEY:VALUE")
            sys.exit(1)
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


def main():
    print(BANNER)
    parser = argparse.ArgumentParser(prog="NgenuMCP", description="MCP server enumerator")
    parser.add_argument("url", help="Target MCP endpoint (e.g. http://host:3000/mcp)")
    parser.add_argument("-H", "--header", action="append", metavar="KEY:VALUE",
                        help="Extra HTTP header, repeatable")
    parser.add_argument("--ping", action="store_true",
                        help="Ping the server instead of enumerating")
    parser.add_argument("--no-init", action="store_true",
                        help="Skip MCP initialize handshake")
    parser.add_argument("--raw", action="store_true",
                        help="Print raw JSON output")
    parser.add_argument("-vt", action="store_true",
                        help="Verbose: show full tool schemas")
    parser.add_argument("-vp", action="store_true",
                        help="Verbose: show full prompt arguments")
    parser.add_argument("-vr", action="store_true",
                        help="Verbose: show full resource details")
    parser.add_argument("-vv", action="store_true",
                        help="Verbose: show full detail for everything")
    parser.add_argument("-to", action="store_true",
                        help="Enumerate tools only")
    parser.add_argument("-po", action="store_true",
                        help="Enumerate prompts only")
    parser.add_argument("-ro", action="store_true",
                        help="Enumerate resources only")
    args = parser.parse_args()

    verbose = set()
    if args.vv:
        verbose.add("all")
    else:
        if args.vt:
            verbose.add("tools")
        if args.vp:
            verbose.add("prompts")
        if args.vr:
            verbose.add("resources")

    only = set()
    if args.to:
        only.add("tools")
    if args.po:
        only.add("prompts")
    if args.ro:
        only.add("resources")

    headers = parse_headers(args.header)

    try:
        with EnumClient(args.url, headers) as client:
            if args.ping:
                resp = client._rpc("ping")
                print(f"[+] Host {args.url} is reachable 🤖🤖🤖" if "result" in resp else f"[!] Host {args.url} is not reachable ☠️☠️☠️: {resp}")
                return

            if not args.no_init:
                r = client.initiate_session()
                info = r.get("result", {})
                print_server_info(info)

            print("\nEnumerating...")
            only_filter = only or None
            results = client.enumerate(only=only_filter) if not args.no_init else client.start(only=only_filter)

            if args.raw:
                print(json.dumps(results, indent=2))
            else:
                print_results(results, verbose)

    except ConnectTimeout:
        print(f"[timeout] Connection to {args.url} timed out.")
        sys.exit(1)
    except ReadTimeout:
        print(f"[timeout] Server at {args.url} connected but did not respond in time.")
        sys.exit(1)
    except TimeoutException as e:
        print(f"[timeout] {e}")
        sys.exit(1)
    except ConnectError as e:
        msg = str(e)
        if "refused" in msg.lower():
            print(f"[refused] Connection refused — is the server running at {args.url}?")
        elif "name or service not known" in msg.lower() or "nodename nor servname" in msg.lower() or "getaddrinfo" in msg.lower():
            print(f"[dns] Could not resolve host from {args.url}")
        elif "network is unreachable" in msg.lower():
            print(f"[network] Network unreachable — check your connection.")
        else:
            print(f"[connect] {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"[parse] Unexpected response from server: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
