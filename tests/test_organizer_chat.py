"""The organizer as chat tools: what the user approves is what happens.

preview_organize is free and moves nothing; apply_organize goes through the
single confirmation gate, whose text is read from the stored plan; undo puts
everything back. Every test works in a pytest tmp_path.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests import _isolate  # noqa: F401

from brain.core_runtime import _execute_organize
from brain.core_tools import confirmation_detail, needs_confirmation
from organizer import chat

OLD = time.time() - 3600


def make(folder: Path, name: str, content: str | None = None) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Distinct by default: identical bytes would (rightly) be set aside as duplicates.
    path.write_text(name if content is None else content)
    os.utime(path, (OLD, OLD))
    return path


def files(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file()}


def preview(folder: Path) -> dict:
    return _execute_organize("preview_organize", {"folder": str(folder), "use_ai": False})


# ── the gate ───────────────────────────────────────────────

def test_preview_is_free_and_moving_is_gated():
    assert not needs_confirmation("preview_organize", {"folder": "~/Downloads"})
    assert needs_confirmation("apply_organize", {"plan_id": "plan-1"})
    assert needs_confirmation("undo_organize", {})


def test_preview_moves_nothing_and_returns_a_plan(tmp_path):
    make(tmp_path, "IMG_0001.jpg")
    make(tmp_path, "Lab 3.pdf")
    before = files(tmp_path)

    result = preview(tmp_path)

    assert result["status"] == "success" and result["plan_id"].startswith("plan-")
    assert files(tmp_path) == before
    assert "2 files" in result["summary"]
    assert any("IMG_0001.jpg -> Photo " in line for line in result["preview"])


def test_the_confirmation_shows_the_real_plan(tmp_path):
    make(tmp_path, "IMG_0001.jpg")
    make(tmp_path, "Lab 3.pdf")
    plan_id = preview(tmp_path)["plan_id"]

    text = confirmation_detail("apply_organize", {"plan_id": plan_id})

    assert str(tmp_path.name) in text and "2 files" in text
    assert "Lab 3.pdf" in text and "Documents/" in text
    assert "Nothing is deleted" in text


def test_a_made_up_plan_id_is_neither_confirmed_nor_applied(tmp_path):
    assert "nothing will be moved" in confirmation_detail("apply_organize", {"plan_id": "plan-999"})
    result = _execute_organize("apply_organize", {"plan_id": "plan-999"})
    assert result["status"] == "error" and result["retry_safe"]


# ── apply does exactly what was approved ───────────────────

def test_apply_carries_out_the_approved_plan_and_nothing_else(tmp_path):
    make(tmp_path, "Lab 3.pdf")
    plan_id = preview(tmp_path)["plan_id"]
    make(tmp_path, "arrived later.pdf")          # not in the plan the user saw

    result = _execute_organize("apply_organize", {"plan_id": plan_id})

    assert result["status"] == "success" and result["run_id"]
    assert files(tmp_path) == {"Documents/Lab 3.pdf", "arrived later.pdf"}


def test_a_plan_is_applied_once(tmp_path):
    make(tmp_path, "Lab 3.pdf")
    plan_id = preview(tmp_path)["plan_id"]
    assert _execute_organize("apply_organize", {"plan_id": plan_id})["status"] == "success"
    assert _execute_organize("apply_organize", {"plan_id": plan_id})["status"] == "error"


def test_an_old_preview_is_refused(tmp_path, monkeypatch):
    make(tmp_path, "Lab 3.pdf")
    plan_id = preview(tmp_path)["plan_id"]
    monkeypatch.setattr(chat, "PLAN_TTL_SECONDS", -1)

    assert _execute_organize("apply_organize", {"plan_id": plan_id})["status"] == "error"
    assert files(tmp_path) == {"Lab 3.pdf"}


def test_undo_puts_everything_back(tmp_path):
    make(tmp_path, "IMG_0001.jpg", "photo")
    make(tmp_path, "Lab 3.pdf", "lab")
    run_id = _execute_organize("apply_organize", {"plan_id": preview(tmp_path)["plan_id"]})["run_id"]

    assert "Undo organizing" in confirmation_detail("undo_organize", {"run_id": run_id})
    result = _execute_organize("undo_organize", {"run_id": run_id})

    assert result["status"] == "success" and result["result"] == "Put 2 files back."
    assert files(tmp_path) == {"IMG_0001.jpg", "Lab 3.pdf"}


def test_an_already_tidy_folder_has_nothing_to_approve(tmp_path):
    make(tmp_path, "Documents/Lab 3.pdf")
    result = preview(tmp_path)
    assert result["status"] == "success" and "plan_id" not in result
    assert "already tidy" in result["result"]


# ── folders the organizer refuses ──────────────────────────

@pytest.mark.parametrize("marker", [".git", "package.json", "pyproject.toml"])
def test_a_project_folder_is_refused(tmp_path, marker):
    make(tmp_path, "main.py")
    if marker == ".git":
        (tmp_path / marker).mkdir()
    else:
        make(tmp_path, marker)

    result = preview(tmp_path)

    assert result["status"] == "error" and "project" in result["error"]
    assert result["retry_safe"] is False


def test_the_home_folder_itself_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    make(tmp_path, "notes.pdf")
    result = preview(tmp_path)
    assert result["status"] == "error" and "too broad" in result["error"]


def test_a_folder_name_means_the_users_folder_not_a_relative_path(tmp_path, monkeypatch):
    """The model says "Downloads"; that is the user's Downloads, whatever
    folder Mike itself happens to be running from."""
    from tools.filesystem import path_utils

    downloads = tmp_path / "home" / "Downloads"
    make(downloads, "Lab 3.pdf")
    monkeypatch.setitem(path_utils.SPECIAL_PATHS, "downloads", downloads)
    monkeypatch.chdir(tmp_path)

    for said in ("Downloads", "downloads"):
        result = _execute_organize("preview_organize", {"folder": said, "use_ai": False})
        assert result["status"] == "success", result
        assert "1 files" in result["summary"]


def test_windows_user_folders_come_from_windows():
    """On Windows, Desktop/Documents/Downloads are asked of Windows itself
    (OneDrive moves them); elsewhere they are the usual home folders."""
    import sys

    from tools.filesystem import path_utils

    if sys.platform == "win32":
        for folder in (path_utils.DESKTOP, path_utils.DOCUMENTS, path_utils.DOWNLOADS):
            assert folder.is_absolute() and folder.is_dir(), folder
        assert path_utils._known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641") == path_utils.DESKTOP
    else:
        assert path_utils._known_folder("B4BFCC3A-DB2C-424C-B029-7FE99A87C641") is None
        assert path_utils.DESKTOP == path_utils.HOME / "Desktop"


def test_a_missing_folder_says_so(tmp_path):
    result = preview(tmp_path / "nope")
    assert result["status"] == "error" and "isn't a folder" in result["error"]


# ── offered when it's asked for ────────────────────────────

@pytest.mark.parametrize("ask", [
    "clean up my downloads", "can you organize my Desktop",
    "my downloads folder is a mess, tidy it", "undo that", "put them back",
])
def test_the_organizer_is_offered_when_asked(ask):
    from brain import tool_router

    assert "organize" in tool_router.wanted_groups([{"role": "user", "content": ask}])


def test_it_is_not_offered_for_unrelated_work():
    from brain import tool_router

    groups = tool_router.wanted_groups([{"role": "user", "content": "what's 2 + 2"}])
    assert "organize" not in groups
