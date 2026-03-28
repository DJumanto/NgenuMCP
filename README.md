# NgenuMCP

MCP server enumeration tool. Connects to any MCP-compatible HTTP server and lists its exposed tools, prompts, and resources — and lets you call or fuzz them directly.

## Requirements

- Python 3.8+
- `httpx`

```bash
pip install -r requirements.txt
```

---

## Usage

```
python NgenuMCP.py <url> [options]

positional arguments:
  url                   Target MCP endpoint (e.g. http://host:3000/mcp)

options:
  -h, --help            show this help message and exit
  -H, --header KEY:VALUE
                        Extra HTTP header, repeatable
  -o FILE               Output file for JSON results (default: stdout)
  --ping                Ping the server instead of enumerating
  --no-init             Skip MCP initialize handshake
  --raw                 Print raw JSON output

enumeration filters:
  -to                   Enumerate tools only
  -po                   Enumerate prompts only
  -ro                   Enumerate resources only

verbosity:
  -vt                   Verbose: show full tool schemas
  -vp                   Verbose: show full prompt arguments
  -vr                   Verbose: show full resource details
  -vv                   Verbose: show full detail for everything

calling:
  --call-tool NAME      Call a tool by name
  --call-prompt NAME    Get a prompt by name
  --call-resource URI   Read a resource by URI
  --args JSON           Arguments as JSON object for --call-tool / --call-prompt

fuzzing:
  --fuzz-it             Fuzz resource URIs using a URI template
  --fuzz-uri TEMPLATE   URI template with @@FUZZ1 / @@FUZZ2 / @@FUZZn placeholders (required with --fuzz-it)
  -w, --wordlist FILE   Wordlist file, repeatable — 1st -w feeds @@FUZZ1, 2nd feeds @@FUZZ2, nth feeds @@FUZZn
  --threads N           Number of threads for fuzzing (default: 4)
  --show-output         Show resource content for HIT results
  --show-miss           Show failed fuzz attempts (miss results)
```

---

## Enumeration

Basic enumeration — list everything the server exposes:

```bash
python NgenuMCP.py http://target:3000/mcp
```

Enumerate specific categories:

```bash
python NgenuMCP.py http://target:3000/mcp -to          # tools only
python NgenuMCP.py http://target:3000/mcp -po          # prompts only
python NgenuMCP.py http://target:3000/mcp -ro          # resources only
```

Verbose — show full schemas and parameter details:

```bash
python NgenuMCP.py http://target:3000/mcp -vt          # full tool input schemas
python NgenuMCP.py http://target:3000/mcp -vp          # full prompt arguments
python NgenuMCP.py http://target:3000/mcp -vr          # full resource metadata
python NgenuMCP.py http://target:3000/mcp -vv          # everything verbose
```

With authentication headers:

```bash
python NgenuMCP.py http://target:3000/mcp -H "Authorization:Bearer <token>"
python NgenuMCP.py http://target:3000/mcp -H "X-Api-Key:secret" -H "X-Tenant:corp"
```

Save output to file:

```bash
python NgenuMCP.py http://target:3000/mcp -o results.json
python NgenuMCP.py http://target:3000/mcp --raw -o raw.json
```

Ping / connectivity check:

```bash
python NgenuMCP.py http://target:3000/mcp --ping
```

---

## Calling

> **Windows note:** single quotes are not stripped by the shell. Always use double quotes with escaped inner quotes for `--args`:
> ```bash
> --args "{\"key\":\"value\"}"
> ```

### Call a tool

```bash
# Tool with required arguments
python NgenuMCP.py http://target:3000/mcp --call-tool port_scan --args "{\"host\":\"10.0.0.1\"}"

# Tool with multiple arguments
python NgenuMCP.py http://target:3000/mcp --call-tool port_scan --args "{\"host\":\"10.0.0.1\",\"ports\":\"22,80,443\"}"

# Tool with no required arguments
python NgenuMCP.py http://target:3000/mcp --call-tool whoami

# Save result to file
python NgenuMCP.py http://target:3000/mcp --call-tool dns_resolve --args "{\"domain\":\"example.com\"}" -o out.json

# Raw JSON response
python NgenuMCP.py http://target:3000/mcp --call-tool whois_lookup --args "{\"target\":\"example.com\"}" --raw
```

### Call a prompt

```bash
# Prompt with required argument
python NgenuMCP.py http://target:3000/mcp --call-prompt recon_report --args "{\"target\":\"example.com\"}"

# Prompt with multiple arguments
python NgenuMCP.py http://target:3000/mcp --call-prompt attack_surface --args "{\"domain\":\"example.com\",\"include_subdomains\":true}"

# Save to file
python NgenuMCP.py http://target:3000/mcp --call-prompt vuln_summary --args "{\"findings\":\"open port 22, weak SSH config\"}" -o report.json
```

### Read a resource

