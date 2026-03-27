import base64
import socket
import threading
import time
from pathlib import Path
from typing import Annotated

import uvicorn
from fastmcp import FastMCP
from pydantic import Field

FILES = Path(__file__).parent / "files"

mcp = FastMCP(
    name="NgenuMCP-FastMCP-Sample",
    version="1.0.0",
    instructions="Sample MCP server for enumeration testing",
)


@mcp.tool(description="Scan a target host for open TCP ports within a specified range and return open port list")
def port_scan(
    host: Annotated[str, Field(description="Target hostname or IP address")],
    ports: Annotated[str, Field(description="Port range to scan, e.g. 1-1024 or 80,443,8080")] = "1-1024",
) -> str:
    return f"Scan results for {host}:{ports}"


@mcp.tool(description="Perform a WHOIS lookup on a domain or IP to retrieve registration and ownership info")
def whois_lookup(
    target: Annotated[str, Field(description="Domain name or IP address to look up")],
) -> dict:
    return {"target": target, "registrar": "Example Registrar", "created": "2020-01-01"}


@mcp.tool(description="Resolve DNS records for a domain, supporting A, AAAA, MX, TXT, and NS record types")
def dns_resolve(
    domain: Annotated[str, Field(description="Domain name to resolve")],
    record_type: Annotated[str, Field(description="DNS record type to query")] = "A",
) -> list:
    return [{"type": record_type, "value": "93.184.216.34", "ttl": 3600}]


@mcp.tool(description="Probe an HTTP/HTTPS endpoint and return status code, response headers, and redirect chain")
def http_probe(
    url: Annotated[str, Field(description="Full URL to probe including scheme")],
    follow_redirects: Annotated[bool, Field(description="Whether to follow HTTP redirects")] = True,
) -> dict:
    return {"url": url, "status": 200, "headers": {"server": "nginx"}, "redirected": False}


@mcp.prompt(description="Generate a structured recon report covering open ports, services, subdomains, and exposed endpoints for a target")
def recon_report(target: str) -> str:
    return f"Generate a comprehensive recon report for target: {target}. Include open ports, services, subdomains, and exposed endpoints."


@mcp.prompt(description="Summarise raw vulnerability findings into a structured report with severity ratings and remediation steps")
def vuln_summary(findings: str) -> str:
    return f"Summarise the following vulnerability findings into a structured report:\n\n{findings}"


@mcp.prompt(description="Map the full attack surface of a domain, optionally including subdomains and third-party assets")
def attack_surface(domain: str, include_subdomains: bool = True) -> str:
    sub = "including subdomains" if include_subdomains else "top-level domain only"
    return f"Map the attack surface for {domain} ({sub})."


@mcp.resource("file:///wordlists/common.txt", description="Top common passwords and usernames for brute-force testing", mime_type="text/plain")
def common_wordlist() -> str:
    return "admin\npassword\n123456\nroot\nguest"


@mcp.resource("file:///reports/last_scan.json", description="JSON report from the most recent enumeration run", mime_type="application/json")
def last_scan_report() -> dict:
    return {"scan_id": "abc123", "target": "example.com", "tools_used": ["port_scan", "dns_resolve"]}


@mcp.resource("config://server/settings", description="Current server configuration including concurrency limits and timeouts", mime_type="application/json")
def server_settings() -> dict:
    return {"version": "1.0.0", "max_concurrent": 10, "timeout": 30}


@mcp.resource("file:///internal/credentials.txt", description="Leaked credential pairs found on the target server", mime_type="text/plain")
def credentials_file() -> str:
    return (FILES / "credentials.txt").read_text()


@mcp.resource("file:///internal/notes.txt", description="Internal admin notes containing infrastructure details", mime_type="text/plain")
def notes_file() -> str:
    return (FILES / "notes.txt").read_text()


@mcp.resource("file:///internal/employees.csv", description="Employee directory with roles and VPN access flags", mime_type="text/csv")
def employees_file() -> str:
    return (FILES / "employees.csv").read_text()


@mcp.resource("file:///reports/pentest_report.pdf", description="Latest penetration testing report (PDF)", mime_type="application/pdf")
def pentest_report() -> str:
    return base64.b64encode((FILES / "report.pdf").read_bytes()).decode()


@mcp.resource("file:///reports/{scan_id}.json", description="Retrieve a scan report by its unique ID", mime_type="application/json")
def get_scan_report(scan_id: str) -> dict:
    return {"scan_id": scan_id, "target": "example.com", "status": "completed", "findings": []}


@mcp.resource("file:///internal/{filename}.txt", description="Retrieve an internal text file by name", mime_type="text/plain")
def get_internal_file(filename: str) -> str:
    path = FILES / f"{filename}.txt"
    if path.exists():
        return path.read_text()
    return f"File not found: {filename}.txt"


@mcp.resource("db://users/{user_id}/profile", description="Fetch a user profile record from the internal database", mime_type="application/json")
def get_user_profile(user_id: str) -> dict:
    return {"user_id": user_id, "name": "John Doe", "role": "admin", "last_login": "2024-11-20T08:32:00Z"}


@mcp.resource("http://target/{path}", description="Proxy a request to a path on the target host", mime_type="text/html")
def target_path(path: str) -> str:
    return f"<html><body>Response from /{path}</body></html>"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FastMCPTestServer:
    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port or _free_port()
        self._server = None
        self._thread = None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/mcp"

    def start(self, wait=2.0):
        app = mcp.http_app(path="/mcp", stateless_http=True)
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        time.sleep(wait)

    def stop(self):
        if self._server:
            self._server.should_exit = True


if __name__ == "__main__":
    srv = FastMCPTestServer(port=5173)
    srv.start(wait=0)
    print(f"FastMCP sample server running at {srv.url}")
    try:
        input("Press Enter to stop...\n")
    finally:
        srv.stop()
