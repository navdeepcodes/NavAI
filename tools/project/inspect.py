"""Efficient ways to understand a project, rather than dumping it into context.

The goal is not to summarise a repository for the model — the model is the
intelligence and does that far better than any heuristic here could. The goal
is to answer, cheaply and factually, the questions it would otherwise have to
burn many tool calls guessing at: what kind of project is this, what has
changed, what is worth reading first.

Everything here is read-only observation. Nothing writes, so nothing needs a
confirmation gate.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from tools.filesystem.path_utils import resolve_path

# Noise that would crowd out signal in a tree. Deliberately conservative —
# the model can always look inside these explicitly if it needs to.
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "target", ".idea", ".vscode",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage",
    ".DS_Store", "site-packages", ".tox", ".gradle",
}

# Files that identify what a project *is* — worth surfacing wherever found.
_MARKERS = {
    "package.json": "Node/JavaScript",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "setup.py": "Python",
    "Pipfile": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java/Maven",
    "build.gradle": "Java/Gradle",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "CMakeLists.txt": "C/C++",
    "Makefile": "Make",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "tsconfig.json": "TypeScript",
}


def _git(root: Path, *args: str, timeout: int = 10) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


def project_tree(path: str = ".", max_depth: int = 3, max_entries: int = 300) -> dict:
    """
    A depth-limited, noise-filtered tree.

    Bounded on purpose: an unbounded tree of a real repository is both
    useless and expensive. Truncation is reported explicitly so the model
    knows it is looking at a partial view and can descend deliberately.
    """
    root = resolve_path(path)
    if not root.exists():
        return {"status": "error", "error": f"No such path: {root}"}
    if not root.is_dir():
        return {"status": "error", "error": f"{root} is not a directory."}

    lines: list[str] = []
    truncated = False
    skipped_dirs: set[str] = set()

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal truncated
        if depth > max_depth or truncated:
            return
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except OSError:
            return

        for entry in entries:
            if len(lines) >= max_entries:
                truncated = True
                return
            if entry.name.startswith(".") and entry.name not in {".env.example", ".github"}:
                continue
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    skipped_dirs.add(entry.name)
                    continue
                lines.append(f"{prefix}{entry.name}/")
                walk(entry, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{entry.name}")

    walk(root, "", 1)

    return {
        "status": "success",
        "root": str(root),
        "tree": "\n".join(lines) if lines else "(empty)",
        "entries_shown": len(lines),
        "truncated": truncated,
        "skipped_directories": sorted(skipped_dirs),
        "note": (
            f"Depth-limited to {max_depth} and filtered. Use list_directory or "
            "another project_tree call on a subpath to go deeper."
            if truncated or skipped_dirs else ""
        ),
    }


def project_overview(path: str = ".") -> dict:
    """
    What kind of project this is, what state it is in, and where to start.

    One call in place of the handful of guesses that would otherwise be
    needed: markers, declared scripts/dependencies, git state, and recently
    changed files — the last being the single best pointer to what someone
    was actually working on.
    """
    root = resolve_path(path)
    if not root.exists():
        return {"status": "error", "error": f"No such path: {root}"}
    if not root.is_dir():
        return {"status": "error", "error": f"{root} is not a directory."}

    overview: dict = {"status": "success", "root": str(root)}

    # ── what kind of project ─────────────────────────────
    found: dict[str, str] = {}
    for marker, kind in _MARKERS.items():
        if (root / marker).exists():
            found[marker] = kind
    overview["markers"] = found
    overview["project_types"] = sorted(set(found.values()))

    # ── declared entry points, from the project's own metadata ──
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            overview["package"] = {
                "name": pkg.get("name"),
                "version": pkg.get("version"),
                "scripts": pkg.get("scripts", {}),
                "dependencies": sorted((pkg.get("dependencies") or {}).keys()),
                "devDependencies": sorted((pkg.get("devDependencies") or {}).keys()),
            }
        except Exception as exc:
            overview["package_error"] = str(exc)

    if (root / "pyproject.toml").exists():
        try:
            text = (root / "pyproject.toml").read_text(encoding="utf-8")
            overview["pyproject_excerpt"] = text[:2000]
        except Exception:
            pass

    if (root / "requirements.txt").exists():
        try:
            reqs = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
            overview["requirements"] = [r for r in reqs if r.strip() and not r.startswith("#")][:80]
        except Exception:
            pass

    # ── git state ────────────────────────────────────────
    code, _, _ = _git(root, "rev-parse", "--is-inside-work-tree")
    if code == 0:
        git: dict = {"is_repo": True}
        _, branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        git["branch"] = branch
        _, status, _ = _git(root, "status", "--porcelain")
        changed = [ln for ln in status.splitlines() if ln.strip()]
        git["dirty"] = bool(changed)
        git["changed_files"] = changed[:60]
        git["changed_count"] = len(changed)
        _, log, _ = _git(root, "log", "-8", "--pretty=format:%h %ad %s", "--date=short")
        git["recent_commits"] = log.splitlines()
        overview["git"] = git
    else:
        overview["git"] = {"is_repo": False}

    # ── what was recently worked on ──────────────────────
    overview["recently_modified"] = _recent_files(root)

    return overview


def _recent_files(root: Path, limit: int = 15) -> list[dict]:
    candidates: list[tuple[float, Path]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            if name.startswith("."):
                continue
            fp = Path(dirpath) / name
            try:
                candidates.append((fp.stat().st_mtime, fp))
            except OSError:
                continue
        if len(candidates) > 20_000:  # guard against pathological trees
            break

    candidates.sort(key=lambda t: t[0], reverse=True)
    import datetime
    out = []
    for mtime, fp in candidates[:limit]:
        try:
            rel = str(fp.relative_to(root))
        except ValueError:
            rel = str(fp)
        out.append({
            "path": rel,
            "modified": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return out


# A backslash escaping a regex metacharacter -- the signature of a caller
# who assumed this tool takes patterns rather than literal text.
_REGEX_ESCAPE = re.compile(r"\\([.^$*+?()\[\]{}|\\])")


def search_code(
    query: str,
    path: str = ".",
    file_glob: str = "",
    max_results: int = 60,
    regex: bool = False,
) -> dict:
    """
    Search file *contents* and return file:line:text.

    The existing search_files returns matching filenames only, which forces a
    read of each candidate to find out where the match is. Returning the
    matching line with its number is usually enough to decide what to open,
    and is what makes a targeted edit possible straight afterwards.

    Prefers ripgrep when present, falls back to grep so this works on a plain
    machine with nothing installed.
    """
    if not query:
        return {"status": "error", "error": "No search query provided."}

    root = resolve_path(path)
    if not root.exists():
        return {"status": "error", "error": f"No such path: {root}"}

    has_rg = subprocess.run(
        ["which", "rg"], capture_output=True, text=True
    ).returncode == 0

    if has_rg:
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never",
               "--max-count", "10", "-S"]
        if not regex:
            cmd.append("--fixed-strings")
        if file_glob:
            cmd += ["--glob", file_glob]
        cmd += [query, str(root)]
    else:
        cmd = ["grep", "-rn", "-I"]
        if not regex:
            cmd.append("-F")
        for skip in ("node_modules", ".git", "__pycache__", "venv", "dist", "build"):
            cmd += ["--exclude-dir", skip]
        if file_glob:
            cmd += [f"--include={file_glob}"]
        cmd += [query, str(root)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Search timed out. Narrow the path or query."}

    output = (proc.stdout or "").strip()

    # A literal search for text the caller escaped as if it were a regex can
    # never match: the backslashes are searched for too. Callers reasonably
    # assume a code-search tool takes patterns, so this happened repeatedly --
    # five consecutive dead searches for `self.builder\\[rule\\] = builder`
    # in one run, a quarter of that task's step budget, when the unescaped
    # query matched immediately. Retry once without the escapes and say so,
    # rather than returning a bare "no matches" that gives nothing to correct.
    if not output and not regex and _REGEX_ESCAPE.search(query):
        unescaped = _REGEX_ESCAPE.sub(r"\1", query)
        retry = list(cmd)
        retry[-2] = unescaped
        try:
            proc = subprocess.run(retry, capture_output=True, text=True, timeout=30)
            output = (proc.stdout or "").strip()
        except subprocess.TimeoutExpired:
            output = ""
        if output:
            query = unescaped
            note = ("No literal matches for the escaped query; retried with the "
                    "regex escapes removed. This tool matches text literally "
                    "unless you pass regex=true.")
        else:
            note = ""
    else:
        note = ""

    if not output:
        hint = ""
        if not regex and _REGEX_ESCAPE.search(query):
            hint = (" The query is matched literally, so backslash escapes are "
                    "searched for as characters. Try it unescaped, or regex=true.")
        elif not regex:
            hint = " The query is matched literally; pass regex=true for a pattern."
        return {
            "status": "success",
            "query": query,
            "match_count": 0,
            "result": f"No matches for '{query}' in {root}.{hint}",
            "engine": "ripgrep" if has_rg else "grep",
        }

    lines = output.splitlines()
    total = len(lines)
    shown = lines[:max_results]

    cleaned = []
    root_str = str(root)
    for line in shown:
        cleaned.append(line[len(root_str) + 1:] if line.startswith(root_str + "/") else line)

    result = {
        "status": "success",
        "query": query,
        "match_count": total,
        "truncated": total > max_results,
        "engine": "ripgrep" if has_rg else "grep",
        "result": "\n".join(cleaned),
    }
    if note:
        result["note"] = note
    return result
