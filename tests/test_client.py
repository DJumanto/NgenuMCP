from unittest.mock import MagicMock, patch

import pytest

from NgenuMCP.client import EnumClient


@pytest.fixture
def mock_http():
    with patch("NgenuMCP.client.Client") as MockClient:
        yield MockClient.return_value


def _rpc_response(result: dict, rid: int = 1, session_id: str = None):
    m = MagicMock()
    m.json.return_value = {"jsonrpc": "2.0", "id": rid, "result": result}
    m.raise_for_status = MagicMock()
    headers = {"content-type": "application/json"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    m.headers = headers
    return m


# ── Session ───────────────────────────────────────────────────────────────────

def test_initiate_session(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "test", "version": "1.0"}}
    )
    client = EnumClient("http://localhost/mcp")
    result = client.initiate_session()
    assert client._initialized is True
    assert result["result"]["protocolVersion"] == "2024-11-05"


def test_session_id_captured_and_forwarded(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}},
        session_id="sess-abc",
    )
    client = EnumClient("http://localhost/mcp")
    client.initiate_session()
    assert client._session_id == "sess-abc"

    mock_http.post.return_value = _rpc_response({"tools": []}, rid=2)
    client._rpc("tools/list")
    _, call_kwargs = mock_http.post.call_args
    assert call_kwargs.get("headers", {}).get("Mcp-Session-Id") == "sess-abc"


def test_context_manager_closes(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}}
    )
    with EnumClient("http://localhost/mcp") as c:
        c.initiate_session()
    mock_http.close.assert_called_once()


# ── Enumeration ───────────────────────────────────────────────────────────────

def test_start_enumerates_all_categories(mock_http):
    responses = [
        _rpc_response({"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}}, 1),
        MagicMock(raise_for_status=MagicMock(), headers={"content-type": "application/json"}),
        _rpc_response({"prompts": []}, 2),
        _rpc_response({"resources": []}, 3),
        _rpc_response({"resourceTemplates": []}, 4),
        _rpc_response({"tools": [{"name": "echo", "description": "Echo", "inputSchema": {}}]}, 5),
    ]
    mock_http.post.side_effect = responses
    results = EnumClient("http://localhost/mcp").start()
    assert set(results.keys()) == {"prompts", "resources", "tools"}
    assert results["tools"]["tools/list"]["result"]["tools"][0]["name"] == "echo"


def test_start_captures_http_errors(mock_http):
    from httpx import HTTPError

    init = _rpc_response({"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}}, 1)

    def side_effect(url, **kwargs):
        method = kwargs.get("json", {}).get("method", "")
        if method == "initialize":
            return init
        if method == "initialized":
            return MagicMock(raise_for_status=MagicMock(), headers={"content-type": "application/json"})
        raise HTTPError("refused")

    mock_http.post.side_effect = side_effect
    results = EnumClient("http://localhost/mcp").start()
    for category in results.values():
        for r in category.values():
            assert "error" in r


def test_enumerate_skips_handshake(mock_http):
    mock_http.post.side_effect = [
        _rpc_response({"prompts": []}, 1),
        _rpc_response({"resources": []}, 2),
        _rpc_response({"resourceTemplates": []}, 3),
        _rpc_response({"tools": []}, 4),
    ]
    client = EnumClient("http://localhost/mcp")
    results = client.enumerate()
    assert mock_http.post.call_count == 4
    assert client._initialized is False


def test_enumerate_only_filter(mock_http):
    mock_http.post.return_value = _rpc_response({"tools": []}, 1)
    client = EnumClient("http://localhost/mcp")
    results = client.enumerate(only={"tools"})
    assert list(results.keys()) == ["tools"]
    assert mock_http.post.call_count == 1


# ── Call methods ──────────────────────────────────────────────────────────────

def test_call_tool(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"content": [{"type": "text", "text": "scan result"}], "isError": False}, rid=1
    )
    client = EnumClient("http://localhost/mcp")
    result = client.call_tool("port_scan", {"host": "10.0.0.1"})
    assert result["result"]["content"][0]["text"] == "scan result"
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["method"] == "tools/call"
    assert payload["params"]["name"] == "port_scan"
    assert payload["params"]["arguments"]["host"] == "10.0.0.1"


def test_call_tool_no_args(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"content": [{"type": "text", "text": "ok"}], "isError": False}, rid=1
    )
    client = EnumClient("http://localhost/mcp")
    client.call_tool("whoami")
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["params"]["arguments"] == {}


def test_get_prompt(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"messages": [{"role": "user", "content": {"type": "text", "text": "report for example.com"}}]}, rid=1
    )
    client = EnumClient("http://localhost/mcp")
    result = client.get_prompt("recon_report", {"target": "example.com"})
    assert result["result"]["messages"][0]["role"] == "user"
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["method"] == "prompts/get"
    assert payload["params"]["name"] == "recon_report"
    assert payload["params"]["arguments"]["target"] == "example.com"


def test_read_resource(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"contents": [{"uri": "file:///wordlists/common.txt", "mimeType": "text/plain", "text": "admin\npassword"}]},
        rid=1,
    )
    client = EnumClient("http://localhost/mcp")
    result = client.read_resource("file:///wordlists/common.txt")
    assert result["result"]["contents"][0]["text"] == "admin\npassword"
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["method"] == "resources/read"
    assert payload["params"]["uri"] == "file:///wordlists/common.txt"


# ── SSE transport ─────────────────────────────────────────────────────────────

def test_sse_response_parsed(mock_http):
    sse_payload = '{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}'
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.headers = {"content-type": "text/event-stream"}
    m.text = f"event: message\ndata: {sse_payload}\n\n"
    mock_http.post.return_value = m
    client = EnumClient("http://localhost/mcp")
    result = client._rpc("tools/list")
    assert result["result"]["tools"] == []
