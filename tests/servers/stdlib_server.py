import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

TOOLS = [
    {
        "name": "port_scan",
        "description": "Scan TCP ports on a target host",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "ports": {"type": "string", "description": "Port range, e.g. 1-1024"},
            },
            "required": ["host"],
        },
    },
    {
        "name": "whois_lookup",
        "description": "Perform a WHOIS lookup on a domain or IP",
        "inputSchema": {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
    },
    {
        "name": "dns_resolve",
        "description": "Resolve DNS records for a domain",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string"},
                "record_type": {"type": "string", "enum": ["A", "AAAA", "MX", "TXT", "NS"]},
            },
            "required": ["domain"],
        },
    },
]

PROMPTS = [
    {
        "name": "recon_report",
        "description": "Generate a recon report for a target",
        "arguments": [{"name": "target", "description": "Target IP or domain", "required": True}],
    },
    {
        "name": "vuln_summary",
        "description": "Summarise discovered vulnerabilities",
        "arguments": [{"name": "findings", "description": "Raw findings text", "required": True}],
    },
]

RESOURCES = [
    {
        "uri": "file:///wordlists/common.txt",
        "name": "Common wordlist",
        "description": "Top 1000 common passwords and usernames",
        "mimeType": "text/plain",
    },
    {
        "uri": "file:///reports/last_scan.json",
        "name": "Last scan report",
        "description": "Most recent enumeration output",
        "mimeType": "application/json",
    },
]

RESOURCE_TEMPLATES = [
    {
        "uriTemplate": "file:///reports/{scan_id}.json",
        "name": "Scan report by ID",
        "description": "Retrieve a specific scan report",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "http://target/{path}",
        "name": "Target path",
        "description": "Access a path on the target",
        "mimeType": "text/html",
    },
]

RESOURCE_CONTENT = {
    "file:///wordlists/common.txt": ("text/plain", "admin\npassword\n123456\nroot\nguest"),
    "file:///reports/last_scan.json": ("application/json", '{"scan_id":"abc123","target":"example.com"}'),
}

_TOOL_INDEX   = {t["name"]: t for t in TOOLS}
_PROMPT_INDEX = {p["name"]: p for p in PROMPTS}


def _call_tool(params):
    name = params.get("name", "")
    args = params.get("arguments", {})
    tool = _TOOL_INDEX.get(name)
    if not tool:
        return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
    missing = [r for r in tool["inputSchema"].get("required", []) if r not in args]
    if missing:
        return {"isError": True, "content": [{"type": "text", "text": f"Missing required: {', '.join(missing)}"}]}
    return {"isError": False, "content": [{"type": "text", "text": f"{name} result for {json.dumps(args)}"}]}


def _get_prompt(params):
    name   = params.get("name", "")
    args   = params.get("arguments", {})
    prompt = _PROMPT_INDEX.get(name)
    if not prompt:
        raise ValueError(f"Unknown prompt: {name}")
    return {
        "description": prompt["description"],
        "messages": [{"role": "user", "content": {"type": "text", "text": f"{name}: {json.dumps(args)}"}}],
    }


def _read_resource(params):
    uri     = params.get("uri", "")
    content = RESOURCE_CONTENT.get(uri)
    if content:
        mime, text = content
        return {"contents": [{"uri": uri, "mimeType": mime, "text": text}]}
    if uri.startswith("file:///reports/") and uri.endswith(".json"):
        scan_id = uri.split("/")[-1].replace(".json", "")
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                               "text": json.dumps({"scan_id": scan_id, "status": "completed"})}]}
    raise ValueError(f"Resource not found: {uri}")


DISPATCH = {
    "initialize": lambda p: {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {"listChanged": False},
            "prompts": {"listChanged": False},
            "resources": {"listChanged": False, "subscribe": False},
        },
        "serverInfo": {"name": "NgenuMCP-SampleServer", "version": "1.0.0"},
    },
    "ping":                    lambda p: {},
    "tools/list":              lambda p: {"tools": TOOLS},
    "prompts/list":            lambda p: {"prompts": PROMPTS},
    "resources/list":          lambda p: {"resources": RESOURCES},
    "resources/templates/list": lambda p: {"resourceTemplates": RESOURCE_TEMPLATES},
    "tools/call":              _call_tool,
    "prompts/get":             _get_prompt,
    "resources/read":          _read_resource,
}


class MCPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)

        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"})
            return

        method = msg.get("method", "")
        rid    = msg.get("id")

        if rid is None:
            self._send(200, {})
            return

        handler = DISPATCH.get(method)
        if handler is None:
            payload = {"jsonrpc": "2.0", "id": rid,
                       "error": {"code": -32601, "message": f"Method not found: {method}"}}
        else:
            try:
                result  = handler(msg.get("params", {}))
                payload = {"jsonrpc": "2.0", "id": rid, "result": result}
            except Exception as exc:
                payload = {"jsonrpc": "2.0", "id": rid,
                           "error": {"code": -32603, "message": str(exc)}}

        self._send(200, payload)

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class SampleMCPServer:
    def __init__(self, host="127.0.0.1", port=0):
        self._server = HTTPServer((host, port), MCPHandler)
        self.host    = host
        self.port    = self._server.server_address[1]
        self._thread = None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    def start(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self._server.shutdown()


if __name__ == "__main__":
    srv = SampleMCPServer(port=5173)
    srv.start()
    print(f"Sample MCP server running at {srv.url}")
    try:
        input("Press Enter to stop...\n")
    finally:
        srv.stop()
