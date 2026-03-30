import json

from NgenuMCP.display import print_call_result


def run(client, call_type: str, call_target: str, call_args: dict, args):
    print(f"\nCalling {call_type}: {call_target}" + (f" {call_args}" if call_args else "") + " ...")

    if call_type == "tool":
        print(call_args)
        result = client.call_tool(call_target, call_args)
    elif call_type == "prompt":
        result = client.get_prompt(call_target, call_args)
    else:
        result = client.read_resource(call_target)

    if args.raw:
        print(json.dumps(result, indent=2))
    elif args.o:
        with open(args.o, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Result written to {args.o}")
    else:
        print_call_result(result, call_type)
