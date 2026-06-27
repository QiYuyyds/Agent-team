"""Unit tests for skill_service — slugify, contract validation, collision, registry."""

import pytest

from app.services import skill_service as svc
from app.services.skill_service import SkillError

VALID_MD = """---
name: PPT Builder
description: Turn an outline into a polished deck.
---

# How to build a deck
Do the thing.
"""


@pytest.fixture(autouse=True)
def _tmp_skills_root(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(svc, "skills_root", lambda: root)
    return root


# ─── slugify ───
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PPT Builder", "ppt-builder"),
        ("  Hello   World  ", "hello-world"),
        ('bad:name*with?illegal"chars', "bad-name-with-illegal-chars"),
        ("snake_case_name", "snake-case-name"),
    ],
)
def test_slugify(name, expected):
    assert svc.slugify(name) == expected


def test_slugify_empty_result_raises():
    with pytest.raises(SkillError):
        svc.slugify("：？＊")  # full-width / non-ascii only → empty


# ─── parse_skill_md ───
def test_parse_skill_md_ok():
    assert svc.parse_skill_md(VALID_MD) == (
        "PPT Builder",
        "Turn an outline into a polished deck.",
    )


def test_parse_skill_md_missing_field():
    with pytest.raises(SkillError):
        svc.parse_skill_md("---\nname: X\n---\nbody")  # no description


def test_parse_skill_md_no_frontmatter():
    with pytest.raises(SkillError):
        svc.parse_skill_md("# just markdown")


def test_strip_frontmatter():
    assert svc.strip_frontmatter(VALID_MD).startswith("# How to build a deck")


# ─── save_skill / collision ───
def test_save_skill_and_list(_tmp_skills_root):
    meta = svc.save_skill({"SKILL.md": VALID_MD, "scripts/run.py": "print(1)\n"})
    assert meta.slug == "ppt-builder"
    assert (_tmp_skills_root / "ppt-builder" / "SKILL.md").is_file()
    assert (_tmp_skills_root / "ppt-builder" / "scripts" / "run.py").is_file()

    listed = svc.list_skills()
    assert [m.slug for m in listed] == ["ppt-builder"]
    assert listed[0].description == "Turn an outline into a polished deck."


def test_save_skill_requires_skill_md():
    with pytest.raises(SkillError):
        svc.save_skill({"notes.txt": "hi"})


def test_save_skill_collision_rejected():
    svc.save_skill({"SKILL.md": VALID_MD})
    with pytest.raises(SkillError):
        svc.save_skill({"SKILL.md": VALID_MD})


def test_save_skill_rejects_path_escape():
    with pytest.raises(SkillError):
        svc.save_skill({"SKILL.md": VALID_MD, "../evil.txt": "x"})


# ─── list_skills skips broken dirs ───
def test_list_skills_skips_invalid(_tmp_skills_root):
    svc.save_skill({"SKILL.md": VALID_MD})
    (_tmp_skills_root / "broken").mkdir()  # no SKILL.md
    (_tmp_skills_root / "broken" / "readme.txt").write_text("x")
    assert [m.slug for m in svc.list_skills()] == ["ppt-builder"]


# ─── read_skill_body / delete ───
def test_read_skill_body_and_delete():
    svc.save_skill({"SKILL.md": VALID_MD})
    assert "How to build a deck" in svc.read_skill_body("ppt-builder")
    svc.delete_skill("ppt-builder")
    assert svc.list_skills() == []
    with pytest.raises(SkillError):
        svc.read_skill_body("ppt-builder")
