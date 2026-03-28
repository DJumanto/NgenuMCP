from types import SimpleNamespace

import pytest

from NgenuMCP.client import EnumClient
from NgenuMCP.handlers import call as call_handler
from NgenuMCP.handlers import enum as enum_handler
from NgenuMCP.handlers import fuzz as fuzz_handler
from tests.servers.fastmcp_server import FastMCPTestServer
from tests.servers.stdlib_server import SampleMCPServer

pytestmark = pytest.mark.integration


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def stdlib_server():
    srv = SampleMCPServer()
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def fastmcp_server():
    srv = FastMCPTestServer()
    srv.start(wait=2.0)
    yield srv
    srv.stop()


@pytest.fixture()
def stdlib_client(stdlib_server):
    c = EnumClient(stdlib_server.url)
    c.initiate_session()
    yield c
    c.close()


@pytest.fixture()
def fastmcp_client(fastmcp_server):
    c = EnumClient(fastmcp_server.url)
    c.initiate_session()
    yield c
    c.close()


def _fuzz_args(**kwargs):
    defaults = dict(fuzz_uri=None, wordlist=None, threads=4,
                    show_output=False, show_miss=False, raw=False, o=None)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Stdlib server — enumeration ───────────────────────────────────────────────

class TestStdlibEnum:
    def test_handshake(self, stdlib_client):
        assert stdlib_client._initialized is True

    def test_ping(self, stdlib_client):
        assert "result" in stdlib_client._rpc("ping")

    def test_tools_list(self, stdlib_client):
        tools = stdlib_client._rpc("tools/list")["result"]["tools"]
        assert {t["name"] for t in tools} == {"port_scan", "whois_lookup", "dns_resolve"}
        for t in tools:
            assert "inputSchema" in t and "description" in t

    def test_prompts_list(self, stdlib_client):
        prompts = stdlib_client._rpc("prompts/list")["result"]["prompts"]
        assert {p["name"] for p in prompts} == {"recon_report", "vuln_summary"}
        for p in prompts:
            assert len(p["arguments"]) > 0

    def test_resources_list(self, stdlib_client):
        uris = {r["uri"] for r in stdlib_client._rpc("resources/list")["result"]["resources"]}
        assert "file:///wordlists/common.txt" in uris

    def test_resource_templates(self, stdlib_client):
        templates = stdlib_client._rpc("resources/templates/list")["result"]["resourceTemplates"]
        assert len(templates) == 2

    def test_unknown_method_error(self, stdlib_client):
        r = stdlib_client._rpc("nonexistent/method")
        assert r["error"]["code"] == -32601

    def test_full_enum(self, stdlib_client):
        results = stdlib_client.start()
        assert set(results.keys()) == {"prompts", "resources", "tools"}
        for category, methods in results.items():
            for method, r in methods.items():
                assert "error" not in r, f"{method}: {r}"


# ── Stdlib server — call methods ──────────────────────────────────────────────

class TestStdlibCall:
    def test_call_tool_returns_content(self, stdlib_client):
        r = stdlib_client.call_tool("port_scan", {"host": "10.0.0.1"})
        res = r["result"]
        assert res["isError"] is False
        assert res["content"][0]["type"] == "text"
        assert "port_scan" in res["content"][0]["text"]

    def test_call_tool_missing_required_returns_is_error(self, stdlib_client):
        r = stdlib_client.call_tool("port_scan", {})
        assert r["result"]["isError"] is True
        assert "host" in r["result"]["content"][0]["text"].lower()

    def test_call_tool_unknown_returns_is_error(self, stdlib_client):
        r = stdlib_client.call_tool("nonexistent_tool", {})
        assert r["result"]["isError"] is True

    def test_get_prompt_returns_messages(self, stdlib_client):
        r = stdlib_client.get_prompt("recon_report", {"target": "example.com"})
        msgs = r["result"]["messages"]
        assert len(msgs) > 0
        assert msgs[0]["role"] == "user"
        assert "example.com" in msgs[0]["content"]["text"]

    def test_get_prompt_unknown_returns_error(self, stdlib_client):
        r = stdlib_client.get_prompt("nonexistent_prompt", {})
        assert "error" in r

    def test_read_static_resource(self, stdlib_client):
        r = stdlib_client.read_resource("file:///wordlists/common.txt")
        contents = r["result"]["contents"]
        assert len(contents) == 1
        assert contents[0]["mimeType"] == "text/plain"
        assert len(contents[0]["text"]) > 0

    def test_read_resource_not_found_returns_error(self, stdlib_client):
        r = stdlib_client.read_resource("file:///does/not/exist.txt")
        assert "error" in r


