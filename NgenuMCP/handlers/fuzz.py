import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import product as cartesian

from NgenuMCP.display import (
    print_fuzz_prompt_result,
    print_fuzz_summary,
    print_fuzz_tool_result,
    print_resource_content,
)

FUZZ_MARKER_RE = re.compile(r'@@FUZZ\d+')

_BAD_ARGS_HINTS  = {"missing required", "validation error", "missing argument", "invalid argument", "invalid param"}
_NOT_FOUND_HINTS = {"not found", "does not exist", "no such file", "cannot find", "file not found",
                    "unknown resource", "resource not found", "not exist", "404", "no resource"}


def load_wordlist(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def _fuzz_status(response: dict, mode: str = "name") -> str:
    if mode == "args":
        if "result" in response:
            res = response["result"]
            if isinstance(res, dict) and res.get("isError"):
                return "MAYBE"
            return "HIT"
        if "error" in response:
            err = response["error"]
            msg = (err.get("message", "") if isinstance(err, dict) else str(err)).lower()
            if any(k in msg for k in _BAD_ARGS_HINTS):
                return "miss"
            return "MAYBE"
        return "miss"

    if "result" in response:
        res = response["result"]
        if isinstance(res, dict) and res.get("isError"):
            text = " ".join(
                c.get("text", "") for c in res.get("content", []) if isinstance(c, dict)
            ).lower()
            if any(k in text for k in _BAD_ARGS_HINTS):
                return "MAYBE"
            return "miss"
        contents_text = " ".join(
            item.get("text", "") for item in res.get("contents", []) if isinstance(item, dict)
        ).lower()
        if any(k in contents_text for k in _NOT_FOUND_HINTS):
            return "miss"
        return "HIT"

    if "error" in response:
        err  = response["error"]
        code = err.get("code") if isinstance(err, dict) else None
        msg  = (err.get("message", "") if isinstance(err, dict) else str(err)).lower()
        if any(k in msg for k in _BAD_ARGS_HINTS):
            return "MAYBE"
        if code == -32602:
            return "MAYBE"
    return "miss"


def _extract_error_msg(response: dict) -> str:
    if "error" in response:
        err = response["error"]
        return err.get("message", str(err)) if isinstance(err, dict) else str(err)
    if "result" in response:
        res = response["result"]
        if isinstance(res, dict) and res.get("isError"):
            parts = [c.get("text", "") for c in res.get("content", []) if isinstance(c, dict)]
            return " ".join(parts).strip()
    return ""


def _cast_word(word: str, fuzz_type: str):
    """Cast a wordlist string to the requested type before injecting into an argument."""
    if fuzz_type == "str":
        return word
    if fuzz_type == "int":
        return int(word)
    if fuzz_type == "float":
        return float(word)
    if fuzz_type == "bool":
        if word.lower() in ("true", "1", "yes"):
            return True
        if word.lower() in ("false", "0", "no"):
            return False
        raise ValueError(f"cannot cast {word!r} to bool")
    if fuzz_type == "json":
        return json.loads(word)
    for cast in (int, float):
        try:
            return cast(word)
        except ValueError:
            pass
    if word.lower() in ("true", "1", "yes"):
        return True
    if word.lower() in ("false", "0", "no"):
        return False
    try:
        parsed = json.loads(word)
        if isinstance(parsed, (dict, list)):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return word


def _find_markers(template) -> list:
    """Return @@FUZZn markers found in the template, sorted numerically by n."""
    found = set()
    if isinstance(template, dict):
        for v in template.values():
            found.update(_find_markers(v))
    elif isinstance(template, list):
        for item in template:
            found.update(_find_markers(item))
    elif isinstance(template, str):
        found.update(FUZZ_MARKER_RE.findall(template))
    return sorted(found, key=lambda m: int(m[6:]))


def _inject_markers(template, values: dict, fuzz_type: str):
    """Recursively replace @@FUZZn markers with values from the wordlist combo."""
    if isinstance(template, dict):
        return {k: _inject_markers(v, values, fuzz_type) for k, v in template.items()}
    if isinstance(template, list):
        return [_inject_markers(item, values, fuzz_type) for item in template]
    if isinstance(template, str):
        for marker, word in values.items():
            if template == marker:
                return _cast_word(word, fuzz_type)
            if marker in template:
                template = template.replace(marker, word)
        return template
    return template


def _load_marker_wordlists(markers: list, wl_paths: list) -> dict | None:
    """Load wordlists for each marker. Returns None and prints an error on failure."""
    marker_words = {}
    for i, marker in enumerate(markers):
        path = wl_paths[i] if i < len(wl_paths) else wl_paths[-1]
        try:
            marker_words[marker] = load_wordlist(path)
        except FileNotFoundError:
            print(f"[error] Wordlist not found: {path}")
            return None
    return marker_words


def _probe_resources(client, probes: list, threads: int, on_result=None) -> list:
    """Probe resource URIs in parallel. Returns list of (label, status, resp)."""
    def probe(label, uri):
        try:
            resp = client.read_resource(uri)
            return label, resp
        except Exception as e:
            return label, {"error": {"code": 0, "message": str(e)}}

    results = []
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(probe, lbl, uri): lbl for lbl, uri in probes}
        for future in as_completed(futures):
            label, resp = future.result()
            status = _fuzz_status(resp)
            results.append((label, status, resp))
            if on_result:
                on_result(label, status, resp)
    return results


