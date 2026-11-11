"""Folder organizer: rules, planning, apply and undo.

Every test works in a pytest tmp_path; journals land under MIKE_DATA_DIR,
which tests/conftest.py points at a throwaway directory.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer import apply_plan, build_plan, list_runs, undo_run
from organizer.classify import is_junk_name
from organizer.model import Suggestion

OLD = time.time() - 3600  # past the "changed in the last minute" guard


def make(folder: Path, name: str, content: bytes | str = b"x", *, age: float | None = OLD) -> Path:
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode() if isinstance(content, str) else content
    path.write_bytes(data)
    if age is not None:
        os.utime(path, (age, age))
    return path


def snapshot(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file() and p.name != ".DS_Store"}


def rules(folder: Path):
    return build_plan(folder, use_model=False)


def dst_of(plan, name: str) -> Path:
    return next(m.dst for m in plan.moves if m.src.name == name)


# ── names ──────────────────────────────────────────────────

@pytest.mark.parametrize("stem", [
    "IMG_1234", "IMG-20260104-WA0007", "document(3)", "Document 2", "untitled",
    "WhatsApp Image 2026-01-04 at 10.30.15 PM", "scan0001", "Screenshot 2026-11-10 at 3.30.12 PM",
    "a3f9c2d1e8b7f6a5c4d3", "20260104_103015", "download (2)",
])
def test_junk_names(stem):
    assert is_junk_name(stem)


@pytest.mark.parametrize("stem", [
    "water", "warranty", "Chapter 2", "Lab 3", "resume", "resume (1)",
    "Flight Dynamics HW", "my notes final FINAL", "Swiggy Invoice March",
])
def test_real_names_are_not_junk(stem):
    assert not is_junk_name(stem)


# ── planning ───────────────────────────────────────────────

def test_plan_sorts_by_type_and_touches_nothing(tmp_path):
    make(tmp_path, "Lab 3.pdf", "a")
    make(tmp_path, "budget.xlsx", "b")
    make(tmp_path, "song.mp3", "c")
    make(tmp_path, "setup.dmg", "d")
    make(tmp_path, "weird.xyz", "e")
    before = snapshot(tmp_path)

    plan = rules(tmp_path)

    assert snapshot(tmp_path) == before
    assert dst_of(plan, "Lab 3.pdf") == tmp_path / "Documents" / "Lab 3.pdf"
    assert dst_of(plan, "budget.xlsx") == tmp_path / "Spreadsheets" / "budget.xlsx"
    assert dst_of(plan, "song.mp3") == tmp_path / "Audio" / "song.mp3"
    assert dst_of(plan, "setup.dmg") == tmp_path / "Installers" / "setup.dmg"
    assert dst_of(plan, "weird.xyz") == tmp_path / "Other" / "weird.xyz"
    assert not plan.used_model


def test_junk_photos_and_screenshots_get_dated_names(tmp_path):
    make(tmp_path, "IMG_4821.JPG", "p")
    make(tmp_path, "Screenshot 2026-11-10 at 3.30.12 PM.png", "s")
    plan = rules(tmp_path)

    photo = dst_of(plan, "IMG_4821.JPG")
    shot = dst_of(plan, "Screenshot 2026-11-10 at 3.30.12 PM.png")
    assert photo.parent.name == "Images" and photo.name.startswith("Photo ") and photo.suffix == ".JPG"
    assert shot.parent.name == "Screenshots" and shot.name.startswith("Screenshot 20")


def test_user_names_are_kept_and_copy_markers_removed(tmp_path):
    make(tmp_path, "my notes final FINAL.docx", "n")
    make(tmp_path, "resume (1).pdf", "r")
    make(tmp_path, "document(3).pdf", "d")  # junk, but no model to name it
    plan = rules(tmp_path)

    assert dst_of(plan, "my notes final FINAL.docx").name == "my notes final FINAL.docx"
    assert dst_of(plan, "resume (1).pdf").name == "resume.pdf"
    assert dst_of(plan, "document(3).pdf").name == "document(3).pdf"


def test_duplicates_are_set_aside_never_deleted(tmp_path):
    make(tmp_path, "report.pdf", "same bytes")
    make(tmp_path, "report (1).pdf", "same bytes", age=OLD - 100)  # older, but worse name
    make(tmp_path, "empty1.txt", b"")
    make(tmp_path, "empty2.txt", b"")
    plan = rules(tmp_path)

    assert dst_of(plan, "report.pdf").parent.name == "Documents"
    assert dst_of(plan, "report (1).pdf").parent.name == "Duplicates"
    assert plan.duplicate_count == 1  # empty files are not duplicates of each other

    apply_plan(plan)
    assert (tmp_path / "Documents" / "report.pdf").read_text() == "same bytes"
    assert (tmp_path / "Duplicates" / "report (1).pdf").read_text() == "same bytes"


def test_a_copy_never_takes_the_originals_name(tmp_path):
    """Found on a real Downloads folder: "note (1).txt" sorts before
    "note.txt", dropped its marker first, and the original became "note 2.txt"."""
    make(tmp_path, "note.txt", "the original")
    make(tmp_path, "note (1).txt", "a different note")
    make(tmp_path, "google-services.json", "one")
    make(tmp_path, "google-services (1).json", "two")
    make(tmp_path, "google-services (3).json", "three")
    plan = rules(tmp_path)

    assert dst_of(plan, "note.txt").name == "note.txt"
    assert dst_of(plan, "note (1).txt").name == "note (1).txt"   # not "note 2.txt"
    assert dst_of(plan, "google-services.json").name == "google-services.json"
    assert {dst_of(plan, n).name for n in ("google-services (1).json", "google-services (3).json")} \
        == {"google-services (1).json", "google-services (3).json"}
    assert plan.renamed_count == 0
    assert [m.src.name for m in plan.moves] == sorted(
        (m.src.name for m in plan.moves), key=str.lower), "preview stays in folder order"


def test_collision_with_existing_file_gets_a_suffix(tmp_path):
    make(tmp_path, "Documents/notes.pdf", "already sorted")
    make(tmp_path, "notes.pdf", "new one")
    plan = rules(tmp_path)

    assert dst_of(plan, "notes.pdf") == tmp_path / "Documents" / "notes 2.pdf"
    apply_plan(plan)
    assert (tmp_path / "Documents" / "notes.pdf").read_text() == "already sorted"
    assert (tmp_path / "Documents" / "notes 2.pdf").read_text() == "new one"


def test_two_files_wanting_the_same_name_both_survive(tmp_path):
    make(tmp_path, "IMG_0001.png", "a", age=OLD)
    make(tmp_path, "IMG_0002.png", "b", age=OLD)  # same minute -> same dated name
    plan = rules(tmp_path)
    names = sorted(m.dst.name for m in plan.moves)
    assert len(set(names)) == 2
    apply_plan(plan)
    assert sorted(p.read_text() for p in (tmp_path / "Images").iterdir()) == ["a", "b"]


def test_left_alone(tmp_path):
    make(tmp_path, "fresh.pdf", "f", age=None)          # just written
    make(tmp_path, "movie.mp4.crdownload", "partial")
    make(tmp_path, ".hidden", "h")
    make(tmp_path, "My Folder/inside.pdf", "i")         # user's own folder
    (tmp_path / "link.pdf").symlink_to(tmp_path / "My Folder" / "inside.pdf")
    plan = rules(tmp_path)

    assert plan.moves == []
    reasons = {p.name: why for p, why in plan.skipped}
    assert "fresh.pdf" in reasons and "movie.mp4.crdownload" in reasons and "link.pdf" in reasons
    assert ".hidden" not in reasons and "inside.pdf" not in reasons


def test_category_blocked_by_a_file_is_skipped(tmp_path):
    make(tmp_path, "Images", "a file called Images")
    make(tmp_path, "cat.png", "c")
    plan = rules(tmp_path)
    assert all(m.src.name != "cat.png" for m in plan.moves)
    assert any(p.name == "cat.png" for p, _ in plan.skipped)


# ── Windows ────────────────────────────────────────────────

def test_windows_system_files_and_shortcuts_stay_put(tmp_path):
    """desktop.ini and Thumbs.db don't start with a dot, and a Desktop is
    mostly .lnk shortcuts: moving any of them would wreck the folder."""
    for name in ("desktop.ini", "Thumbs.db", "Chrome.lnk", "Course site.url", "notes.pdf"):
        make(tmp_path, name, name)
    plan = rules(tmp_path)

    assert [m.src.name for m in plan.moves] == ["notes.pdf"]
    reasons = {p.name: why for p, why in plan.skipped}
    assert reasons.get("Chrome.lnk") == "shortcut" and reasons.get("Course site.url") == "shortcut"
    assert "desktop.ini" not in reasons and "Thumbs.db" not in reasons  # not even mentioned


def test_hidden_and_system_attributes_are_respected(tmp_path, monkeypatch):
    from organizer import scan as scan_mod

    for name in ("hidden.pdf", "system.pdf", "mine.pdf"):
        make(tmp_path, name, name)
    real = scan_mod._attributes
    flags = {"hidden.pdf": 0x2, "system.pdf": 0x4}
    monkeypatch.setattr(scan_mod, "_attributes", lambda st: flags.get(
        next((n for n in flags if (tmp_path / n).stat().st_ino == st.st_ino), ""), real(st)))

    assert [m.src.name for m in rules(tmp_path).moves] == ["mine.pdf"]


def test_onedrive_online_only_files_are_moved_but_never_read(tmp_path, monkeypatch):
    """Hashing or reading an online-only file makes OneDrive download it."""
    from organizer import scan as scan_mod

    make(tmp_path, "cloud a.pdf", "same")
    make(tmp_path, "cloud b.pdf", "same")
    make(tmp_path, "document(3).pdf", "local")
    monkeypatch.setattr(scan_mod, "_attributes", lambda st: 0x400000)   # RECALL_ON_DATA_ACCESS
    opened = []
    monkeypatch.setattr(scan_mod, "content_hash", lambda p, *a: opened.append(p) or "h")
    namer = FakeNamer({"document(3).pdf": Suggestion("Read Anyway", None)})

    plan = build_plan(tmp_path, namer=namer)

    assert opened == [] and plan.duplicate_count == 0
    assert {m.src.name for m in plan.moves} == {"cloud a.pdf", "cloud b.pdf", "document(3).pdf"}
    # FakeNamer doesn't check; the real ModelNamer must refuse.
    from organizer.model import ModelNamer
    from organizer.scan import FileEntry

    real = ModelNamer.__new__(ModelNamer)
    real._client = object()
    assert real.suggest(FileEntry(tmp_path / "cloud a.pdf", 4, 0, cloud_only=True), "Documents") is None


@pytest.mark.parametrize("stem", ["CON", "nul", "Com1", "lpt9"])
def test_windows_reserved_names_are_never_suggested(stem):
    from organizer.classify import clean_stem

    assert clean_stem(stem).lower() != stem.lower()


# ── the model path ─────────────────────────────────────────

class FakeNamer:
    def __init__(self, answers: dict[str, Suggestion], reason: str | None = None):
        self.answers, self.reason, self.asked = answers, reason, []

    def unavailable_reason(self):
        return self.reason

    def wants(self, category):
        return category in ("Documents", "Spreadsheets", "Presentations", "Other")

    def suggest(self, entry, category):
        self.asked.append(entry.name)
        return self.answers.get(entry.name)


def test_model_names_junk_files_and_groups_topics(tmp_path):
    make(tmp_path, "document(3).pdf", "Swiggy order #1 total 450")
    make(tmp_path, "download.pdf", "Amazon invoice")
    make(tmp_path, "Lab 3.pdf", "lab report")
    namer = FakeNamer({
        "document(3).pdf": Suggestion("Swiggy Invoice March", "Invoices & Receipts"),
        "download.pdf": Suggestion("Amazon Invoice", "Invoices & Receipts"),
        # A real name is never replaced, and a one-file topic is dropped.
        "Lab 3.pdf": Suggestion("Aerodynamics Lab Report", "College"),
    })
    plan = build_plan(tmp_path, namer=namer)

    assert plan.used_model
    invoices = tmp_path / "Documents" / "Invoices & Receipts"
    assert dst_of(plan, "document(3).pdf") == invoices / "Swiggy Invoice March.pdf"
    assert dst_of(plan, "download.pdf") == invoices / "Amazon Invoice.pdf"
    assert dst_of(plan, "Lab 3.pdf") == tmp_path / "Documents" / "Lab 3.pdf"


def test_model_unavailable_falls_back_to_rules(tmp_path):
    make(tmp_path, "document(3).pdf", "x")
    namer = FakeNamer({}, reason="Ollama isn't running, so files are sorted by type only.")
    plan = build_plan(tmp_path, namer=namer)
    assert not plan.used_model and namer.asked == []
    assert plan.notes == ["Ollama isn't running, so files are sorted by type only."]
    assert dst_of(plan, "document(3).pdf") == tmp_path / "Documents" / "document(3).pdf"


def test_model_suggestion_is_made_filename_safe(tmp_path):
    make(tmp_path, "scan0001.pdf", "x")
    plan = build_plan(tmp_path, namer=FakeNamer({"scan0001.pdf": Suggestion("A/B: test?", None)}))
    # The model's raw reply is cleaned by model._parse; a fake namer bypasses
    # that, so the planner must not trust titles blindly either.
    assert "/" not in dst_of(plan, "scan0001.pdf").name
    assert dst_of(plan, "scan0001.pdf").parent == tmp_path / "Documents"


def test_model_reply_parsing():
    from organizer.model import _parse

    assert _parse('{"title": "A/B: test?", "topic": "College"}') == Suggestion("A B test", "College")
    assert _parse('{"title": "", "topic": ""}') == Suggestion(None, None)
    assert _parse("not json") is None
    assert _parse("[1, 2]") is None


# ── apply and undo ─────────────────────────────────────────

def _messy(folder: Path) -> None:
    make(folder, "IMG_1.jpg", "photo")
    make(folder, "Screenshot 2026-01-01 at 1.00.00 PM.png", "shot")
    make(folder, "Lab 3.pdf", "lab")
    make(folder, "resume (1).pdf", "cv")
    make(folder, "copy.pdf", "lab")  # duplicate of Lab 3.pdf
    make(folder, "data.csv", "1,2")
    make(folder, "Documents/keep.pdf", "already here")


def test_apply_then_undo_restores_everything(tmp_path):
    _messy(tmp_path)
    before = snapshot(tmp_path)

    plan = rules(tmp_path)
    result = apply_plan(plan)
    assert result.moved == len(plan.moves) and not result.failed
    assert snapshot(tmp_path) != before
    assert list_runs()[0]["run_id"] == result.run_id

    undo = undo_run(result.run_id)
    assert undo.restored == len(plan.moves) and not undo.left_alone
    assert snapshot(tmp_path) == before
    # Folders this run made are gone; the user's own Documents folder stays.
    assert sorted(p.name for p in tmp_path.iterdir() if p.is_dir()) == ["Documents"]
    with pytest.raises(LookupError):
        undo_run(result.run_id)


def test_undo_defaults_to_latest_run(tmp_path):
    make(tmp_path, "a.pdf", "a")
    result = apply_plan(rules(tmp_path))
    assert undo_run().run_id == result.run_id
    assert (tmp_path / "a.pdf").exists()


def test_undo_leaves_files_the_user_moved(tmp_path):
    make(tmp_path, "a.pdf", "a")
    make(tmp_path, "b.pdf", "b")
    result = apply_plan(rules(tmp_path))
    elsewhere = tmp_path / "My Stuff"
    elsewhere.mkdir()
    os.rename(tmp_path / "Documents" / "a.pdf", elsewhere / "a.pdf")

    undo = undo_run(result.run_id)
    assert undo.restored == 1
    assert len(undo.left_alone) == 1
    assert (elsewhere / "a.pdf").read_text() == "a"
    assert (tmp_path / "b.pdf").read_text() == "b"


def test_undo_never_overwrites(tmp_path):
    make(tmp_path, "a.pdf", "original")
    result = apply_plan(rules(tmp_path))
    make(tmp_path, "a.pdf", "a new file with the same name")

    undo = undo_run(result.run_id)
    assert undo.restored == 0 and len(undo.left_alone) == 1
    assert (tmp_path / "a.pdf").read_text() == "a new file with the same name"
    assert (tmp_path / "Documents" / "a.pdf").read_text() == "original"


def test_apply_refuses_to_overwrite_a_file_that_appeared(tmp_path):
    make(tmp_path, "a.pdf", "mine")
    plan = rules(tmp_path)
    make(tmp_path, "Documents/a.pdf", "appeared after planning")

    result = apply_plan(plan)
    assert result.moved == 0 and len(result.failed) == 1
    assert (tmp_path / "a.pdf").read_text() == "mine"
    assert (tmp_path / "Documents" / "a.pdf").read_text() == "appeared after planning"


def test_empty_folder_left_by_finder_litter_is_removed_on_undo(tmp_path):
    make(tmp_path, "a.pdf", "a")
    result = apply_plan(rules(tmp_path))
    (tmp_path / "Documents" / ".DS_Store").write_bytes(b"finder")
    undo_run(result.run_id)
    assert not (tmp_path / "Documents").exists()


# ── CLI ────────────────────────────────────────────────────

def test_cli_plan_apply_undo_history(tmp_path, capsys):
    from organizer.__main__ import main

    make(tmp_path, "IMG_9.png", "p")
    assert main(["plan", str(tmp_path), "--no-ai"]) == 0
    out = capsys.readouterr().out
    assert "Images/" in out and "IMG_9.png  ->  Photo " in out and "Nothing is deleted." in out
    assert snapshot(tmp_path) == {"IMG_9.png": b"p"}

    assert main(["apply", str(tmp_path), "--no-ai", "--yes"]) == 0
    assert main(["undo"]) == 0
    assert snapshot(tmp_path) == {"IMG_9.png": b"p"}
    assert main(["history"]) == 0
    assert "undone" in capsys.readouterr().out
