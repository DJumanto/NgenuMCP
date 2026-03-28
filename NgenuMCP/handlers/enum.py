import json

from NgenuMCP.display import print_results


def run(client, only: set, args):
    print("\nEnumerating...")
    results = client.enumerate(only=only or None)

    if args.raw:
        print(json.dumps(results, indent=2))
    elif args.o:
        with open(args.o, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults written to {args.o}")
    else:
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
        print_results(results, verbose)