```bash
# Static resource — use the exact URI from enumeration
python NgenuMCP.py http://target:3000/mcp --call-resource "file:///wordlists/common.txt"
python NgenuMCP.py http://target:3000/mcp --call-resource "config://server/settings"

# Template resource — substitute the variable in the URI yourself
# Template: file:///reports/{scan_id}.json  →  fill in scan_id
python NgenuMCP.py http://target:3000/mcp --call-resource "file:///reports/abc123.json"

# Template: db://users/{user_id}/profile  →  fill in user_id
python NgenuMCP.py http://target:3000/mcp --call-resource "db://users/42/profile"

# Template: file:///internal/{filename}.txt  →  fill in filename
python NgenuMCP.py http://target:3000/mcp --call-resource "file:///internal/credentials.txt"

# Save resource content to file
python NgenuMCP.py http://target:3000/mcp --call-resource "file:///reports/pentest_report.pdf" -o report.json
```

---

## Fuzzing

Resource URI fuzzing uses a **URI template** with `@@FUZZn` positional markers. Each `@@FUZZn` is replaced by a word from the corresponding `-w` wordlist, and all combinations are tried (cartesian product). Only resource fuzzing is supported.

### Result codes

| `[HIT]` | `[MAYBE]` | `[miss]` |
|---|---|---|
| Valid resource content returned | URI reached but caused a server-side execution error — potentially interesting | Resource not found or unrecognised error |

---

### URI template syntax

Use `@@FUZZ1`, `@@FUZZ2`, … `@@FUZZn` as placeholders in the URI template:

```
file:///internal/@@FUZZ1.txt          # single position
file:///@@FUZZ1/@@FUZZ2/secret.txt    # two positions — all combinations tried
```

The nth `-w` wordlist feeds `@@FUZZn`. If you supply fewer wordlists than markers, the last wordlist is reused.

---

### Single-position fuzzing

```bash
# Fuzz filename in a URI template using a custom wordlist
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt

# Use the built-in resource wordlist (full URI per line — each line is tried as-is)
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "@@FUZZ1" -w NgenuMCP/wordlists/resources.txt

# Path traversal fuzzing with an encoding wordlist
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///app/@@FUZZ1" -w traversal.txt
```

### Multi-position fuzzing

Each marker gets its own `-w` wordlist. All combinations are tried.

```bash
# @@FUZZ1 from users.txt, @@FUZZ2 from actions.txt
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "db://@@FUZZ1/@@FUZZ2/profile" \
  -w users.txt -w actions.txt

# Three positions — 1st and 2nd get own lists, 3rd reuses the 2nd
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "file:///@@FUZZ1/@@FUZZ2/@@FUZZ3.txt" \
  -w dirs.txt -w subdirs.txt
```

### Viewing results

```bash
# Show resource content for every HIT inline
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt --show-output

# Also show every failed attempt (miss results)
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt --show-output --show-miss
```

### Threading and output

```bash
# More threads
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt --threads 20

# Save results to JSON file
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt -o fuzz.json

# Raw JSON output
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt --raw
```

### Built-in wordlist

Located in `NgenuMCP/wordlists/resources.txt` — use with `@@FUZZ1` as a full-URI wordlist:

```bash
python NgenuMCP.py http://target:3000/mcp --fuzz-it --fuzz-uri "@@FUZZ1" -w NgenuMCP/wordlists/resources.txt
```

Covers:
- Standard Linux/Windows file paths
- Path traversal: `../`, URL-encoded (`%2F`, `%2e%2e`), double-encoded (`%252F`), backslash, Unicode overlong
- Null byte injection (`%00`)
- Protocol schemes: `config://`, `db://`, `memory://`, `base64://`, `env://`, `s3://`, `http://`
- Cloud metadata endpoints (AWS IMDS, GCP metadata)

---

## Transport support

| Server type | Transport | Supported |
|---|---|---|
| FastMCP / MCP SDK | Streamable HTTP (SSE) | Yes |
| Custom / plain HTTP | JSON response | Yes |

---

## Project structure

```
NgenuMCP/
├── NgenuMCP/
│   ├── __init__.py
│   ├── client.py               EnumClient — core MCP JSON-RPC client
│   ├── const.py                RPC method definitions
│   ├── display.py              All print/output functions
│   ├── handlers/
│   │   ├── enum.py             Enumeration handler
│   │   ├── call.py             Call tool/prompt/resource handler
│   │   └── fuzz.py             Fuzzing logic and runner
│   └── wordlists/
│       └── resources.txt       Built-in resource URI wordlist
├── tests/
│   ├── servers/
│   │   ├── stdlib_server.py    Minimal stdlib MCP server (no deps)
│   │   └── fastmcp_server.py   FastMCP server with tools/prompts/resources
│   ├── test_client.py          Unit tests (mocked HTTP)
│   └── test_integration.py     Integration tests (live servers)
├── NgenuMCP.py                 Entry point — run this
├── pyproject.toml
└── requirements.txt
```

---

## Running tests

Install dev dependencies and run the full suite (unit + integration):

```bash
pip install -e ".[dev]"
pytest
```

Run only unit tests (no live server required):

```bash
pytest tests/test_client.py
```

Start the FastMCP test server manually:

```bash
python tests/servers/fastmcp_server.py
# Listening at http://127.0.0.1:5173/mcp
```
