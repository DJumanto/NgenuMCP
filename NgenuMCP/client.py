import json

from httpx import Client, HTTPError

from .const import _ENUM_METHODS, _DEFAULT_HEADERS


def _parse_response(resp) -> dict:
    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise ValueError("No data line found in SSE response")
    return resp.json()


class EnumClient:
    def __init__(self, base_url: str, headers: dict = None):
        self.endpoint = base_url.rstrip("/")
        self.client = Client(verify=False, timeout=10.0, headers=_DEFAULT_HEADERS)
        if headers:
            self.client.headers.update(headers)
        self._request_id = 1
        self._initialized = False
        self._session_id = None

    def _next_id(self) -> int:
        rid = self._request_id
        self._request_id += 1
        return rid

    def _rpc(self, method: str, params: dict = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params or {}}
        headers = {"Mcp-Session-Id": self._session_id} if self._session_id else {}
        resp = self.client.post(self.endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        return _parse_response(resp)

    def _notify(self, method: str):
        try:
            headers = {"Mcp-Session-Id": self._session_id} if self._session_id else {}
            self.client.post(self.endpoint, json={"jsonrpc": "2.0", "method": method, "params": {}}, headers=headers)
        except HTTPError:
            pass

    def initiate_session(self) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "NgenuMCP", "version": "0.1.0"},
        }}
        resp = self.client.post(self.endpoint, json=payload)
        resp.raise_for_status()
        session_id = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        result = _parse_response(resp)
        self._notify("initialized")
        self._initialized = True
        return result

    def enumerate(self, only: set = None) -> dict:
        results = {}
        for category, methods in _ENUM_METHODS.items():
            if only and category not in only:
                continue
            results[category] = {}
            for method in methods:
                try:
                    results[category][method] = self._rpc(method)
                except Exception as e:
                    results[category][method] = {"error": str(e)}
        return results

    def start(self, only: set = None) -> dict:
        if not self._initialized:
            self.initiate_session()
        return self.enumerate(only=only)

    def call_tool(self, name: str, arguments: dict = None) -> dict:
        return self._rpc("tools/call", {"name": name, "arguments": arguments or {}})

    def get_prompt(self, name: str, arguments: dict = None) -> dict:
        return self._rpc("prompts/get", {"name": name, "arguments": arguments or {}})

    def read_resource(self, uri: str) -> dict:
        return self._rpc("resources/read", {"uri": uri})

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