# ── FastMCP server — enumeration ──────────────────────────────────────────────

class TestFastMCPEnum:
    def test_handshake(self, fastmcp_client):
        assert fastmcp_client._initialized is True

    def test_ping(self, fastmcp_client):
        assert "result" in fastmcp_client._rpc("ping")

    def test_tools_list(self, fastmcp_client):
        tools = fastmcp_client._rpc("tools/list")["result"]["tools"]
        assert {t["name"] for t in tools} == {"port_scan", "whois_lookup", "dns_resolve", "http_probe"}
        for t in tools:
            assert t["inputSchema"]["type"] == "object"
        port_scan = next(t for t in tools if t["name"] == "port_scan")
        assert "host" in port_scan["inputSchema"]["required"]
        assert "ports" not in port_scan["inputSchema"].get("required", [])

    def test_prompts_list(self, fastmcp_client):
        prompts = fastmcp_client._rpc("prompts/list")["result"]["prompts"]
        assert {p["name"] for p in prompts} == {"recon_report", "vuln_summary", "attack_surface"}
        recon = next(p for p in prompts if p["name"] == "recon_report")
        assert {a["name"]: a for a in recon["arguments"]}["target"]["required"] is True

    def test_resources_list(self, fastmcp_client):
        resources = fastmcp_client._rpc("resources/list")["result"]["resources"]
        uris = {r["uri"] for r in resources}
        assert {"file:///wordlists/common.txt", "file:///reports/last_scan.json",
                "config://server/settings", "file:///internal/credentials.txt",
                "file:///internal/notes.txt", "file:///internal/employees.csv",
                "file:///reports/pentest_report.pdf"} == uris

    def test_resource_templates(self, fastmcp_client):
        templates = fastmcp_client._rpc("resources/templates/list")["result"]["resourceTemplates"]
        uri_templates = {t["uriTemplate"] for t in templates}
        assert "file:///reports/{scan_id}.json" in uri_templates
        assert "file:///internal/{filename}.txt" in uri_templates
        assert "db://users/{user_id}/profile" in uri_templates
        for t in templates:
            assert "uriTemplate" in t and "description" in t and "mimeType" in t

    def test_full_enum(self, fastmcp_client):
        results = fastmcp_client.start()
        assert set(results.keys()) == {"prompts", "resources", "tools"}
        for category, methods in results.items():
            for method, r in methods.items():
                assert "error" not in r, f"{method}: {r}"
        assert len(results["tools"]["tools/list"]["result"]["tools"]) == 4
        assert len(results["prompts"]["prompts/list"]["result"]["prompts"]) == 3
        assert len(results["resources"]["resources/list"]["result"]["resources"]) == 7

    def test_auto_initializes(self, fastmcp_server):
        c = EnumClient(fastmcp_server.url)
        assert not c._initialized
        results = c.start()
        assert c._initialized
        assert "tools" in results
        c.close()


# ── FastMCP server — call methods ─────────────────────────────────────────────