def _probe_calls(client, probes: list, threads: int, target_type: str, name: str, on_result=None) -> list:
    """Probe tool or prompt calls in parallel. Returns list of (label, status, resp, injected_args)."""
    def probe(label, injected_args):
        try:
            if target_type == "tool":
                resp = client.call_tool(name, injected_args)
            else:
                resp = client.get_prompt(name, injected_args)
            return label, injected_args, resp
        except Exception as e:
            return label, injected_args, {"error": {"code": 0, "message": str(e)}}

    results = []
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(probe, lbl, ia): lbl for lbl, ia in probes}
        for future in as_completed(futures):
            label, injected_args, resp = future.result()
            status = _fuzz_status(resp, "args")
            results.append((label, status, resp, injected_args))
            if on_result:
                on_result(label, status, resp, injected_args)
    return results


def _run_resource_fuzz(client, args) -> int:
    uri_template = args.fuzz_uri
    markers      = _find_markers(uri_template)

    if not markers:
        print(f"[error] No @@FUZZn placeholders found in: {uri_template!r}")
        return 1

    wl_paths = args.wordlist or []
    if not wl_paths:
        print("[error] At least one -w WORDLIST is required with --fuzz-it")
        return 1

    marker_words = _load_marker_wordlists(markers, wl_paths)
    if marker_words is None:
        return 1

    probes = []
    for combo in cartesian(*[marker_words[m] for m in markers]):
        values = dict(zip(markers, combo))
        uri    = _inject_markers(uri_template, values, "str")
        label  = " | ".join(f"{m}={w}" for m, w in values.items())
        probes.append((label, uri))

    sizes = " x ".join(str(len(marker_words[m])) for m in markers)
    print(f"\n[FUZZING RESOURCES] {uri_template}")
    print(f"  markers : {' '.join(markers)}")
    print(f"  combos  : {sizes} = {len(probes)}")
    print(f"  threads : {args.threads}")

    if args.raw or args.o:
        results     = _probe_resources(client, probes, args.threads)
        fuzz_output = {
            "target"      : "resource",
            "uri_template": uri_template,
            "results": [{"label": lbl, "status": s, "response": r} for lbl, s, r in results],
        }
        if args.raw:
            print(json.dumps(fuzz_output, indent=2))
        else:
            with open(args.o, "w", encoding="utf-8") as f:
                json.dump(fuzz_output, f, indent=2)
            print(f"\nFuzz results written to {args.o}")
    else:
        def on_result(label, status, resp):
            if status == "HIT":
                print(f"  [HIT]   {label}")
                if args.show_output:
                    print_resource_content(resp, indent="    ")
            elif status == "MAYBE":
                msg = _extract_error_msg(resp)
                print(f"  [MAYBE] {label}" + (f"  ({msg})" if msg else ""))
            elif status == "miss" and args.show_miss:
                print(f"  [miss]  {label}")

        results = _probe_resources(client, probes, args.threads, on_result=on_result)
        print_fuzz_summary(results)

    return 0


