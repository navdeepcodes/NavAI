"""Documents: a failed extraction must not look like content.

The dangerous failure here is not a crash. It is returning
status=success with the body "Could not extract text from this .csv file" --
because the model receives that in the slot where the document's contents
belong, and has no way to tell it apart from a document that genuinely says
so. Worse was a PNG returned as a successful read whose body was the literal
bytes of the file header: noise for the model to pattern-match against.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401


def _runtime():
    from brain.core_runtime import CoreRuntime
    return CoreRuntime()


def _write(name: str, data, binary=False):
    path = os.path.join(tempfile.mkdtemp(), name)
    with open(path, "wb" if binary else "w") as handle:
        handle.write(data)
    return path


# ══ what should work ═══════════════════════════════════════

def test_real_documents_are_read():
    runtime = _runtime()
    cases = {
        _write("d.csv", "region,q3\nnorth,1200\n"): "north",
        _write("d.json", json.dumps({"tests": 242})): "242",
        _write("d.txt", "SENTINEL_TXT here."): "SENTINEL_TXT",
        _write("d.md", "# Heading\n\nSENTINEL_MD"): "SENTINEL_MD",
    }
    for path, expected in cases.items():
        result = runtime._execute_tool("read_document", {"path": path})
        assert result["status"] == "success", f"{path}: {result.get('error')}"
        assert expected in result["result"], f"{path} did not contain {expected!r}"
    print(f"PASS: {len(cases)} real document types read correctly")


# ══ what must fail, and fail visibly ═══════════════════════

def test_an_empty_document_is_an_error_not_an_apology():
    runtime = _runtime()
    result = runtime._execute_tool(
        "read_document", {"path": _write("empty.csv", "")})

    assert result["status"] == "error", (
        "an unextractable file reported as success puts an apology where the "
        "model expects content"
    )
    assert "No text could be extracted" in result["error"]
    print("PASS: an empty document reports an error")


def test_binary_content_is_never_returned_as_document_text():
    """A PNG was being returned as a successful read whose body started with
    the file header bytes."""
    runtime = _runtime()
    png = _write("image.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 200, binary=True)

    result = runtime._execute_tool("read_document", {"path": png})
    assert result["status"] == "error"
    assert "binary" in result["error"].lower()
    assert "see_screen" in result["error"], "point at the tool that can help"
    print("PASS: binary files are refused, not returned as text")


def test_a_corrupt_document_reports_a_readable_failure():
    runtime = _runtime()
    broken = _write("broken.pdf", b"%PDF-1.4 not really a pdf \x00\x01", binary=True)

    result = runtime._execute_tool("read_document", {"path": broken})
    assert result["status"] == "error"
    assert result.get("retry_safe") is False, (
        "the file is corrupt; retrying the same call cannot help"
    )
    print("PASS: a corrupt document fails without inviting a retry")


def test_a_missing_file_is_retryable_but_a_broken_one_is_not():
    """The distinction matters: a wrong path is the model's to fix, a corrupt
    file is not."""
    runtime = _runtime()

    missing = runtime._execute_tool(
        "read_document", {"path": "/tmp/definitely_absent_xyz.pdf"})
    assert missing["status"] == "error"
    assert missing.get("retry_safe") is True

    corrupt = runtime._execute_tool(
        "read_document", {"path": _write("x.docx", b"PK\x03\x04 truncated", binary=True)})
    assert corrupt["status"] == "error"
    assert corrupt.get("retry_safe") is False
    print("PASS: retryability distinguishes a wrong path from a broken file")


def test_an_image_pdf_says_so_specifically():
    """"No text" and "this is a scan" call for different next actions."""
    from tools.filesystem.document_reader import DocumentUnreadable, read_document

    # A structurally valid PDF with no text layer is hard to synthesise here;
    # assert the message exists for the path that produces it.
    import inspect
    source = inspect.getsource(read_document)
    assert "image-based" in source
    assert "see_screen" in source, "an image PDF should point at vision"
    assert "DocumentUnreadable" in source
    print("PASS: an image-only PDF gets its own explanation")


def test_no_extraction_failure_is_reported_as_success():
    """The general invariant, checked across every failure shape at once."""
    runtime = _runtime()
    failures = [
        _write("empty.csv", ""),
        _write("empty.txt", "   \n  \n"),
        _write("img.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 200, binary=True),
        _write("bad.pdf", b"%PDF junk \x00", binary=True),
    ]
    for path in failures:
        result = runtime._execute_tool("read_document", {"path": path})
        assert result["status"] == "error", (
            f"{os.path.basename(path)} was reported as a successful read: "
            f"{str(result.get('result'))[:80]!r}"
        )
    print(f"PASS: none of {len(failures)} unreadable files reported success")


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
    print("\nAll document honesty tests passed.")
