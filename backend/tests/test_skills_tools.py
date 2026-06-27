"""Unit tests for the load_skill / write_skill tools."""

import asyncio

import pytest

from app.services import skill_service as svc
from app.tools.base import ToolContext
from app.tools.skills import load_skill_handler, write_skill_handler

VALID_MD = "---\nname: Deck\ndescription: make decks\n---\n\n# steps\n"


@pytest.fixture(autouse=True)
def _tmp_skills_root(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(svc, "skills_root", lambda: root)
    return root


def _ctx() -> ToolContext:
    return ToolContext(
        conversation_id="c", workspace_path="/tmp", agent_id="a",
        run_id="r", cancel_event=asyncio.Event(),
    )


async def test_write_then_load_skill():
    w = await write_skill_handler(
        {"name": "Deck", "description": "make decks", "body": "# steps\nDo it."}, _ctx()
    )
    assert w.ok and w.value["slug"] == "deck"

    r = await load_skill_handler({"name": "deck"}, _ctx())
    assert r.ok
    assert "Do it." in r.value["body"]


async def test_write_skill_collision():
    args = {"name": "Deck", "description": "make decks", "body": "x"}
    assert (await write_skill_handler(args, _ctx())).ok
    dup = await write_skill_handler(args, _ctx())
    assert not dup.ok and "already exists" in dup.error


async def test_write_skill_requires_fields():
    res = await write_skill_handler({"name": "Deck"}, _ctx())
    assert not res.ok


async def test_load_unknown_skill():
    res = await load_skill_handler({"name": "nope"}, _ctx())
    assert not res.ok
