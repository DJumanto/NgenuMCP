import json

import pytest

from NgenuMCP.display import (
    print_call_result,
    print_fuzz_summary,
    print_resource_content,
    print_results,
    print_server_info,
)


# ── print_server_info ─────────────────────────────────────────────────────────

def test_print_server_info_basic(capsys):
    print_server_info({"serverInfo": {"name": "TestSrv", "version": "2.0"},
                       "protocolVersion": "2024-11-05", "capabilities": {}})
    out = capsys.readouterr().out
    assert "TestSrv" in out
    assert "2.0" in out
    assert "2024-11-05" in out


def test_print_server_info_capabilities(capsys):
    caps = {
        "tools":     {"listChanged": True},
        "prompts":   {"listChanged": False},
        "resources": {"subscribe": True, "listChanged": False},
    }
    print_server_info({"serverInfo": {}, "protocolVersion": "?", "capabilities": caps})
    out = capsys.readouterr().out
    assert "tools" in out
    assert "prompts" in out
    assert "resources" in out


def test_print_server_info_instructions(capsys):
    print_server_info({"serverInfo": {}, "protocolVersion": "?",
                       "capabilities": {}, "instructions": "Use carefully"})
    assert "Use carefully" in capsys.readouterr().out


# ── print_results ─────────────────────────────────────────────────────────────

def _make_enum_results(**overrides):
    base = {
        "tools": {"tools/list": {"result": {"tools": [
            {"name": "port_scan", "description": "Scan ports",
             "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}}, "required": ["host"]}}
        ]}}},
        "prompts": {"prompts/list": {"result": {"prompts": [
            {"name": "recon_report", "description": "Recon",
             "arguments": [{"name": "target", "required": True, "description": "Target"}]}
        ]}}},
        "resources": {
            "resources/list": {"result": {"resources": [
                {"name": "Wordlist", "uri": "file:///wordlists/common.txt",
                 "mimeType": "text/plain", "description": "Common words"}
            ]}},
            "resources/templates/list": {"result": {"resourceTemplates": [
                {"uriTemplate": "file:///reports/{id}.json", "name": "Report",
                 "mimeType": "application/json", "description": "Report by ID"}
            ]}},
        },
    }
    base.update(overrides)
    return base


def test_print_results_tool_names(capsys):
    print_results(_make_enum_results(), set())
    assert "port_scan" in capsys.readouterr().out


def test_print_results_tool_verbose(capsys):
    print_results(_make_enum_results(), {"tools"})
    out = capsys.readouterr().out
    assert "host" in out
    assert "required" in out


def test_print_results_prompt_names(capsys):
    print_results(_make_enum_results(), set())
    assert "recon_report" in capsys.readouterr().out


def test_print_results_prompt_verbose(capsys):
    print_results(_make_enum_results(), {"prompts"})
    assert "target" in capsys.readouterr().out


def test_print_results_resource_names(capsys):
    print_results(_make_enum_results(), set())
    assert "Wordlist" in capsys.readouterr().out


def test_print_results_resource_verbose(capsys):
    print_results(_make_enum_results(), {"resources"})
    out = capsys.readouterr().out
    assert "file:///wordlists/common.txt" in out
    assert "text/plain" in out


def test_print_results_error_method(capsys):
    results = {"tools": {"tools/list": {"error": "connection refused"}}}
    print_results(results, set())
    assert "ERROR" in capsys.readouterr().out


def test_print_results_verbose_all(capsys):
    print_results(_make_enum_results(), {"all"})
    out = capsys.readouterr().out
    assert "host" in out        # tool schema
    assert "target" in out      # prompt arg
    assert "text/plain" in out  # resource mime


# ── print_call_result ─────────────────────────────────────────────────────────

def test_print_call_result_tool_text(capsys):
    result = {"result": {"content": [{"type": "text", "text": "scan done"}], "isError": False}}
    print_call_result(result, "tool")
    assert "scan done" in capsys.readouterr().out


def test_print_call_result_tool_error_flag(capsys):
    result = {"result": {"content": [], "isError": True}}
    print_call_result(result, "tool")
    assert "tool error" in capsys.readouterr().out


def test_print_call_result_tool_image(capsys):
    result = {"result": {"content": [{"type": "image", "mimeType": "image/png", "data": "abc"}], "isError": False}}
    print_call_result(result, "tool")
    assert "image/png" in capsys.readouterr().out


def test_print_call_result_tool_unknown_type(capsys):
    result = {"result": {"content": [{"type": "audio", "data": "xyz"}], "isError": False}}
    print_call_result(result, "tool")
    assert "audio" in capsys.readouterr().out


def test_print_call_result_prompt_messages(capsys):
    result = {"result": {
        "description": "A recon report",
        "messages": [{"role": "user", "content": {"type": "text", "text": "report for example.com"}}],
    }}
    print_call_result(result, "prompt")
    out = capsys.readouterr().out
    assert "A recon report" in out
    assert "[user]" in out
    assert "report for example.com" in out


def test_print_call_result_resource_text(capsys):
    result = {"result": {"contents": [
        {"uri": "file:///wordlists/common.txt", "mimeType": "text/plain", "text": "admin\nroot"}
    ]}}
    print_call_result(result, "resource")
    out = capsys.readouterr().out
    assert "file:///wordlists/common.txt" in out
    assert "admin" in out
    assert "root" in out


def test_print_call_result_resource_blob(capsys):
    result = {"result": {"contents": [{"uri": "file:///report.pdf", "mimeType": "application/pdf", "blob": "abc123"}]}}
    print_call_result(result, "resource")
    assert "binary blob" in capsys.readouterr().out


def test_print_call_result_rpc_error(capsys):
    result = {"error": {"code": -32601, "message": "Method not found"}}
    print_call_result(result, "tool")
    assert "Method not found" in capsys.readouterr().out


def test_print_call_result_rpc_error_string(capsys):
    result = {"error": "plain error string"}
    print_call_result(result, "tool")
    assert "plain error string" in capsys.readouterr().out


# ── print_resource_content ────────────────────────────────────────────────────

def test_print_resource_content_default_indent(capsys):
    resp = {"result": {"contents": [{"uri": "file:///x.txt", "mimeType": "text/plain", "text": "line1\nline2"}]}}
    print_resource_content(resp)
    out = capsys.readouterr().out
    assert "file:///x.txt" in out
    assert "line1" in out


def test_print_resource_content_custom_indent(capsys):
    resp = {"result": {"contents": [{"uri": "u", "text": "data"}]}}
    print_resource_content(resp, indent="    ")
    out = capsys.readouterr().out
    assert out.startswith("    ")


def test_print_resource_content_blob(capsys):
    resp = {"result": {"contents": [{"uri": "u", "blob": "abc"}]}}
    print_resource_content(resp)
    assert "binary blob" in capsys.readouterr().out


# ── print_fuzz_summary ────────────────────────────────────────────────────────

def test_print_fuzz_summary_counts(capsys):
    results = [
        ("a", "HIT",   {}),
        ("b", "HIT",   {}),
        ("c", "MAYBE", {}),
        ("d", "miss",  {}),
        ("e", "miss",  {}),
        ("f", "miss",  {}),
    ]
    print_fuzz_summary(results)
    out = capsys.readouterr().out
    assert "[HIT] 2" in out
    assert "[MAYBE] 1" in out
    assert "[miss] 3" in out


def test_print_fuzz_summary_no_hits(capsys):
    results = [("a", "miss", {})]
    print_fuzz_summary(results)
    out = capsys.readouterr().out
    assert "No hits found" in out
