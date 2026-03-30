# NgenuMCP

<p align="center">
  <img src="pict/image.png" alt="NgenuMCP" />
</p>

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
  --fuzz-it             Enable fuzzing mode
  --fuzz-target TARGET  What to fuzz: tool | prompt | resource (default: resource)
  --fuzz-uri URI_TEMPLATE
                        URI template with @@FUZZ1 / @@FUZZn placeholders (resource fuzzing)
  --fuzz-args JSON      Args template with @@FUZZ1 / @@FUZZn placeholders (tool/prompt fuzzing).
                        Accepts a JSON string or a path to a text file.
  -w, --wordlist FILE   Wordlist file, repeatable — 1st -w feeds @@FUZZ1, 2nd feeds @@FUZZ2, nth feeds @@FUZZn
  --threads N           Number of threads for fuzzing (default: 4)
  --show-output         Show response content for HIT results
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
python NgenuMCP.py http://target:3000/mcp -o results.json   # formatted output to file
python NgenuMCP.py http://target:3000/mcp --raw             # raw JSON to stdout
```

Ping / connectivity check:

```bash
python NgenuMCP.py http://target:3000/mcp --ping
```

Skip the MCP initialize handshake (useful for servers that respond without it):

```bash
python NgenuMCP.py http://target:3000/mcp --no-init
```

---

## Calling

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

Fuzzing iterates wordlists over `@@FUZZn` positional markers and tries all combinations (cartesian product). Three targets are supported: **resource** URIs, **tool** arguments, and **prompt** arguments.

### Result codes

| Code | Meaning |
|---|---|
| `[HIT]` | Valid response — resource content returned, or tool/prompt executed successfully |
| `[MAYBE]` | Request reached the server but caused an execution-level error — potentially interesting |
| `[miss]` | Not found, bad arguments, or response text contains a "not found" phrase |

`[MAYBE]` is worth investigating manually — the server processed the input but something went wrong server-side (e.g. a handler that exists but crashed).

`[miss]` covers both hard errors and soft misses where the server returns text containing phrases like `"not found"`, `"does not exist"`, or `"no such file"`.

---

### Placeholder syntax

Use `@@FUZZ1`, `@@FUZZ2`, … `@@FUZZn` as placeholders anywhere in a URI or JSON args template. The nth `-w` wordlist feeds `@@FUZZn`. If you supply fewer wordlists than markers, the last one is reused.

**Resource URI template:**
```
file:///internal/@@FUZZ1.txt          # single marker
file:///@@FUZZ1/@@FUZZ2/secret.txt    # two markers — cartesian product
```

**Tool / prompt args template (JSON):**
```json
{"host": "@@FUZZ1", "ports": "@@FUZZ2"}
{"host": "@@FUZZ1", "port": @@FUZZ2}
```

> Markers inside JSON string quotes stay strings after substitution. Unquoted markers take on the JSON type of the substituted word (e.g. `@@FUZZ2` → `80` becomes the integer `80`).

---

### Resource fuzzing

Fuzz resource URIs by iterating filenames, paths, or full URIs.

```bash
# Fuzz a filename in a URI template
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "file:///internal/@@FUZZ1.txt" -w names.txt

# Full-URI wordlist (each line tried as-is)
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "@@FUZZ1" -w NgenuMCP/wordlists/resources.txt

# Path traversal
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "file:///app/@@FUZZ1" -w traversal.txt

# Multi-marker — 2 wordlists, all combinations tried
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-uri "db://@@FUZZ1/@@FUZZ2/profile" \
  -w users.txt -w actions.txt
```

---

### Tool fuzzing

Fuzz tool arguments using a JSON template. Pass the template as a string or as a `.json` file. The tool name is set with `--call-tool`.

```bash
# Inline JSON template — fuzz the host argument
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-target tool --call-tool port_scan \
  --fuzz-args '{"host":"@@FUZZ1","ports":"80,443"}' \
  -w hosts.txt

# JSON file template — fuzz host and port simultaneously
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-target tool --call-tool port_scan \
  --fuzz-args args_template.json \
  -w hosts.txt -w ports.txt
```

**`args_template.json`** (port as an unquoted integer):
```json
{"host": "@@FUZZ1", "port": @@FUZZ2}
```

---

### Prompt fuzzing

Fuzz prompt arguments the same way — use `--fuzz-target prompt` and `--call-prompt`.

```bash
python NgenuMCP.py http://target:3000/mcp --fuzz-it \
  --fuzz-target prompt --call-prompt recon_report \
  --fuzz-args '{"target":"@@FUZZ1"}' \
  -w domains.txt
```

---

### Common options

```bash
# Show response content inline for every HIT
... --show-output

# Also show miss results
... --show-miss

# More threads
... --threads 20

# Save all results to a JSON file
... -o fuzz_results.json

# Raw JSON to stdout
... --raw
```

**JSON output format** (`-o` / `--raw`):

```json
{
  "target": "tool",
  "name": "port_scan",
  "fuzz_template": "{\"host\":\"@@FUZZ1\",\"port\":@@FUZZ2}",
  "results": [
    {
      "label": "@@FUZZ1=127.0.0.1 | @@FUZZ2=80",
      "injected_args": {"host": "127.0.0.1", "port": 80},
      "status": "HIT",
      "response": { ... }
    }
  ]
}
```

Resource fuzz output uses `uri_template` instead of `name`/`fuzz_template`/`injected_args`.

---

### Built-in wordlists

Located in `NgenuMCP/wordlists/`:

| File | Use |
|---|---|
| `resources.txt` | Full resource URIs — use with `--fuzz-uri "@@FUZZ1"` |
| `hosts.txt` | Common internal hostnames and IPs |
| `ports.txt` | Common ports |
| `domains.txt` | Domain names for prompt/tool fuzzing |

`resources.txt` covers:
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
│   ├── test_client.py          Unit tests — EnumClient (mocked HTTP)
│   ├── test_fuzz.py            Unit tests — fuzz handler and helpers
│   ├── test_display.py         Unit tests — all print/output functions
│   └── test_integration.py     Integration tests (live servers)
├── NgenuMCP.py                 Entry point — run this
├── pyproject.toml
└── requirements.txt
```

---

## Running tests

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the full suite (unit + integration, starts live servers automatically):

```bash
pytest
```

Run only unit tests (no live server required, fast):

```bash
pytest tests/test_client.py tests/test_fuzz.py tests/test_display.py
```

Run only integration tests:

```bash
pytest tests/test_integration.py
```

> **Windows note:** if pytest is not on PATH, use the venv directly:
> ```bash
> venv/Scripts/pytest
> ```

Start the FastMCP test server manually:

```bash
python tests/servers/fastmcp_server.py
# Listening at http://127.0.0.1:5173/mcp
```
