"""Tests for document reading and search tools."""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.filesystem.document_reader import read_document, MAX_TEXT_CHARS
from tools.filesystem.file_manager import FileManager


def test_read_text_file():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("Hello, Mike!")
        f.flush()
        result = read_document(f.name)
        assert result == "Hello, Mike!"
    os.unlink(f.name)
    print("PASS: text file")


def test_read_json():
    data = {"name": "Mike", "version": 2}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump(data, f)
        f.flush()
        result = read_document(f.name)
        parsed = json.loads(result)
        assert parsed["name"] == "Mike"
        assert parsed["version"] == 2
    os.unlink(f.name)
    print("PASS: JSON file")


def test_read_csv():
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        f.write("Name,Score\nAlice,95\nBob,87\n")
        f.flush()
        result = read_document(f.name)
        assert "Alice" in result
        assert "95" in result
        assert "|" in result
    os.unlink(f.name)
    print("PASS: CSV file")


def test_read_markdown():
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write("# Title\n\nSome **bold** text.")
        f.flush()
        result = read_document(f.name)
        assert "# Title" in result
        assert "**bold**" in result
    os.unlink(f.name)
    print("PASS: markdown file")


def test_truncation():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("x" * 20_000)
        f.flush()
        result = read_document(f.name)
        assert "Truncated" in result
        assert len(result) < 20_000
    os.unlink(f.name)
    print("PASS: truncation")


def test_missing_file():
    try:
        read_document("/nonexistent/file.txt")
        assert False, "Should have raised"
    except FileNotFoundError:
        pass
    print("PASS: missing file error")


def test_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("")
        f.flush()
        result = read_document(f.name)
        assert "Could not extract" in result
    os.unlink(f.name)
    print("PASS: empty file")


def test_read_python_file():
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write("def hello():\n    return 'world'\n")
        f.flush()
        result = read_document(f.name)
        assert "def hello" in result
    os.unlink(f.name)
    print("PASS: Python file")


def test_size_guard_read_file():
    fm = FileManager()
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("a" * 20_000)
        f.flush()
        result = fm.read_file(f.name)
        assert "Truncated" in result
        assert len(result) < 20_000
    os.unlink(f.name)
    print("PASS: read_file size guard")


def test_real_pdf():
    pdf_path = os.path.expanduser("~/Downloads/Motor Specifications (2).pdf")
    if not os.path.exists(pdf_path):
        print("SKIP: real PDF (file not found)")
        return
    result = read_document(pdf_path)
    assert len(result) > 100
    assert "image-based" not in result.lower()
    print(f"PASS: real PDF ({len(result)} chars)")


def test_real_docx():
    docx_path = os.path.expanduser("~/Downloads/Webpage content (1).docx")
    if not os.path.exists(docx_path):
        print("SKIP: real DOCX (file not found)")
        return
    result = read_document(docx_path)
    assert len(result) > 100
    print(f"PASS: real DOCX ({len(result)} chars)")


if __name__ == "__main__":
    test_read_text_file()
    test_read_json()
    test_read_csv()
    test_read_markdown()
    test_truncation()
    test_missing_file()
    test_empty_file()
    test_read_python_file()
    test_size_guard_read_file()
    test_real_pdf()
    test_real_docx()
    print("\nAll document tests passed.")