class TestFastMCPCall:
    def test_call_tool_required_arg(self, fastmcp_client):
        r = fastmcp_client.call_tool("port_scan", {"host": "10.0.0.1"})
        content = r["result"]["content"]
        assert content[0]["type"] == "text"
        assert "10.0.0.1" in content[0]["text"]

    def test_call_tool_with_optional_arg(self, fastmcp_client):
        r = fastmcp_client.call_tool("port_scan", {"host": "10.0.0.1", "ports": "80,443"})
        assert "80,443" in r["result"]["content"][0]["text"]

    def test_call_tool_dict_response(self, fastmcp_client):
        r = fastmcp_client.call_tool("whois_lookup", {"target": "example.com"})
        assert r["result"]["content"][0]["type"] == "text"

    def test_call_tool_list_response(self, fastmcp_client):
        r = fastmcp_client.call_tool("dns_resolve", {"domain": "example.com"})
        assert r["result"]["content"][0]["type"] == "text"

    def test_get_prompt_with_required_arg(self, fastmcp_client):
        r = fastmcp_client.get_prompt("recon_report", {"target": "example.com"})
        msgs = r["result"]["messages"]
        assert any("example.com" in m["content"]["text"] for m in msgs)

    def test_get_prompt_optional_bool_arg(self, fastmcp_client):
        # FastMCP serialises bool args as strings over JSON-RPC
        r = fastmcp_client.get_prompt("attack_surface", {"domain": "example.com", "include_subdomains": "true"})
        assert r["result"]["messages"][0]["content"]["type"] == "text"

    def test_get_prompt_default_optional(self, fastmcp_client):
        r = fastmcp_client.get_prompt("attack_surface", {"domain": "example.com"})
        assert "result" in r

    def test_read_static_resource_text(self, fastmcp_client):
        r = fastmcp_client.read_resource("file:///wordlists/common.txt")
        contents = r["result"]["contents"]
        assert contents[0]["mimeType"] == "text/plain"
        assert "admin" in contents[0]["text"]

    def test_read_static_resource_json(self, fastmcp_client):
        r = fastmcp_client.read_resource("file:///reports/last_scan.json")
        text = r["result"]["contents"][0]["text"]
        import json as _json
        data = _json.loads(text)
        assert "scan_id" in data

    def test_read_template_resource_with_var(self, fastmcp_client):
        r = fastmcp_client.read_resource("file:///internal/credentials.txt")
        assert r["result"]["contents"][0]["mimeType"] == "text/plain"

    def test_read_template_with_filled_param(self, fastmcp_client):
        r = fastmcp_client.read_resource("db://users/42/profile")
        import json as _json
        data = _json.loads(r["result"]["contents"][0]["text"])
        assert data["user_id"] == "42"

    def test_read_unicode_resource(self, fastmcp_client):
        r = fastmcp_client.read_resource("file:///internal/nosferatu.txt")
        text = r["result"]["contents"][0]["text"]
        assert len(text) > 0

    def test_read_nonexistent_file_returns_not_found_text(self, fastmcp_client):
        r = fastmcp_client.read_resource("file:///internal/nonexistent.txt")
        text = r["result"]["contents"][0]["text"]
        assert "not found" in text.lower() or "nonexistent" in text.lower()


# ── FastMCP server — fuzzing ──────────────────────────────────────────────────

class TestFastMCPFuzz:
    def test_known_files_are_hits(self, fastmcp_client):
        from NgenuMCP.handlers.fuzz import _fuzz_status
        for name in ("credentials", "notes"):   # employees is .csv, not .txt
            uri  = f"file:///internal/{name}.txt"
            resp = fastmcp_client.read_resource(uri)
            assert _fuzz_status(resp) == "HIT", f"{uri} should be HIT"

    def test_unknown_file_is_miss(self, fastmcp_client):
        from NgenuMCP.handlers.fuzz import _fuzz_status
        resp = fastmcp_client.read_resource("file:///internal/nonexistent.txt")
        assert _fuzz_status(resp) == "miss"

    def test_fuzz_run_finds_hits(self, fastmcp_server, tmp_path, capsys):
        wl = tmp_path / "names.txt"
        wl.write_text("credentials\nnotes\nnonexistent\n", encoding="utf-8")

        client = EnumClient(fastmcp_server.url)
        client.initiate_session()

        rc = fuzz_handler.run(client, _fuzz_args(
            fuzz_uri="file:///internal/@@FUZZ1.txt",
            wordlist=[str(wl)],
        ))
        client.close()

        assert rc == 0
        out = capsys.readouterr().out
        assert "[HIT]" in out
        assert "[HIT] 2" in out

    def test_fuzz_run_show_miss(self, fastmcp_server, tmp_path, capsys):
        wl = tmp_path / "names.txt"
        wl.write_text("credentials\nnonexistent\n", encoding="utf-8")

        client = EnumClient(fastmcp_server.url)
        client.initiate_session()

        rc = fuzz_handler.run(client, _fuzz_args(
            fuzz_uri="file:///internal/@@FUZZ1.txt",
            wordlist=[str(wl)],
            show_miss=True,
        ))
        client.close()

        assert rc == 0
        assert "[miss]" in capsys.readouterr().out

    def test_fuzz_run_show_output(self, fastmcp_server, tmp_path, capsys):
        wl = tmp_path / "names.txt"
        wl.write_text("credentials\n", encoding="utf-8")

        client = EnumClient(fastmcp_server.url)
        client.initiate_session()

        fuzz_handler.run(client, _fuzz_args(
            fuzz_uri="file:///internal/@@FUZZ1.txt",
            wordlist=[str(wl)],
            show_output=True,
        ))
        client.close()

        out = capsys.readouterr().out
        assert "[HIT]" in out
        assert "file:///internal/credentials.txt" in out

    def test_fuzz_file_output(self, fastmcp_server, tmp_path):
        wl    = tmp_path / "names.txt"
        out_f = tmp_path / "results.json"
        wl.write_text("credentials\nnotes\n", encoding="utf-8")

        client = EnumClient(fastmcp_server.url)
        client.initiate_session()

        fuzz_handler.run(client, _fuzz_args(
            fuzz_uri="file:///internal/@@FUZZ1.txt",
            wordlist=[str(wl)],
            o=str(out_f),
        ))
        client.close()

        import json
        data = json.loads(out_f.read_text(encoding="utf-8"))
        assert data["uri_template"] == "file:///internal/@@FUZZ1.txt"
        hits = [r for r in data["results"] if r["status"] == "HIT"]
        assert len(hits) == 2


