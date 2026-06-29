"""fs_grep tool — regex text search inside the workspace.

Uses ``re.compile()`` + ``pathlib.Path.rglob()`` to scan files line by line
(pure Python stdlib, no ``ripgrep`` binary dependency). Skips binary files
(null-byte detection), dependency directories (``node_modules`` / ``.git``),
enforces a per-file match cap (50) and a total result cap (default 100), and
has a 10-second timeout that returns partial results.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.fs_service import get_workspace_for_conversation
from app.tools.base import ToolContext, ToolDef, ToolResult, err, ok
from app.utils.workspace_utils import assert_path_within_workspace, get_effective_cwd

MAX_RESULTS_DEFAULT = 100
PER_FILE_MATCH_CAP = 50
SEARCH_TIMEOUT_SECONDS = 10.0
_BINARY_THRESHOLD = 8192  # read first N bytes to check for null bytes

_SKIP_DIRS = {"node_modules", ".git", ".venv", "__pycache__", ".next", "dist", "build"}


class _Args(BaseModel):
    pattern: str = Field(min_length=1)
    path: str = ""
    glob: str = ""
    max_results: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=1000)


_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "required": ["pattern"],
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Regular expression to search for (Python re syntax).",
        },
        "path": {
            "type": "string",
            "description": (
                "Optional subdirectory to search in (relative to workspace root). "
                "Omit for the whole workspace."
            ),
        },
        "glob": {
            "type": "string",
            "description": (
                "Optional file glob filter, e.g. '*.py' or '*.tsx'. Only files "
                "matching this pattern are searched."
            ),
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum number of matches to return (default 100).",
            "default": MAX_RESULTS_DEFAULT,
        },
    },
}


_DESCRIPTION = (
    "Search for a regular expression inside workspace files. Returns structured "
    "matches with file, line_number, line, and match text. Skips binary files "
    "(null-byte detection) and dependency directories (node_modules, .git). "
    "Per-file cap is 50 matches; total default cap is 100 (override with "
    "max_results). A 10-second timeout returns partial results. Use this to find "
    "code symbols, function calls, or text patterns across a project."
)


def _is_binary(path: Path) -> bool:
    """Detect binary files by checking for null bytes in the first chunk."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_THRESHOLD)
        return b"\x00" in chunk
    except OSError:
        return True  # treat unreadable as binary (skip)


def _iter_search_files(root: Path, glob_filter: str):
    """Yield files under root, skipping dependency dirs and honoring glob filter."""
    for entry in root.rglob("*"):
        # Skip dependency directories and common build artifacts.
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        if not entry.is_file():
            continue
        if glob_filter:
            # Use Path's match for simple glob filtering (e.g. "*.py").
            if not entry.match(glob_filter):
                continue
        yield entry


async def _handler(args: Any, ctx: ToolContext) -> ToolResult:
    try:
        parsed = _Args.model_validate(args or {})
    except ValidationError as e:
        return err(f"Invalid args: {e}")

    workspace = await get_workspace_for_conversation(ctx.conversation_id)
    if workspace is None:
        return err("Workspace not found")

    # Resolve the search root.
    try:
        search_root = (
            get_effective_cwd(workspace)
            if parsed.path == ""
            else assert_path_within_workspace(workspace, parsed.path)
        )
    except ValueError as e:
        return err(str(e))

    if not os.path.isdir(search_root):
        return err(f"Not a directory: {parsed.path or '(root)'}")

    # Compile the regex.
    try:
        regex = re.compile(parsed.pattern)
    except re.error as e:
        return err(f"Invalid regex: {e}")

    cwd = get_effective_cwd(workspace)
    matches: list[dict[str, Any]] = []
    total_matches = 0
    truncated = False
    timed_out = False
    start = time.monotonic()

    for file_path in _iter_search_files(Path(search_root), parsed.glob):
        if timed_out:
            break

        # Per-file match cap
        file_matches = 0
        if _is_binary(file_path):
            continue

        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                for line_no, line in enumerate(f, start=1):
                    if file_matches >= PER_FILE_MATCH_CAP:
                        break
                    m = regex.search(line)
                    if m:
                        file_matches += 1
                        total_matches += 1
                        # Only collect up to max_results
                        if len(matches) < parsed.max_results:
                            try:
                                rel = os.path.relpath(str(file_path), cwd)
                            except ValueError:
                                rel = str(file_path)
                            matches.append(
                                {
                                    "file": rel,
                                    "line_number": line_no,
                                    "line": line.rstrip("\n\r"),
                                    "match": m.group(0),
                                }
                            )
                        else:
                            truncated = True

                    # Check timeout periodically (per line is fine, it's cheap)
                    if time.monotonic() - start > SEARCH_TIMEOUT_SECONDS:
                        timed_out = True
                        break
        except OSError:
            continue

        # Also check timeout between files
        if time.monotonic() - start > SEARCH_TIMEOUT_SECONDS:
            timed_out = True
            break

    result: dict[str, Any] = {
        "matches": matches,
        "total_matches": total_matches,
        "truncated": truncated or timed_out,
    }
    if timed_out:
        result["timeout"] = True
    return ok(result)


fs_grep_tool = ToolDef(
    name="fs_grep",
    description=_DESCRIPTION,
    parameters=_PARAMETERS,
    handler=_handler,
)
