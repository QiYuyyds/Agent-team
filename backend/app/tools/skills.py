"""Skill tools — load_skill (progressive disclosure) and write_skill (agent-authored).

``load_skill`` reads back a skill's SKILL.md body on demand: the run only injects
each equipped skill's name+description into the system prompt, and the model calls
this when it decides a skill is relevant (same shape as memory_recall / rag_search).

``write_skill`` lets an agent author a skill into the shared store; it is opt-in
(never auto-injected — must be in the agent's tool_names), mirroring web_search.
Bundled scripts are stored, never executed here; execution only happens later via
the model's explicit bash call, under the existing blacklist + workspace sandbox.
"""

from __future__ import annotations

from typing import Any

from app.services.skill_service import (
    SKILL_MD,
    SkillError,
    read_skill_body,
    save_skill,
)
from app.tools.base import ToolContext, ToolDef, ToolResult, err, ok


async def load_skill_handler(args: Any, ctx: ToolContext) -> ToolResult:
    name = args.get("name", "").strip() if isinstance(args, dict) else str(args).strip()
    if not name:
        return err("name is required for load_skill")
    try:
        body = read_skill_body(name)
    except SkillError as e:
        return err(str(e))
    return ok({"slug": name, "body": body})


async def write_skill_handler(args: Any, ctx: ToolContext) -> ToolResult:
    if not isinstance(args, dict):
        return err("write_skill requires an object with name/description/body")
    name = (args.get("name") or "").strip()
    description = (args.get("description") or "").strip()
    body = args.get("body") or ""
    if not name or not description:
        return err("write_skill requires non-empty 'name' and 'description'")

    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"
    files: dict[str, str] = {SKILL_MD: skill_md}

    extra = args.get("files")
    if isinstance(extra, dict):
        for rel, content in extra.items():
            if rel == SKILL_MD:
                continue
            files[str(rel)] = content if isinstance(content, str) else str(content)

    try:
        meta = save_skill(files)
    except SkillError as e:
        return err(str(e))
    return ok({"slug": meta.slug, "name": meta.name, "description": meta.description})


load_skill_tool = ToolDef(
    name="load_skill",
    description=(
        "Load the full instructions for one of your equipped skills by its slug. "
        "Your system prompt lists each available skill's name and description; call "
        "this when a task matches a skill to read its SKILL.md body, then follow it. "
        "Bundled files referenced by the skill are read with fs_read and run with bash."
    ),
    parameters={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "The skill slug (as shown in the available-skills list).",
            },
        },
    },
    handler=load_skill_handler,
)


write_skill_tool = ToolDef(
    name="write_skill",
    description=(
        "Author a new reusable skill and save it to the shared skill store. Provide a "
        "short 'name', a one-line 'description' (used to decide when the skill applies), "
        "and the 'body' (Markdown instructions). Optionally include 'files' (a map of "
        "relative path -> text content) for bundled scripts/templates. Fails if a skill "
        "with the same name already exists."
    ),
    parameters={
        "type": "object",
        "required": ["name", "description", "body"],
        "properties": {
            "name": {"type": "string", "description": "Short skill name."},
            "description": {
                "type": "string",
                "description": "One-line summary of when to use this skill.",
            },
            "body": {"type": "string", "description": "Markdown instructions (the skill body)."},
            "files": {
                "type": "object",
                "description": "Optional map of relative path -> text content for bundled files.",
            },
        },
    },
    handler=write_skill_handler,
)
