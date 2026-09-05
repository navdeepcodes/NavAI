"""Verification primitives — evidence that something actually worked.

A tool call succeeding is not the same as a task succeeding. Writing a file
does not mean the file parses; starting a server does not mean it serves.
These close that gap by producing evidence the model can reason about,
without deciding anything on its behalf.

Nothing here is model-specific, and nothing here retries or repairs. It
observes and reports.
"""
from __future__ import annotations

import ast
import json
import socket
import subprocess
import time
from urllib.parse import urlparse

from tools.filesystem.path_utils import resolve_path

# Long enough for a dev server that is still warming up, short enough that a
# wrong URL fails while the model is still thinking about it.
DEFAULT_TIMEOUT = 10
MAX_BODY_CHARS = 4000


def check_url(url: str, timeout: int = DEFAULT_TIMEOUT, expect: str = "") -> dict:
    """
    Fetch a URL and report what came back.

    This is what turns "I started the server" into "the server is serving".
    A connection refused is a normal, informative answer here — not an error
    to be hidden — because it is exactly how the model learns the server is
    not up yet.
    """
    if not url:
        return {"status": "error", "error": "No URL provided."}
    if "://" not in url:
        url = "http://" + url

    parsed = urlparse(url)
    started = time.monotonic()

    try:
        import requests

        response = requests.get(url, timeout=timeout)
        body = response.text or ""
        elapsed = round((time.monotonic() - started) * 1000)

        result = {
            "status": "success",
            "url": url,
            "http_status": response.status_code,
            "reachable": True,
            "content_type": response.headers.get("Content-Type", ""),
            "body_chars": len(body),
            "body": body[:MAX_BODY_CHARS],
            "truncated": len(body) > MAX_BODY_CHARS,
            "duration_ms": elapsed,
        }
        if expect:
            result["expected_text"] = expect
            result["expected_present"] = expect in body
        return result

    except Exception as exc:
        # Distinguish "nothing is listening" from "listening but broken",
        # because they call for completely different next steps.
        listening = _port_open(parsed.hostname or "127.0.0.1", parsed.port or 80)
        return {
            "status": "error",
            "url": url,
            "reachable": False,
            "port_listening": listening,
            "error": (
                f"Could not fetch {url}: {type(exc).__name__}. "
                + (
                    "Something is listening on the port but did not serve this "
                    "request — the server may still be starting, or the path is wrong."
                    if listening
                    else "Nothing is listening on that port yet."
                )
            ),
            "duration_ms": round((time.monotonic() - started) * 1000),
        }


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False


def check_port(port: int, host: str = "127.0.0.1") -> dict:
    """Is anything listening? The cheapest possible 'did my server start'."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return {"status": "error", "error": f"{port!r} is not a port number."}

    listening = _port_open(host, port)
    return {
        "status": "success",
        "host": host,
        "port": port,
        "listening": listening,
        "result": (
            f"Something is listening on {host}:{port}."
            if listening
            else f"Nothing is listening on {host}:{port}."
        ),
    }


# Syntax checkers Mike can run without installing anything. Deliberately
# limited to languages where a check is both cheap and trustworthy — a
# half-right answer about whether code parses is worse than no answer.
def check_syntax(path: str) -> dict:
    """
    Does this file still parse?

    Intended to be run straight after an edit. `edit_file` guarantees the
    text changed; it cannot guarantee the result is still valid code, and a
    file that no longer parses is a failure the model needs to know about
    immediately rather than discovering later through a confusing test error.
    """
    file = resolve_path(path)
    if not file.exists():
        return {"status": "error", "error": f"No such file: {file}"}

    suffix = file.suffix.lower()

    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"status": "error", "error": f"Could not read {file}: {exc}"}

    if suffix == ".py":
        try:
            ast.parse(text)
            return {"status": "success", "path": str(file), "language": "python",
                    "valid": True, "result": f"{file.name} parses cleanly."}
        except SyntaxError as exc:
            return {
                "status": "success",          # the check ran; the file is bad
                "path": str(file),
                "language": "python",
                "valid": False,
                "line": exc.lineno,
                "column": exc.offset,
                "message": exc.msg,
                "result": f"{file.name} has a syntax error on line {exc.lineno}: {exc.msg}",
            }

    if suffix in (".json", ".jsonc"):
        try:
            json.loads(text)
            return {"status": "success", "path": str(file), "language": "json",
                    "valid": True, "result": f"{file.name} is valid JSON."}
        except json.JSONDecodeError as exc:
            return {
                "status": "success",
                "path": str(file),
                "language": "json",
                "valid": False,
                "line": exc.lineno,
                "column": exc.colno,
                "message": exc.msg,
                "result": f"{file.name} is not valid JSON: {exc.msg} (line {exc.lineno})",
            }

    if suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
        # Only if a checker is already present — Mike does not install things
        # to answer a question.
        probe = subprocess.run(["which", "node"], capture_output=True, text=True)
        if probe.returncode == 0 and suffix in (".js", ".mjs", ".cjs"):
            check = subprocess.run(
                ["node", "--check", str(file)], capture_output=True, text=True, timeout=20
            )
            valid = check.returncode == 0
            return {
                "status": "success",
                "path": str(file),
                "language": "javascript",
                "valid": valid,
                "message": (check.stderr or "").strip()[:400],
                "result": (
                    f"{file.name} parses cleanly."
                    if valid else f"{file.name} has a syntax error."
                ),
            }
        return {
            "status": "success", "path": str(file), "language": suffix.lstrip("."),
            "valid": None,
            "result": (
                f"No syntax checker available for {suffix} files. "
                "Run the project's own build or type-check instead."
            ),
        }

    return {
        "status": "success", "path": str(file), "language": suffix.lstrip(".") or "unknown",
        "valid": None,
        "result": (
            f"Mike can't syntax-check {suffix or 'this'} files. "
            "Checking is available for Python, JSON and JavaScript."
        ),
    }