def _run_arg_fuzz(client, args, target_type: str, name: str) -> int:
    """Fuzz a tool or prompt by iterating wordlists over @@FUZZn markers in the args template."""
    raw_template = args.fuzz_args  # raw text — JSON is parsed *after* marker substitution
    markers      = _find_markers(raw_template)

    if not markers:
        print(f"[error] No @@FUZZn placeholders found in --fuzz-args")
        return 1

    wl_paths = args.wordlist or []
    if not wl_paths:
        print("[error] At least one -w WORDLIST is required with --fuzz-it")
        return 1

    marker_words = _load_marker_wordlists(markers, wl_paths)
    if marker_words is None:
        return 1

    probes = []
    for combo in cartesian(*[marker_words[m] for m in markers]):
        values = dict(zip(markers, combo))
        raw    = raw_template
        for marker, word in values.items():
            raw = raw.replace(marker, word)
        try:
            injected = json.loads(raw)
        except json.JSONDecodeError as e:
            label = " | ".join(f"{m}={w}" for m, w in values.items())
            print(f"[error] Invalid JSON after substituting {label}: {e}")
            return 1
        label = " | ".join(f"{m}={w}" for m, w in values.items())
        probes.append((label, injected))

    sizes = " x ".join(str(len(marker_words[m])) for m in markers)
    print(f"\n[FUZZING {target_type.upper()}S] {name}")
    print(f"  markers : {' '.join(markers)}")
    print(f"  combos  : {sizes} = {len(probes)}")
    print(f"  threads : {args.threads}")

    _print_result = print_fuzz_tool_result if target_type == "tool" else print_fuzz_prompt_result

    if args.raw or args.o:
        results     = _probe_calls(client, probes, args.threads, target_type, name)
        fuzz_output = {
            "target"       : target_type,
            "name"         : name,
            "fuzz_template": raw_template,
            "results": [
                {"label": lbl, "injected_args": ia, "status": s, "response": r}
                for lbl, s, r, ia in results
            ],
        }
        if args.raw:
            print(json.dumps(fuzz_output, indent=2))
        else:
            with open(args.o, "w", encoding="utf-8") as f:
                json.dump(fuzz_output, f, indent=2)
            print(f"\nFuzz results written to {args.o}")
    else:
        def on_result(label, status, resp, injected_args):
            if status == "HIT":
                print(f"  [HIT]   {label}")
                if args.show_output:
                    _print_result(resp, indent="    ")
            elif status == "MAYBE":
                msg = _extract_error_msg(resp)
                print(f"  [MAYBE] {label}" + (f"  ({msg})" if msg else ""))
            elif status == "miss" and args.show_miss:
                print(f"  [miss]  {label}")

        results = _probe_calls(client, probes, args.threads, target_type, name, on_result=on_result)
        print_fuzz_summary(results)

    return 0


def run(client, args) -> int:
    if args.fuzz_target not in ("tool", "prompt", "resource"):
        print(f"[error] Invalid --fuzz-target: {args.fuzz_target!r} (must be 'tool', 'prompt', or 'resource')")
        return 1

    if args.fuzz_target in ("tool", "prompt"):
        fuzz_args = getattr(args, "fuzz_args", None)
        if not fuzz_args or fuzz_args == "{}":
            print(f"[error] --fuzz-args JSON is required for fuzzing {args.fuzz_target}s")
            return 1
        if isinstance(fuzz_args, str):
            if os.path.isfile(fuzz_args):
                try:
                    with open(fuzz_args, "r", encoding="utf-8") as f:
                        fuzz_args = f.read()
                except OSError as e:
                    print(f"[error] Cannot read --fuzz-args file: {e}")
                    return 1
            args.fuzz_args = fuzz_args  # keep as raw text — JSON parsed after substitution

        if args.fuzz_target == "tool":
            name = getattr(args, "call_tool", None)
            if not name:
                print("[error] --call-tool NAME is required when --fuzz-target is 'tool'")
                return 1
        else:
            name = getattr(args, "call_prompt", None)
            if not name:
                print("[error] --call-prompt NAME is required when --fuzz-target is 'prompt'")
                return 1

        return _run_arg_fuzz(client, args, args.fuzz_target, name)

    if not args.fuzz_uri:
        print("[error] --fuzz-uri URI_TEMPLATE is required with --fuzz-it")
        print('        Example: --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt')
        return 1

    return _run_resource_fuzz(client, args)
