import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from NgenuMCP.handlers.fuzz import (
    _cast_word,
    _extract_error_msg,
    _find_markers,
    _fuzz_status,
    _inject_markers,
    load_wordlist,
    run,
)


def _args(**kwargs):
    defaults = dict(
        fuzz_target="resource",
        fuzz_uri=None,
        fuzz_args="{}",
        call_tool=None,
        call_prompt=None,
        wordlist=None,
        threads=4,
        show_output=False,
        show_miss=False,
        raw=False,
        o=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _hit_resp(uri="file:///x", text="secret data"):
    return {"result": {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]}}


def _miss_resp(msg="Resource not found"):
    return {"error": {"code": -32001, "message": msg}}


def _tool_hit_resp(text="scan result"):
    return {"result": {"content": [{"type": "text", "text": text}], "isError": False}}


def _tool_error_resp(msg="missing required argument: host"):
    return {"error": {"code": -32602, "message": msg}}


def _prompt_hit_resp(text="recon report for example.com"):
    return {"result": {"messages": [{"role": "user", "content": {"type": "text", "text": text}}]}}


# ── _fuzz_status ──────────────────────────────────────────────────────────────

class TestFuzzStatus:
    def test_hit_clean_content(self):
        assert _fuzz_status(_hit_resp()) == "HIT"

    def test_hit_empty_contents(self):
        assert _fuzz_status({"result": {"contents": []}}) == "HIT"

    def test_miss_not_found_in_content_text(self):
        resp = {"result": {"contents": [{"uri": "x", "text": "File not found: credentials.txt"}]}}
        assert _fuzz_status(resp) == "miss"

    def test_miss_not_found_variants(self):
        for phrase in ("does not exist", "no such file", "resource not found", "404"):
            resp = {"result": {"contents": [{"uri": "x", "text": phrase}]}}
            assert _fuzz_status(resp) == "miss", f"expected miss for: {phrase!r}"

    def test_miss_is_error_no_hints(self):
        resp = {"result": {"isError": True, "content": [{"type": "text", "text": "execution failed"}]}}
        assert _fuzz_status(resp) == "miss"

    def test_maybe_is_error_with_bad_args_hint(self):
        resp = {"result": {"isError": True, "content": [{"type": "text", "text": "missing required field"}]}}
        assert _fuzz_status(resp) == "MAYBE"

    def test_maybe_error_code_32602(self):
        assert _fuzz_status({"error": {"code": -32602, "message": "Invalid params"}}) == "MAYBE"

    def test_maybe_error_message_contains_hint(self):
        assert _fuzz_status({"error": {"code": -1, "message": "validation error in field"}}) == "MAYBE"

    def test_miss_plain_error(self):
        assert _fuzz_status(_miss_resp()) == "miss"

    def test_miss_no_result_no_error(self):
        assert _fuzz_status({}) == "miss"

    def test_args_mode_hit(self):
        resp = {"result": {"content": [{"type": "text", "text": "ok"}], "isError": False}}
        assert _fuzz_status(resp, "args") == "HIT"

    def test_args_mode_maybe_is_error(self):
        resp = {"result": {"isError": True, "content": []}}
        assert _fuzz_status(resp, "args") == "MAYBE"

    def test_args_mode_miss_bad_args(self):
        resp = {"error": {"code": -32602, "message": "missing required argument: host"}}
        assert _fuzz_status(resp, "args") == "miss"

    def test_args_mode_maybe_unexpected_error(self):
        resp = {"error": {"code": -32603, "message": "internal server error"}}
        assert _fuzz_status(resp, "args") == "MAYBE"


# ── _extract_error_msg ────────────────────────────────────────────────────────

class TestExtractErrorMsg:
    def test_from_error_dict(self):
        assert _extract_error_msg({"error": {"code": -1, "message": "oops"}}) == "oops"

    def test_from_error_string(self):
        assert _extract_error_msg({"error": "plain error"}) == "plain error"

    def test_from_is_error_content(self):
        resp = {"result": {"isError": True, "content": [{"type": "text", "text": "bad input"}]}}
        assert _extract_error_msg(resp) == "bad input"

    def test_empty_on_clean_result(self):
        assert _extract_error_msg({"result": {"contents": []}}) == ""


# ── _find_markers ─────────────────────────────────────────────────────────────

