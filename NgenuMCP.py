"""
NgenuMCP — MCP server enumerator and interact tool.
Connects to any MCP-compatible HTTP endpoint and enumerates tools, prompts,
and resources. Supports calling methods directly and fuzzing resource URIs.
"""
import argparse
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from httpx import ConnectError, ConnectTimeout, ReadTimeout, TimeoutException

from NgenuMCP.client import EnumClient
from NgenuMCP.display import BANNER, print_server_info
from NgenuMCP.handlers import call as call_handler
from NgenuMCP.handlers import enum as enum_handler
from NgenuMCP.handlers import fuzz as fuzz_handler


def _parse_headers(raw: list) -> dict:
    headers = {}
    for h in raw or []:
        if ":" not in h:
            print(f"Invalid header '{h}', expected KEY:VALUE")
            sys.exit(1)
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="NgenuMCP", description="MCP server enumerator")
    parser.add_argument("url", help="Target MCP endpoint (e.g. http://host:3000/mcp)")
    parser.add_argument("-H", "--header", action="append", metavar="KEY:VALUE",
                        help="Extra HTTP header, repeatable")
    parser.add_argument("-o", metavar="FILE", default=None,
                        help="Output file for JSON results (default: stdout)")
    parser.add_argument("--ping",    action="store_true", help="Ping the server")
    parser.add_argument("--no-init", action="store_true", help="Skip MCP initialize handshake")
    parser.add_argument("--raw",     action="store_true", help="Print raw JSON output")

    enum_group = parser.add_argument_group("enumeration filters")
    enum_group.add_argument("-to", action="store_true", help="Tools only")
    enum_group.add_argument("-po", action="store_true", help="Prompts only")
    enum_group.add_argument("-ro", action="store_true", help="Resources only")

    verb_group = parser.add_argument_group("verbosity")
    verb_group.add_argument("-vt", action="store_true", help="Verbose: full tool schemas")
    verb_group.add_argument("-vp", action="store_true", help="Verbose: full prompt arguments")
    verb_group.add_argument("-vr", action="store_true", help="Verbose: full resource details")
    verb_group.add_argument("-vv", action="store_true", help="Verbose: everything")

    call_grp = parser.add_mutually_exclusive_group()
    call_grp.add_argument("--call-tool",     metavar="NAME", help="Call a tool by name")
    call_grp.add_argument("--call-prompt",   metavar="NAME", help="Get a prompt by name")
    call_grp.add_argument("--call-resource", metavar="URI",  help="Read a resource by URI")
    parser.add_argument("--args", metavar="JSON", default="{}",
                        help="Arguments as JSON object for --call-tool / --call-prompt")

    fuzz_group = parser.add_argument_group("fuzzing")
    fuzz_group.add_argument("--fuzz-it",  action="store_true",
                            help="Fuzz resource URIs using a URI template")
    fuzz_group.add_argument("--fuzz-uri", metavar="URI_TEMPLATE",
                            help="URI template with @@FUZZ1 / @@FUZZn placeholders (required with --fuzz-it)")
    fuzz_group.add_argument("-w", "--wordlist", metavar="FILE", action="append",
                            help="Wordlist file, repeatable — nth -w feeds @@FUZZn")
    fuzz_group.add_argument("--threads", metavar="N", type=int, default=4,
                            help="Number of threads for fuzzing (default: 4)")
    fuzz_group.add_argument("--show-output", action="store_true",
                            help="Show resource content for HIT results")
    fuzz_group.add_argument("--show-miss",   action="store_true",
                            help="Show miss results")

    return parser


def main():
    print(BANNER)
    args    = _build_parser().parse_args()
    headers = _parse_headers(args.header)

    call_type   = None
    call_target = None
    if args.call_tool:
        call_type, call_target = "tool", args.call_tool
    elif args.call_prompt:
        call_type, call_target = "prompt", args.call_prompt
    elif args.call_resource:
        call_type, call_target = "resource", args.call_resource

    call_args = {}
    if call_type in ("tool", "prompt") and args.args != "{}":
        try:
            call_args = json.loads(args.args)
            if not isinstance(call_args, dict):
                raise ValueError("expected a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[error] Invalid --args JSON: {e}")
            sys.exit(1)

    only = {cat for flag, cat in [(args.to, "tools"), (args.po, "prompts"), (args.ro, "resources")] if flag}

    try:
        with EnumClient(args.url, headers) as client:
            if args.ping:
                client.initiate_session()
                resp = client._rpc("ping")
                status = "reachable" if "result" in resp else f"unreachable: {resp}"
                print(f"[+] {args.url} — {status}")
                return

            if not args.no_init:
                r = client.initiate_session()
                print_server_info(r.get("result", {}))

            if args.fuzz_it:
                rc = fuzz_handler.run(client, args)
                if rc:
                    sys.exit(rc)
            elif call_type:
                call_handler.run(client, call_type, call_target, call_args, args)
            else:
                enum_handler.run(client, only, args)

    except ConnectTimeout:
        print(f"[timeout] Connection to {args.url} timed out.")
        sys.exit(1)
    except ReadTimeout:
        print(f"[timeout] Server at {args.url} did not respond in time.")
        sys.exit(1)
    except TimeoutException as e:
        print(f"[timeout] {e}")
        sys.exit(1)
    except ConnectError as e:
        msg = str(e).lower()
        if "refused" in msg:
            print(f"[refused] Connection refused — is the server running at {args.url}?")
        elif any(k in msg for k in ("name or service not known", "nodename nor servname", "getaddrinfo")):
            print(f"[dns] Could not resolve host from {args.url}")
        elif "network is unreachable" in msg:
            print("[network] Network unreachable.")
        else:
            print(f"[connect] {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"[parse] Unexpected response: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
