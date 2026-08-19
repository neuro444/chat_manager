"""Transcript content must never reach stdout unless DEBUG_CONTEXT is on.

user_id is the caller's phone number, so these log lines are PII. Timing lines
carry no content and are expected to print in production.
"""
import importlib

import config
import service


def _reload(monkeypatch, value):
    monkeypatch.setenv("DEBUG_CONTEXT", value)
    importlib.reload(config)
    importlib.reload(service)
    return service


def test_debug_silent_when_flag_off(monkeypatch, capsys):
    svc = _reload(monkeypatch, "false")
    svc._debug("[chat_result] chocolate cake for +14045550001")
    assert capsys.readouterr().out == ""


def test_debug_prints_when_flag_on(monkeypatch, capsys):
    svc = _reload(monkeypatch, "true")
    svc._debug("[chat_result] visible locally")
    assert "visible locally" in capsys.readouterr().out


def test_content_bearing_lines_are_gated():
    """The raw-response and result dumps must go through _debug, not print."""
    src = open(service.__file__).read()
    for marker in ("[llm_raw_response]", "[chat_result]"):
        for line in src.splitlines():
            if marker in line and "def " not in line:
                assert "_debug(" in line, f"{marker} must be gated: {line.strip()}"


def test_timing_lines_stay_ungated():
    """Latency signal is not PII and should survive in production logs."""
    src = open(service.__file__).read()
    assert any(
        "[llm_call_start]" in ln and "print(" in ln for ln in src.splitlines()
    )
