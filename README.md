# NgenuMCP

MCP server enumeration tool. Connects to any MCP-compatible HTTP server and lists its exposed tools, prompts, and resources.

## Requirements

- Python 3.8+
- `httpx`

```bash
pip install -r requirements.txt
```

## Usage

```
python NgenuMCP.py <url> [options]

positional arguments:
  url                   Target MCP endpoint (e.g. http://host:3000/mcp)

options:
  -h, --help            show this help message and exit
  -H, --header KEY:VALUE
                        Extra HTTP header, repeatable
  --ping                Ping the server instead of enumerating
  --no-init             Skip MCP initialize handshake
  --raw                 Print raw JSON output
  -vt                   Verbose: show full tool schemas
  -vp                   Verbose: show full prompt arguments
  -vr                   Verbose: show full resource details
  -vv                   Verbose: show full detail for everything
  -to                   Enumerate tools only
  -po                   Enumerate prompts only
  -ro                   Enumerate resources only
```

**Examples:**

```bash
python NgenuMCP.py http://target:3000/mcp
python NgenuMCP.py http://target:3000/mcp -H "Authorization:Bearer <token>"
python NgenuMCP.py http://target:3000/mcp --raw
python NgenuMCP.py http://target:3000/mcp --ping
```

## Transport support

| Server type | Transport | Supported |
|---|---|---|
| FastMCP / MCP SDK | Streamable HTTP (SSE) | Yes |
| Custom / plain HTTP | JSON response | Yes |

## Project structure

```
NgenuMCP/
├── NgenuMCP/
│   ├── __init__.py
│   └── client.py           EnumClient — core MCP JSON-RPC client
├── tests/
│   ├── servers/
│   │   ├── stdlib_server.py    Minimal stdlib MCP server (no deps)
│   │   └── fastmcp_server.py   FastMCP server with tools/prompts/resources
│   ├── test_client.py          Unit tests (mocked HTTP)
│   └── test_integration.py     Integration tests (live servers)
├── NgenuMCP.py             Entry point — run this
├── pyproject.toml
└── requirements.txt
```

## Running tests

```bash
pip install -e ".[dev]"
pytest
```