class TestFindMarkers:
    def test_single(self):
        assert _find_markers("file:///@@FUZZ1.txt") == ["@@FUZZ1"]

    def test_multiple_sorted(self):
        assert _find_markers("db://@@FUZZ1/@@FUZZ2/profile") == ["@@FUZZ1", "@@FUZZ2"]

    def test_numeric_sort(self):
        assert _find_markers("@@FUZZ10/@@FUZZ2/@@FUZZ1") == ["@@FUZZ1", "@@FUZZ2", "@@FUZZ10"]

    def test_in_dict(self):
        markers = _find_markers({"a": "file:///@@FUZZ1.txt", "b": "@@FUZZ2"})
        assert markers == ["@@FUZZ1", "@@FUZZ2"]

    def test_in_list(self):
        assert _find_markers(["@@FUZZ1", "@@FUZZ2"]) == ["@@FUZZ1", "@@FUZZ2"]

    def test_none(self):
        assert _find_markers("file:///static.txt") == []

    def test_deduplicates(self):
        assert _find_markers("@@FUZZ1/@@FUZZ1") == ["@@FUZZ1"]


# ── _inject_markers ───────────────────────────────────────────────────────────

class TestInjectMarkers:
    def test_full_replacement_returns_str(self):
        assert _inject_markers("@@FUZZ1", {"@@FUZZ1": "admin"}, "str") == "admin"

    def test_partial_replacement(self):
        assert _inject_markers("file:///@@FUZZ1.txt", {"@@FUZZ1": "secrets"}, "str") == "file:///secrets.txt"

    def test_multiple_markers(self):
        result = _inject_markers("db://@@FUZZ1/@@FUZZ2", {"@@FUZZ1": "users", "@@FUZZ2": "42"}, "str")
        assert result == "db://users/42"

    def test_nested_dict(self):
        tmpl   = {"uri": "file:///@@FUZZ1", "other": "static"}
        result = _inject_markers(tmpl, {"@@FUZZ1": "test"}, "str")
        assert result == {"uri": "file:///test", "other": "static"}

    def test_nested_list(self):
        result = _inject_markers(["@@FUZZ1", "static"], {"@@FUZZ1": "x"}, "str")
        assert result == ["x", "static"]

    def test_int_cast_on_full_match(self):
        result = _inject_markers("@@FUZZ1", {"@@FUZZ1": "42"}, "int")
        assert result == 42
        assert isinstance(result, int)


# ── _cast_word ────────────────────────────────────────────────────────────────

class TestCastWord:
    def test_str(self):
        assert _cast_word("hello", "str") == "hello"

    def test_int(self):
        assert _cast_word("42", "int") == 42

    def test_float(self):
        assert _cast_word("3.14", "float") == pytest.approx(3.14)

    def test_bool_true(self):
        for v in ("true", "1", "yes"):
            assert _cast_word(v, "bool") is True

    def test_bool_false(self):
        for v in ("false", "0", "no"):
            assert _cast_word(v, "bool") is False

    def test_bool_invalid(self):
        with pytest.raises(ValueError):
            _cast_word("maybe", "bool")

    def test_auto_int(self):
        assert _cast_word("42", "auto") == 42

    def test_auto_float(self):
        assert _cast_word("3.14", "auto") == pytest.approx(3.14)

    def test_auto_bool_true(self):
        assert _cast_word("true", "auto") is True

    def test_auto_str_fallback(self):
        assert _cast_word("hello", "auto") == "hello"

    def test_json_object(self):
        result = _cast_word('{"key":"val"}', "json")
        assert result == {"key": "val"}


# ── load_wordlist ─────────────────────────────────────────────────────────────

class TestLoadWordlist:
    def test_strips_blanks_and_comments(self, tmp_path):
        wl = tmp_path / "words.txt"
        wl.write_text("# comment\nword1\nword2\n\nword3\n", encoding="utf-8")
        assert load_wordlist(str(wl)) == ["word1", "word2", "word3"]

    def test_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_wordlist("/nonexistent/file.txt")

    def test_unicode(self, tmp_path):
        wl = tmp_path / "unicode.txt"
        wl.write_text("ノスフェラトゥ\ncredentials\n", encoding="utf-8")
        words = load_wordlist(str(wl))
        assert words == ["ノスフェラトゥ", "credentials"]


# ── fuzz.run — resource ───────────────────────────────────────────────────────