# ── Handler output ────────────────────────────────────────────────────────────

class TestHandlerOutput:
    def _base_args(self, **kwargs):
        defaults = dict(raw=False, o=None, vt=False, vp=False, vr=False, vv=False)
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_enum_handler_stdout(self, fastmcp_client, capsys):
        enum_handler.run(fastmcp_client, set(), self._base_args())
        out = capsys.readouterr().out
        assert "port_scan" in out
        assert "recon_report" in out

    def test_enum_handler_filter_tools_only(self, fastmcp_client, capsys):
        enum_handler.run(fastmcp_client, {"tools"}, self._base_args())
        out = capsys.readouterr().out
        assert "port_scan" in out
        assert "recon_report" not in out

    def test_enum_handler_verbose_tools(self, fastmcp_client, capsys):
        enum_handler.run(fastmcp_client, {"tools"}, self._base_args(vt=True))
        out = capsys.readouterr().out
        assert "host" in out
        assert "required" in out

    def test_call_handler_tool_output(self, fastmcp_client, capsys):
        call_handler.run(fastmcp_client, "tool", "port_scan", {"host": "10.0.0.1"},
                         self._base_args())
        assert "10.0.0.1" in capsys.readouterr().out

    def test_call_handler_prompt_output(self, fastmcp_client, capsys):
        call_handler.run(fastmcp_client, "prompt", "recon_report", {"target": "example.com"},
                         self._base_args())
        assert "example.com" in capsys.readouterr().out

    def test_call_handler_resource_output(self, fastmcp_client, capsys):
        call_handler.run(fastmcp_client, "resource", "file:///wordlists/common.txt", {},
                         self._base_args())
        out = capsys.readouterr().out
        assert "file:///wordlists/common.txt" in out
        assert "admin" in out

    def test_call_handler_raw_output(self, fastmcp_client, capsys):
        call_handler.run(fastmcp_client, "tool", "port_scan", {"host": "10.0.0.1"},
                         self._base_args(raw=True))
        out = capsys.readouterr().out
        import json
        # The "Calling..." line may contain a Python dict literal with {}, so find the JSON block
        json_start = out.index("\n{") + 1
        data = json.loads(out[json_start:])
        assert "result" in data

    def test_call_handler_file_output(self, fastmcp_client, tmp_path):
        out_f = tmp_path / "result.json"
        call_handler.run(fastmcp_client, "tool", "port_scan", {"host": "10.0.0.1"},
                         self._base_args(o=str(out_f)))
        import json
        data = json.loads(out_f.read_text(encoding="utf-8"))
        assert "result" in data
