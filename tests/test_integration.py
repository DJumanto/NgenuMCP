import pytest

from NgenuMCP.client import EnumClient
from tests.servers.stdlib_server import SampleMCPServer
from tests.servers.fastmcp_server import FastMCPTestServer

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
    yield c
    c.close()


@pytest.fixture()
def fastmcp_client(fastmcp_server):
    c = EnumClient(fastmcp_server.url)
    yield c
    c.close()


# ── Stdlib server tests ───────────────────────────────────────────────────────

class TestStdlibServer:
    def test_handshake(self, stdlib_client):
        r = stdlib_client.initiate_session()
        assert r["result"]["serverInfo"]["name"] == "NgenuMCP-SampleServer"
        assert stdlib_client._initialized is True

    def test_ping(self, stdlib_client):
        stdlib_client.initiate_session()
        assert "result" in stdlib_client._rpc("ping")

    def test_tools(self, stdlib_client):
        stdlib_client.initiate_session()
        tools = stdlib_client._rpc("tools/list")["result"]["tools"]
        assert {t["name"] for t in tools} == {"port_scan", "whois_lookup", "dns_resolve"}
        for t in tools:
            assert "inputSchema" in t and "description" in t

    def test_prompts(self, stdlib_client):
        stdlib_client.initiate_session()
        prompts = stdlib_client._rpc("prompts/list")["result"]["prompts"]
        assert {p["name"] for p in prompts} == {"recon_report", "vuln_summary"}
        for p in prompts:
            assert len(p["arguments"]) > 0

    def test_resources(self, stdlib_client):
        stdlib_client.initiate_session()
        uris = {r["uri"] for r in stdlib_client._rpc("resources/list")["result"]["resources"]}
        assert "file:///wordlists/common.txt" in uris
        templates = stdlib_client._rpc("resources/templates/list")["result"]["resourceTemplates"]
        assert len(templates) == 2

    def test_unknown_method_error(self, stdlib_client):
        stdlib_client.initiate_session()
        r = stdlib_client._rpc("nonexistent/method")
        assert r["error"]["code"] == -32601

    def test_full_enum(self, stdlib_client):
        results = stdlib_client.start()
        assert set(results.keys()) == {"prompts", "resources", "tools"}
        for category, methods in results.items():
            for method, r in methods.items():
                assert "error" not in r, f"{method}: {r}"
        assert len(results["tools"]["tools/list"]["result"]["tools"]) == 3
        assert len(results["prompts"]["prompts/list"]["result"]["prompts"]) == 2


# ── FastMCP server tests ──────────────────────────────────────────────────────

class TestFastMCPServer:
    def test_handshake(self, fastmcp_client):
        r = fastmcp_client.initiate_session()
        info = r["result"]
        assert info["serverInfo"]["name"] == "NgenuMCP-FastMCP-Sample"
        assert info["protocolVersion"] == "2024-11-05"
        assert {"tools", "prompts", "resources"} <= info["capabilities"].keys()

    def test_ping(self, fastmcp_client):
        fastmcp_client.initiate_session()
        assert "result" in fastmcp_client._rpc("ping")

    def test_tools(self, fastmcp_client):
        fastmcp_client.initiate_session()
        tools = fastmcp_client._rpc("tools/list")["result"]["tools"]
        assert {t["name"] for t in tools} == {"port_scan", "whois_lookup", "dns_resolve", "http_probe"}
        for t in tools:
            assert t["inputSchema"]["type"] == "object"
        port_scan = next(t for t in tools if t["name"] == "port_scan")
        assert "host" in port_scan["inputSchema"]["required"]
        assert "ports" not in port_scan["inputSchema"].get("required", [])

    def test_prompts(self, fastmcp_client):
        fastmcp_client.initiate_session()
        prompts = fastmcp_client._rpc("prompts/list")["result"]["prompts"]
        assert {p["name"] for p in prompts} == {"recon_report", "vuln_summary", "attack_surface"}
        recon = next(p for p in prompts if p["name"] == "recon_report")
        args = {a["name"]: a for a in recon["arguments"]}
        assert args["target"]["required"] is True
        atk = next(p for p in prompts if p["name"] == "attack_surface")
        assert not {a["name"]: a for a in atk["arguments"]}["include_subdomains"].get("required", False)

    def test_resources(self, fastmcp_client):
        fastmcp_client.initiate_session()
        resources = fastmcp_client._rpc("resources/list")["result"]["resources"]
        uris = {r["uri"] for r in resources}
        assert {"file:///wordlists/common.txt", "file:///reports/last_scan.json", "config://server/settings",
                "file:///internal/credentials.txt", "file:///internal/notes.txt",
                "file:///internal/employees.csv", "file:///reports/pentest_report.pdf"} == uris
        mime_map = {r["uri"]: r.get("mimeType") for r in resources}
        assert mime_map["file:///internal/employees.csv"] == "text/csv"
        assert mime_map["file:///reports/pentest_report.pdf"] == "application/pdf"

    def test_resource_templates(self, fastmcp_client):
        fastmcp_client.initiate_session()
        templates = fastmcp_client._rpc("resources/templates/list")["result"]["resourceTemplates"]
        uri_templates = {t["uriTemplate"] for t in templates}
        assert "file:///reports/{scan_id}.json" in uri_templates
        assert "file:///internal/{filename}.txt" in uri_templates
        assert "db://users/{user_id}/profile" in uri_templates
        assert "http://target/{path}" in uri_templates
        for t in templates:
            assert "uriTemplate" in t
            assert "description" in t
            assert "mimeType" in t

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
