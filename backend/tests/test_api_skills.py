"""API tests for the skills router (app/api/skills.py): upload / list / delete."""

import pytest

VALID_MD = (
    "---\nname: PPT Builder\ndescription: Turn an outline into a deck.\n---\n\n# Body\n"
)


@pytest.fixture(autouse=True)
def _tmp_skills_root(tmp_path, monkeypatch):
    from app.services import skill_service as svc

    root = tmp_path / "skills_store"
    root.mkdir()
    monkeypatch.setattr(svc, "skills_root", lambda: root)
    return root


async def test_upload_single_file_then_list(api_client):
    resp = await api_client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", VALID_MD.encode(), "text/markdown"))],
        data={"paths": ["SKILL.md"]},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["skill"]["slug"] == "ppt-builder"

    listed = await api_client.get("/api/skills")
    assert listed.status_code == 200
    skills = listed.json()["skills"]
    assert [s["slug"] for s in skills] == ["ppt-builder"]


async def test_upload_folder_rebases_to_skill_md(api_client, _tmp_skills_root):
    resp = await api_client.post(
        "/api/skills/upload",
        files=[
            ("files", ("SKILL.md", VALID_MD.encode(), "text/markdown")),
            ("files", ("run.py", b"print(1)\n", "text/x-python")),
        ],
        data={"paths": ["my-skill/SKILL.md", "my-skill/scripts/run.py"]},
    )
    assert resp.status_code == 201, resp.text
    assert (_tmp_skills_root / "ppt-builder" / "scripts" / "run.py").is_file()
    assert (_tmp_skills_root / "ppt-builder" / "SKILL.md").is_file()


async def test_upload_missing_skill_md_rejected(api_client):
    resp = await api_client.post(
        "/api/skills/upload",
        files=[("files", ("notes.txt", b"hi", "text/plain"))],
        data={"paths": ["notes.txt"]},
    )
    assert resp.status_code == 400


async def test_upload_collision_rejected(api_client):
    payload = {
        "files": [("files", ("SKILL.md", VALID_MD.encode(), "text/markdown"))],
        "data": {"paths": ["SKILL.md"]},
    }
    first = await api_client.post("/api/skills/upload", **payload)
    assert first.status_code == 201
    second = await api_client.post("/api/skills/upload", **payload)
    assert second.status_code == 400


async def test_delete_skill(api_client):
    await api_client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", VALID_MD.encode(), "text/markdown"))],
        data={"paths": ["SKILL.md"]},
    )
    resp = await api_client.delete("/api/skills/ppt-builder")
    assert resp.status_code == 200
    listed = await api_client.get("/api/skills")
    assert listed.json()["skills"] == []
