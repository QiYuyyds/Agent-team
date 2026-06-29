"""Tests for the fs_glob tool — recursive pattern matching.

Covers: ``**/*.tsx`` matching, result cap truncation, symlink cycle guard,
sandbox escape rejection, and subpath scoping. Calls the tool handler directly
with a ToolContext built from a real sandbox workspace.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest
import pytest_asyncio

from app.services import conversation_service
from app.services.fs_service import get_workspace_for_conversation
from app.tools.base import ToolContext
from app.tools.fs_glob import fs_glob_tool


@pytest_asyncio.fixture
async def ctx(agents) -> ToolContext:
    """A single-agent conversation + ToolContext pointing at its sandbox workspace."""
    conv = await conversation_service.create_conversation(
        mode="single",
        agent_ids=[agents["alice"]],
        title="fs_glob test",
    )
    return ToolContext(
        conversation_id=conv.id,
        workspace_path="",
        agent_id=agents["alice"],
        run_id="run_test_glob",
        cancel_event=asyncio.Event(),
    )


async def _write_file(workspace, rel_path: str, content: str = "x") -> None:
    """Write a file into the workspace sandbox dir."""
    abs_path = os.path.join(workspace.root_path, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)


# --- happy path: **/*.tsx ------------------------------------------------------


async def test_glob_recursive_tsx(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    await _write_file(ws, "src/App.tsx", "export default function App() {}")
    await _write_file(ws, "src/components/Button.tsx", "export const Button = () => null")
    await _write_file(ws, "src/utils/format.ts", "export const fmt = () => ''")
    await _write_file(ws, "README.md", "# project")

    result = await fs_glob_tool.handler({"pattern": "**/*.tsx"}, ctx)
    assert result.ok, result.error
    files = result.value["files"]
    paths = {f["path"] for f in files}
    # Both .tsx files found, .ts and .md excluded
    assert any(p.endswith("App.tsx") for p in paths)
    assert any(p.endswith("Button.tsx") for p in paths)
    assert not any(p.endswith("format.ts") for p in paths)
    assert not any(p.endswith("README.md") for p in paths)
    # All entries are files, not directories
    assert all(not f["is_directory"] for f in files)
    # size is present
    assert all("size" in f for f in files)


# --- result cap / truncation ---------------------------------------------------


async def test_glob_result_cap_truncation(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    # Create 210 files — exceeds MAX_GLOB_RESULTS (200)
    for i in range(210):
        await _write_file(ws, f"batch/file_{i:03d}.txt", str(i))

    result = await fs_glob_tool.handler({"pattern": "batch/*.txt"}, ctx)
    assert result.ok, result.error
    assert len(result.value["files"]) == 200
    assert result.value["truncated"] is True


async def test_glob_no_truncation_under_cap(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    for i in range(10):
        await _write_file(ws, f"small/file_{i}.txt", str(i))

    result = await fs_glob_tool.handler({"pattern": "small/*.txt"}, ctx)
    assert result.ok, result.error
    assert len(result.value["files"]) == 10
    assert result.value["truncated"] is False


# --- subpath scoping -----------------------------------------------------------


async def test_glob_scopes_to_subpath(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    await _write_file(ws, "src/a.ts", "a")
    await _write_file(ws, "src/sub/b.ts", "b")
    await _write_file(ws, "tests/c.ts", "c")

    result = await fs_glob_tool.handler({"pattern": "**/*.ts", "path": "src"}, ctx)
    assert result.ok, result.error
    paths = {f["path"] for f in result.value["files"]}
    assert any("a.ts" in p for p in paths)
    assert any("b.ts" in p for p in paths)
    assert not any("c.ts" in p for p in paths)


# --- sandbox escape rejection --------------------------------------------------


async def test_glob_rejects_path_escape(ctx):
    result = await fs_glob_tool.handler(
        {"pattern": "**/*", "path": "../../.ssh"}, ctx
    )
    assert not result.ok
    assert "outside" in result.error.lower()


async def test_glob_rejects_absolute_escape(ctx):
    # An absolute path outside the workspace should be rejected.
    escape = os.path.abspath(os.path.join(os.sep, "tmp", "nope"))
    result = await fs_glob_tool.handler(
        {"pattern": "**/*", "path": escape}, ctx
    )
    assert not result.ok


# --- symlink cycle guard -------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlink creation requires admin on Windows; cycle guard tested on POSIX",
)
async def test_glob_symlink_cycle_no_hang(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    # Create a directory structure with a symlink cycle: dir_a -> dir_b -> dir_a
    dir_a = os.path.join(ws.root_path, "dir_a")
    dir_b = os.path.join(ws.root_path, "dir_b")
    os.makedirs(dir_a, exist_ok=True)
    os.makedirs(dir_b, exist_ok=True)
    os.symlink(dir_a, os.path.join(dir_b, "link_to_a"))
    os.symlink(dir_b, os.path.join(dir_a, "link_to_b"))
    await _write_file(ws, "dir_a/real_file.txt", "content")

    result = await fs_glob_tool.handler({"pattern": "**/*.txt"}, ctx)
    assert result.ok, result.error
    # Should find the real file without hanging
    paths = {f["path"] for f in result.value["files"]}
    assert any("real_file.txt" in p for p in paths)


# --- not a directory -----------------------------------------------------------


async def test_glob_not_a_directory(ctx):
    ws = await get_workspace_for_conversation(ctx.conversation_id)
    await _write_file(ws, "afile.txt", "x")

    result = await fs_glob_tool.handler({"pattern": "*", "path": "afile.txt"}, ctx)
    assert not result.ok
    assert "not a directory" in result.error.lower()
