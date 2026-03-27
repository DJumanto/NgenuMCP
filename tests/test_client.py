from unittest.mock import MagicMock, patch

import pytest

from NgenuMCP.client import EnumClient


@pytest.fixture
def mock_http():
    with patch("NgenuMCP.client.Client") as MockClient:
        yield MockClient.return_value


def _rpc_response(result: dict, rid: int = 1):
    m = MagicMock()
    m.json.return_value = {"jsonrpc": "2.0", "id": rid, "result": result}
    m.raise_for_status = MagicMock()
    m.headers = {"content-type": "application/json"}
    return m


def test_initiate_session(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "test", "version": "1.0"}}
    )
    client = EnumClient("http://localhost/mcp")
    result = client.initiate_session()
    assert client._initialized is True
    assert result["result"]["protocolVersion"] == "2024-11-05"


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


def test_context_manager_closes(mock_http):
    mock_http.post.return_value = _rpc_response(
        {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}}
    )
    with EnumClient("http://localhost/mcp") as c:
        c.initiate_session()
    mock_http.close.assert_called_once()


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