class TestFuzzRunResource:
    def test_no_fuzz_uri(self, capsys):
        rc = run(MagicMock(), _args())
        assert rc == 1
        assert "--fuzz-uri" in capsys.readouterr().out

    def test_no_markers_in_template(self, capsys):
        rc = run(MagicMock(), _args(fuzz_uri="file:///static.txt", wordlist=["x.txt"]))
        assert rc == 1
        assert "@@FUZZn" in capsys.readouterr().out

    def test_no_wordlist(self, capsys):
        rc = run(MagicMock(), _args(fuzz_uri="file:///@@FUZZ1.txt"))
        assert rc == 1
        assert "-w WORDLIST" in capsys.readouterr().out

    def test_wordlist_not_found(self, capsys):
        rc = run(MagicMock(), _args(fuzz_uri="file:///@@FUZZ1.txt", wordlist=["/no/such/file.txt"]))
        assert rc == 1
        assert "not found" in capsys.readouterr().out.lower()

    def test_hits_and_misses_counted(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("hit1\nhit2\nmiss1\n", encoding="utf-8")

        def fake_read(uri):
            return _hit_resp(uri) if "miss" not in uri else _miss_resp()

        client = MagicMock()
        client.read_resource.side_effect = fake_read

        rc = run(client, _args(fuzz_uri="@@FUZZ1", wordlist=[str(wl)]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[HIT]" in out
        assert "done" in out
        assert "[HIT] 2" in out

    def test_show_miss_flag(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("hit\nmiss\n", encoding="utf-8")

        client = MagicMock()
        client.read_resource.side_effect = lambda uri: (
            _hit_resp(uri) if "hit" in uri else _miss_resp()
        )

        run(client, _args(fuzz_uri="@@FUZZ1", wordlist=[str(wl)], show_miss=True))
        assert "[miss]" in capsys.readouterr().out

    def test_show_miss_hidden_by_default(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("miss\n", encoding="utf-8")

        client = MagicMock()
        client.read_resource.return_value = _miss_resp()

        run(client, _args(fuzz_uri="@@FUZZ1", wordlist=[str(wl)], show_miss=False))
        out = capsys.readouterr().out
        assert "  [miss]  " not in out

    def test_show_output_prints_content(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("admin\n", encoding="utf-8")

        client = MagicMock()
        client.read_resource.return_value = _hit_resp(text="root:toor\nuser:pass")

        run(client, _args(fuzz_uri="file:///@@FUZZ1.txt", wordlist=[str(wl)], show_output=True))
        out = capsys.readouterr().out
        assert "root:toor" in out
        assert "user:pass" in out

    def test_raw_output_is_valid_json(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("test\n", encoding="utf-8")

        client = MagicMock()
        client.read_resource.return_value = _hit_resp()

        run(client, _args(fuzz_uri="@@FUZZ1", wordlist=[str(wl)], raw=True))
        out = capsys.readouterr().out
        json_part = out[out.index("{"):]
        data = json.loads(json_part)
        assert data["uri_template"] == "@@FUZZ1"
        assert len(data["results"]) == 1

    def test_file_output(self, tmp_path):
        wl      = tmp_path / "w.txt"
        out_f   = tmp_path / "out.json"
        wl.write_text("test\n", encoding="utf-8")

        client = MagicMock()
        client.read_resource.return_value = _hit_resp()

        run(client, _args(fuzz_uri="@@FUZZ1", wordlist=[str(wl)], o=str(out_f)))
        data = json.loads(out_f.read_text(encoding="utf-8"))
        assert data["uri_template"] == "@@FUZZ1"
        assert data["results"][0]["status"] == "HIT"

    def test_multi_marker_cartesian(self, tmp_path, capsys):
        wl1 = tmp_path / "a.txt"
        wl2 = tmp_path / "b.txt"
        wl1.write_text("users\nreports\n", encoding="utf-8")
        wl2.write_text("admin\ntest\n", encoding="utf-8")

        calls = []
        def fake_read(uri):
            calls.append(uri)
            return _hit_resp(uri)

        client = MagicMock()
        client.read_resource.side_effect = fake_read

        rc = run(client, _args(fuzz_uri="db://@@FUZZ1/@@FUZZ2", wordlist=[str(wl1), str(wl2)]))
        assert rc == 0
        assert len(calls) == 4   # 2 × 2 cartesian product
        assert "db://users/admin" in calls
        assert "db://reports/test" in calls

    def test_last_wordlist_reused_for_extra_markers(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("x\n", encoding="utf-8")

        calls = []
        client = MagicMock()
        client.read_resource.side_effect = lambda uri: (calls.append(uri), _hit_resp(uri))[1]

        rc = run(client, _args(fuzz_uri="@@FUZZ1/@@FUZZ2", wordlist=[str(wl)]))
        assert rc == 0
        assert len(calls) == 1
        assert calls[0] == "x/x"


# ── fuzz.run — tool ───────────────────────────────────────────────────────────

class TestFuzzRunTool:
    def test_no_fuzz_args(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="tool", call_tool="port_scan"))
        assert rc == 1
        assert "--fuzz-args" in capsys.readouterr().out

    def test_no_call_tool_name(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="tool", fuzz_args='{"host":"@@FUZZ1"}',
                                    wordlist=["x.txt"]))
        assert rc == 1
        assert "--call-tool" in capsys.readouterr().out

    def test_fuzz_args_from_file(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("127.0.0.1\n", encoding="utf-8")
        jf = tmp_path / "args.json"
        jf.write_text('{"host": "@@FUZZ1"}', encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_hit_resp("Scan results for 127.0.0.1")

        rc = run(client, _args(fuzz_target="tool", call_tool="port_scan",
                               fuzz_args=str(jf), wordlist=[str(wl)]))
        assert rc == 0
        client.call_tool.assert_called_once_with("port_scan", {"host": "127.0.0.1"})

    def test_integer_value_injected_correctly(self, tmp_path):
        """Wordlist integer stays int because marker is unquoted in template."""
        wl = tmp_path / "w.txt"
        wl.write_text("80\n443\n", encoding="utf-8")

        calls = []
        client = MagicMock()
        client.call_tool.side_effect = lambda n, a: (calls.append(a), _tool_hit_resp())[1]

        rc = run(client, _args(fuzz_target="tool", call_tool="port_scan",
                               fuzz_args='{"host":"localhost","port":@@FUZZ1}',
                               wordlist=[str(wl)]))
        assert rc == 0
        assert {"host": "localhost", "port": 80}  in calls
        assert {"host": "localhost", "port": 443} in calls

    def test_invalid_json_after_substitution(self, tmp_path, capsys):
        """Template that produces malformed JSON after substitution returns error."""
        wl = tmp_path / "w.txt"
        wl.write_text("value\n", encoding="utf-8")
        # missing closing brace → invalid JSON after substitution
        rc = run(MagicMock(), _args(fuzz_target="tool", call_tool="scan",
                                    fuzz_args='{"host": "@@FUZZ1"',
                                    wordlist=[str(wl)]))
        assert rc == 1
        assert "invalid json" in capsys.readouterr().out.lower()

    def test_no_markers_in_args(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="tool", call_tool="scan",
                                    fuzz_args='{"host": "static"}', wordlist=["x.txt"]))
        assert rc == 1
        assert "@@FUZZn" in capsys.readouterr().out

    def test_no_wordlist(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="tool", call_tool="scan",
                                    fuzz_args='{"host":"@@FUZZ1"}'))
        assert rc == 1
        assert "-w WORDLIST" in capsys.readouterr().out

    def test_hits_counted(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("127.0.0.1\n10.0.0.1\n", encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_hit_resp()

        rc = run(client, _args(fuzz_target="tool", call_tool="port_scan",
                               fuzz_args='{"host":"@@FUZZ1"}', wordlist=[str(wl)]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[HIT] 2" in out
        assert "[FUZZING TOOLS]" in out

    def test_miss_bad_args(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("bad\n", encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_error_resp("missing required argument: host")

        run(client, _args(fuzz_target="tool", call_tool="scan",
                          fuzz_args='{"host":"@@FUZZ1"}', wordlist=[str(wl)],
                          show_miss=True))
        out = capsys.readouterr().out
        assert "[miss]" in out

    def test_show_output_prints_content(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("127.0.0.1\n", encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_hit_resp("Open ports: 22, 80, 443")

        run(client, _args(fuzz_target="tool", call_tool="port_scan",
                          fuzz_args='{"host":"@@FUZZ1"}', wordlist=[str(wl)],
                          show_output=True))
        out = capsys.readouterr().out
        assert "Open ports: 22, 80, 443" in out

    def test_raw_output_is_valid_json(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("127.0.0.1\n", encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_hit_resp()

        run(client, _args(fuzz_target="tool", call_tool="port_scan",
                          fuzz_args='{"host":"@@FUZZ1"}', wordlist=[str(wl)], raw=True))
        out = capsys.readouterr().out
        data = json.loads(out[out.index("{"):])
        assert data["target"] == "tool"
        assert data["name"] == "port_scan"
        assert data["results"][0]["injected_args"] == {"host": "127.0.0.1"}
        assert data["results"][0]["status"] == "HIT"

    def test_file_output_tool(self, tmp_path):
        wl    = tmp_path / "w.txt"
        out_f = tmp_path / "out.json"
        wl.write_text("127.0.0.1\n", encoding="utf-8")

        client = MagicMock()
        client.call_tool.return_value = _tool_hit_resp()

        run(client, _args(fuzz_target="tool", call_tool="port_scan",
                          fuzz_args='{"host":"@@FUZZ1"}', wordlist=[str(wl)],
                          o=str(out_f)))
        data = json.loads(out_f.read_text(encoding="utf-8"))
        assert data["target"] == "tool"
        assert data["results"][0]["status"] == "HIT"
        assert "injected_args" in data["results"][0]

    def test_multi_marker_tool(self, tmp_path, capsys):
        """Unquoted @@FUZZ2 in template → port is parsed as JSON integer, not string."""
        wl1 = tmp_path / "hosts.txt"
        wl2 = tmp_path / "ports.txt"
        wl1.write_text("127.0.0.1\n10.0.0.1\n", encoding="utf-8")
        wl2.write_text("80\n443\n", encoding="utf-8")

        calls = []
        client = MagicMock()
        client.call_tool.side_effect = lambda n, a: (calls.append(a), _tool_hit_resp())[1]

        rc = run(client, _args(fuzz_target="tool", call_tool="port_scan",
                               fuzz_args='{"host":"@@FUZZ1","port":@@FUZZ2}',
                               wordlist=[str(wl1), str(wl2)]))
        assert rc == 0
        assert len(calls) == 4  # 2 × 2
        assert {"host": "127.0.0.1", "port": 80}  in calls
        assert {"host": "10.0.0.1",  "port": 443} in calls


# ── fuzz.run — prompt ─────────────────────────────────────────────────────────

class TestFuzzRunPrompt:
    def test_no_call_prompt_name(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="prompt", fuzz_args='{"target":"@@FUZZ1"}',
                                    wordlist=["x.txt"]))
        assert rc == 1
        assert "--call-prompt" in capsys.readouterr().out

    def test_hits_counted(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("example.com\nevil.com\n", encoding="utf-8")

        client = MagicMock()
        client.get_prompt.return_value = _prompt_hit_resp()

        rc = run(client, _args(fuzz_target="prompt", call_prompt="recon_report",
                               fuzz_args='{"target":"@@FUZZ1"}', wordlist=[str(wl)]))
        assert rc == 0
        out = capsys.readouterr().out
        assert "[FUZZING PROMPTS]" in out
        assert "[HIT] 2" in out

    def test_show_output_prints_messages(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("example.com\n", encoding="utf-8")

        client = MagicMock()
        client.get_prompt.return_value = _prompt_hit_resp("recon report for example.com")

        run(client, _args(fuzz_target="prompt", call_prompt="recon_report",
                          fuzz_args='{"target":"@@FUZZ1"}', wordlist=[str(wl)],
                          show_output=True))
        out = capsys.readouterr().out
        assert "recon report for example.com" in out

    def test_raw_output_prompt(self, tmp_path, capsys):
        wl = tmp_path / "w.txt"
        wl.write_text("example.com\n", encoding="utf-8")

        client = MagicMock()
        client.get_prompt.return_value = _prompt_hit_resp()

        run(client, _args(fuzz_target="prompt", call_prompt="recon_report",
                          fuzz_args='{"target":"@@FUZZ1"}', wordlist=[str(wl)], raw=True))
        out = capsys.readouterr().out
        data = json.loads(out[out.index("{"):])
        assert data["target"] == "prompt"
        assert data["name"] == "recon_report"
        assert data["results"][0]["injected_args"] == {"target": "example.com"}

    def test_invalid_target(self, capsys):
        rc = run(MagicMock(), _args(fuzz_target="banana"))
        assert rc == 1
        assert "Invalid --fuzz-target" in capsys.readouterr().out
