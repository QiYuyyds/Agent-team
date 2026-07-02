"""Dispatch plan parsing + validation + dependency compilation + cycle detection.

Port of src/server/dispatch-plan.ts. Pure module (no DB / native deps) so the
runner's dispatch execution (executeDag, which has side effects) stays in
agent_runner; this module is what the orchestrator imports for plan handling.

Works with the Pydantic ``DispatchPlanItem`` from app.schemas.dispatch: construct
with snake_case kwargs (populate_by_name on) and copy with ``model_copy`` rather
than mutating field-by-field as the TS object literals did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas.artifacts import DispatchExpectedOutputType
from app.schemas.dispatch import (
    DispatchExpectedOutput,
    DispatchPlanItem,
    DispatchRequiredCommand,
    DispatchTaskInput,
    DispatchTaskKind,
)


@dataclass
class InferredDependency:
    """One synthesized dependency edge added by compile (for surfacing to the LLM)."""

    task_id: str
    depends_on: list[str]
    reason: str


@dataclass
class CompileDispatchPlanResult:
    plan: list[DispatchPlanItem]
    inferred_dependencies: list[InferredDependency]


# Artifact topics inferred from task text (PRD → UI design → frontend pipeline):
ArtifactTopic = str  # 'prd' | 'ui_design' | 'frontend'

_WRITABLE_ARTIFACT_TYPES: set[str] = {"web_app", "document", "image", "ppt", "diagram"}
_EXPECTED_OUTPUT_TYPES: set[str] = {*_WRITABLE_ARTIFACT_TYPES, "project"}
_DISPATCH_TASK_KINDS: set[str] = {"code", "test", "review", "design", "doc", "analysis"}

CODE_TASK_PROJECT_OUTPUT_ID = "project"
CODE_TASK_PROJECT_OUTPUT_DESCRIPTION = "Workspace project files written by this code task"
CODE_TASK_RUNNABLE_ACCEPTANCE_CRITERION = (
    "项目构建/编译验证通过（至少一条非准备验证命令 exitCode=0）"
)
CODE_TASK_RUNNABLE_REQUIRED_EVIDENCE = "至少一条构建/编译/测试/类型检查命令 exitCode=0"
PLAN_TASKS_TOOL_NAME = "plan_tasks"

# Code-implementation heuristic (distinguishes real code work from review/analysis):
_CODE_TASK_PATTERN = re.compile(
    r"(?:实现|开发|修复|改造|重构|搭建|脚手架|前端|后端|接口|组件|页面|代码|项目|工程|应用|构建|编译|"
    r"implement|develop|build|scaffold|frontend|backend|api|endpoint|component|page|code|"
    r"project|app|fix|refactor)",
    re.IGNORECASE,
)


# ─── tool-name extraction (MCP naming variants) ──────────────────────
def extract_plan_tasks_tool_args(tool_name: str, args: object) -> object | None:
    """Return args if tool_name is plan_tasks in any MCP naming scheme, else None."""
    if tool_name == PLAN_TASKS_TOOL_NAME:
        return args
    if tool_name == f"mcp__agenthub__{PLAN_TASKS_TOOL_NAME}":
        return args
    if tool_name == f"codex_mcp_agenthub_{PLAN_TASKS_TOOL_NAME}":
        return _read_codex_mcp_tool_arguments(args)
    if tool_name.endswith(f"__{PLAN_TASKS_TOOL_NAME}") or tool_name.endswith(
        f"_{PLAN_TASKS_TOOL_NAME}"
    ):
        return args
    return None


def _read_codex_mcp_tool_arguments(args: object) -> object:
    if not _is_record(args) or args.get("tool") != PLAN_TASKS_TOOL_NAME:
        return args
    raw_arguments = args.get("arguments")
    if not isinstance(raw_arguments, str):
        return raw_arguments
    import json

    try:
        return json.loads(raw_arguments)
    except (ValueError, TypeError):
        return raw_arguments


# ─── parsing ──────────────────────
def parse_dispatch_plan_tool_args(args: object) -> list[DispatchPlanItem]:
    """Parse + validate raw plan_tasks tool args into typed DispatchPlanItems."""
    # Some adapters (MCP-provided tools) deliver args as a JSON string rather
    # than a dict. Parse it before validating.
    if isinstance(args, str):
        import json

        try:
            args = json.loads(args)
        except (ValueError, TypeError):
            raise ValueError(
                "Invalid dispatch plan: plan_tasks args must include a tasks array"
            ) from None

    if not _is_record(args) or not isinstance(args.get("tasks"), list):
        raise ValueError("Invalid dispatch plan: plan_tasks args must include a tasks array")

    result: list[DispatchPlanItem] = []
    for index, raw in enumerate(args["tasks"]):
        if not _is_record(raw):
            raise ValueError(f"Invalid dispatch plan: task at index {index} must be an object")
        item_id = _read_non_empty_string(raw.get("id"), f"task at index {index} id")
        agent_id = _read_non_empty_string(raw.get("agentId"), f'task "{item_id}" agentId')
        task = _read_non_empty_string(raw.get("task"), f'task "{item_id}" instruction')
        task_kind = _read_optional_task_kind(raw.get("taskKind"), f'task "{item_id}" taskKind')

        depends_on: list[str] | None = None
        if "dependsOn" in raw and raw.get("dependsOn") is not None:
            dep_raw = raw["dependsOn"]
            if not isinstance(dep_raw, list):
                raise ValueError(
                    f'Invalid dispatch plan: task "{item_id}" dependsOn must be an array'
                )
            depends_on = [
                _read_non_empty_string(dep, f'task "{item_id}" dependsOn[{i}]')
                for i, dep in enumerate(dep_raw)
            ]

        expected_outputs = _parse_expected_outputs(raw, item_id)
        inputs = _parse_inputs(raw, item_id)
        acceptance_criteria = _parse_string_array(raw, "acceptanceCriteria", item_id)
        target_paths = _parse_string_array(raw, "targetPaths", item_id)
        expected_workspace_changes = _parse_string_array(raw, "expectedWorkspaceChanges", item_id)
        required_commands = _parse_required_commands(raw, item_id)
        required_evidence = _parse_string_array(raw, "requiredEvidence", item_id)

        result.append(
            DispatchPlanItem(
                id=item_id,
                agent_id=agent_id,
                task=task,
                task_kind=task_kind,
                depends_on=depends_on if depends_on else None,
                expected_outputs=expected_outputs if expected_outputs else None,
                inputs=inputs if inputs else None,
                acceptance_criteria=acceptance_criteria if acceptance_criteria else None,
                target_paths=target_paths if target_paths else None,
                expected_workspace_changes=(
                    expected_workspace_changes if expected_workspace_changes else None
                ),
                required_commands=required_commands if required_commands else None,
                required_evidence=required_evidence if required_evidence else None,
            )
        )
    return result


def _parse_expected_outputs(raw: dict, item_id: str) -> list[DispatchExpectedOutput] | None:
    if "expectedOutputs" not in raw or raw.get("expectedOutputs") is None:
        return None
    values = raw["expectedOutputs"]
    if not isinstance(values, list):
        raise ValueError(f'Invalid dispatch plan: task "{item_id}" expectedOutputs must be an array')
    outputs: list[DispatchExpectedOutput] = []
    for i, output in enumerate(values):
        if not _is_record(output):
            raise ValueError(
                f'Invalid dispatch plan: task "{item_id}" expectedOutputs[{i}] must be an object'
            )
        outputs.append(
            DispatchExpectedOutput(
                id=_read_non_empty_string(
                    output.get("id"), f'task "{item_id}" expectedOutputs[{i}].id'
                ),
                type=_read_expected_output_type(
                    output.get("type"), f'task "{item_id}" expectedOutputs[{i}].type'
                ),
                required=_read_optional_boolean(
                    output.get("required"), f'task "{item_id}" expectedOutputs[{i}].required'
                ),
                description=_read_optional_string(
                    output.get("description"), f'task "{item_id}" expectedOutputs[{i}].description'
                ),
            )
        )
    return outputs


def _parse_inputs(raw: dict, item_id: str) -> list[DispatchTaskInput] | None:
    if "inputs" not in raw or raw.get("inputs") is None:
        return None
    values = raw["inputs"]
    if not isinstance(values, list):
        raise ValueError(f'Invalid dispatch plan: task "{item_id}" inputs must be an array')
    inputs: list[DispatchTaskInput] = []
    for i, inp in enumerate(values):
        if not _is_record(inp):
            raise ValueError(
                f'Invalid dispatch plan: task "{item_id}" inputs[{i}] must be an object'
            )
        inputs.append(
            DispatchTaskInput(
                from_task_id=_read_non_empty_string(
                    inp.get("fromTaskId"), f'task "{item_id}" inputs[{i}].fromTaskId'
                ),
                output_id=_read_non_empty_string(
                    inp.get("outputId"), f'task "{item_id}" inputs[{i}].outputId'
                ),
                required=_read_optional_boolean(
                    inp.get("required"), f'task "{item_id}" inputs[{i}].required'
                ),
                description=_read_optional_string(
                    inp.get("description"), f'task "{item_id}" inputs[{i}].description'
                ),
            )
        )
    return inputs


def _parse_required_commands(raw: dict, item_id: str) -> list[DispatchRequiredCommand] | None:
    if "requiredCommands" not in raw or raw.get("requiredCommands") is None:
        return None
    values = raw["requiredCommands"]
    if not isinstance(values, list):
        raise ValueError(
            f'Invalid dispatch plan: task "{item_id}" requiredCommands must be an array'
        )
    commands: list[DispatchRequiredCommand] = []
    for i, command in enumerate(values):
        if not _is_record(command):
            raise ValueError(
                f'Invalid dispatch plan: task "{item_id}" requiredCommands[{i}] must be an object'
            )
        commands.append(
            DispatchRequiredCommand(
                command=_read_non_empty_string(
                    command.get("command"), f'task "{item_id}" requiredCommands[{i}].command'
                ),
                description=_read_optional_string(
                    command.get("description"),
                    f'task "{item_id}" requiredCommands[{i}].description',
                ),
                cwd=_read_optional_string(
                    command.get("cwd"), f'task "{item_id}" requiredCommands[{i}].cwd'
                ),
                timeout_ms=_read_optional_positive_integer(
                    command.get("timeoutMs"), f'task "{item_id}" requiredCommands[{i}].timeoutMs'
                ),
            )
        )
    return commands


def _parse_string_array(raw: dict, key: str, item_id: str) -> list[str] | None:
    if key not in raw or raw.get(key) is None:
        return None
    values = raw[key]
    if not isinstance(values, list):
        raise ValueError(f'Invalid dispatch plan: task "{item_id}" {key} must be an array')
    return [
        _read_non_empty_string(v, f'task "{item_id}" {key}[{i}]') for i, v in enumerate(values)
    ]


# ─── validation ──────────────────────
def validate_dispatch_plan(
    plan: list[DispatchPlanItem],
    available_agents: list,
    orchestrator_agent_id: str,
    resolved_external_tasks: list[DispatchPlanItem] | None = None,
) -> None:
    """Enforce plan invariants (raises ValueError on the first violation)."""
    resolved_external_tasks = resolved_external_tasks or []
    if len(plan) == 0:
        raise ValueError("Invalid dispatch plan: tasks must not be empty")

    available_agent_ids = {_agent_id_of(a) for a in available_agents}
    task_ids: set[str] = set()
    duplicate_task_ids: set[str] = set()
    for task in plan:
        if task.id in task_ids:
            duplicate_task_ids.add(task.id)
        task_ids.add(task.id)
    if duplicate_task_ids:
        joined = ", ".join(sorted(duplicate_task_ids))
        raise ValueError(f"Invalid dispatch plan: duplicate task id(s): {joined}")

    task_by_id = {t.id: t for t in plan}
    external_task_by_id = {t.id: t for t in resolved_external_tasks}

    for task in plan:
        if task.agent_id == orchestrator_agent_id:
            raise ValueError(
                f'Invalid dispatch plan: task "{task.id}" dispatches to the orchestrator '
                "itself, which would recurse"
            )
        if task.agent_id not in available_agent_ids:
            raise ValueError(
                f'Invalid dispatch plan: task "{task.id}" references unavailable '
                f'agentId "{task.agent_id}"'
            )

        dep_ids: set[str] = set()
        for dep in task.depends_on or []:
            if dep == task.id:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" cannot depend on itself'
                )
            if dep in dep_ids:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" lists duplicate dependency "{dep}"'
                )
            dep_ids.add(dep)
            if dep not in task_ids and dep not in external_task_by_id:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" depends on unknown task "{dep}"'
                )

        output_ids: set[str] = set()
        for output in task.expected_outputs or []:
            if output.id in output_ids:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" lists duplicate expected '
                    f'output "{output.id}"'
                )
            output_ids.add(output.id)

        for inp in task.inputs or []:
            if inp.from_task_id == task.id:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" input cannot reference itself'
                )
            upstream = task_by_id.get(inp.from_task_id) or external_task_by_id.get(inp.from_task_id)
            if upstream is None:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" input references unknown '
                    f'task "{inp.from_task_id}"'
                )
            output_exists = any(o.id == inp.output_id for o in (upstream.expected_outputs or []))
            if not output_exists:
                raise ValueError(
                    f'Invalid dispatch plan: task "{task.id}" input references unknown '
                    f'output "{inp.output_id}" from task "{inp.from_task_id}"'
                )

    assert_acyclic_dispatch_plan(plan)


# ─── compilation ──────────────────────
def compile_dispatch_plan(plan: list[DispatchPlanItem]) -> CompileDispatchPlanResult:
    """Infer extra deps from task text + normalize code-task contracts."""
    inferred_dependencies: list[InferredDependency] = []
    compiled: list[DispatchPlanItem] = []

    for index, task in enumerate(plan):
        previous_tasks = plan[:index]
        inferred = _infer_dependencies_for_task(task, previous_tasks)
        explicit = list(task.depends_on or [])
        input_deps = [inp.from_task_id for inp in (task.inputs or [])]
        dependency_set = set(explicit)
        dependencies = list(explicit)
        additions = [dep for dep in inferred if dep not in dependency_set]
        for dep in additions:
            dependencies.append(dep)
            dependency_set.add(dep)
        for dep in input_deps:
            if dep in dependency_set:
                continue
            dependencies.append(dep)
            dependency_set.add(dep)

        item = task.model_copy(update={"depends_on": dependencies if dependencies else None})

        if additions:
            inferred_dependencies.append(
                InferredDependency(
                    task_id=task.id,
                    depends_on=additions,
                    reason="task text references earlier task output",
                )
            )

        compiled.append(normalize_task_contract(item))

    return CompileDispatchPlanResult(plan=compiled, inferred_dependencies=inferred_dependencies)


def compile_and_validate_dispatch_plan(
    plan: list[DispatchPlanItem],
    available_agents: list,
    orchestrator_agent_id: str,
    resolved_external_tasks: list[DispatchPlanItem] | None = None,
) -> CompileDispatchPlanResult:
    """Validate the raw plan, then compile (infer deps + normalize contracts)."""
    validate_dispatch_plan(plan, available_agents, orchestrator_agent_id, resolved_external_tasks)
    return compile_dispatch_plan(plan)


def normalize_task_contract(task: DispatchPlanItem) -> DispatchPlanItem:
    """For code tasks: ensure a project output + runnable acceptance/evidence."""
    if not is_code_implementation_task(task):
        return task
    return task.model_copy(
        update={
            "expected_outputs": _ensure_code_project_output(task.expected_outputs or []),
            "acceptance_criteria": _append_unique(
                task.acceptance_criteria or [], CODE_TASK_RUNNABLE_ACCEPTANCE_CRITERION
            ),
            "required_evidence": _append_unique(
                task.required_evidence or [], CODE_TASK_RUNNABLE_REQUIRED_EVIDENCE
            ),
        }
    )


def is_code_implementation_task(task: DispatchPlanItem) -> bool:
    """Heuristic: is this real code work (vs review/analysis)?"""
    if task.task_kind is not None:
        return task.task_kind == "code"
    if any(o.type == "project" for o in (task.expected_outputs or [])):
        return True
    if (
        (task.target_paths or []) or (task.expected_workspace_changes or [])
    ) and not _is_review_task(task.task):
        return True
    return bool(_CODE_TASK_PATTERN.search(task.task)) and not _is_review_task(task.task)


def _ensure_code_project_output(
    outputs: list[DispatchExpectedOutput],
) -> list[DispatchExpectedOutput]:
    has_project = False
    normalized: list[DispatchExpectedOutput] = []
    for output in outputs:
        if output.type != "project":
            normalized.append(output)
            continue
        has_project = True
        normalized.append(
            output.model_copy(
                update={
                    "required": True,
                    "description": output.description or CODE_TASK_PROJECT_OUTPUT_DESCRIPTION,
                }
            )
        )
    if has_project:
        return normalized
    normalized.append(
        DispatchExpectedOutput(
            id=_next_unique_output_id(outputs, CODE_TASK_PROJECT_OUTPUT_ID),
            type="project",
            required=True,
            description=CODE_TASK_PROJECT_OUTPUT_DESCRIPTION,
        )
    )
    return normalized


def _next_unique_output_id(outputs: list[DispatchExpectedOutput], preferred: str) -> str:
    used = {o.id for o in outputs}
    if preferred not in used:
        return preferred
    index = 2
    while True:
        candidate = f"{preferred}_{index}"
        if candidate not in used:
            return candidate
        index += 1


def _append_unique(values: list[str], value: str) -> list[str]:
    normalized = {v.strip() for v in values}
    return values if value in normalized else [*values, value]


# ─── graph queries ──────────────────────
def collect_dependency_closure(plan: list[DispatchPlanItem], task_id: str) -> list[str]:
    """Ordered transitive dependencies for a task (empty if task not found)."""
    by_id = {t.id: t for t in plan}
    task = by_id.get(task_id)
    if task is None:
        return []

    seen: set[str] = set()
    ordered: list[str] = []

    def visit(dep_id: str) -> None:
        if dep_id in seen:
            return
        dep = by_id.get(dep_id)
        if dep is None:
            return
        for nested in dep.depends_on or []:
            visit(nested)
        seen.add(dep_id)
        ordered.append(dep_id)

    for dep in task.depends_on or []:
        visit(dep)
    return ordered


def task_expects_artifact(task: DispatchPlanItem) -> bool:
    """Heuristic: does this task plan to produce an artifact?"""
    if any(o.required is not False for o in (task.expected_outputs or [])):
        return True
    text = task.task
    return (
        len(_get_produced_artifact_topics(text)) > 0
        or bool(_ARTIFACT_PRODUCE_PATTERN_A.search(text))
        or bool(_ARTIFACT_PRODUCE_PATTERN_B.search(text))
        or bool(_ARTIFACT_TYPE_PATTERN.search(text))
        or bool(_ARTIFACT_TITLE_PATTERN.search(text))
    )


def get_required_expected_outputs(task: DispatchPlanItem) -> list[DispatchExpectedOutput]:
    return [o for o in (task.expected_outputs or []) if o.required is not False]


def assert_acyclic_dispatch_plan(plan: list[DispatchPlanItem]) -> None:
    """Depth-first cycle detection (raises ValueError naming the cycle path)."""
    by_id = {t.id: t for t in plan}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        if task_id in visiting:
            cycle_start = stack.index(task_id)
            cycle = [*stack[cycle_start:], task_id]
            raise ValueError(
                f"Invalid dispatch plan: circular dependency {' -> '.join(cycle)}"
            )
        task = by_id.get(task_id)
        if task is None:
            return
        visiting.add(task_id)
        stack.append(task_id)
        for dep in task.depends_on or []:
            visit(dep)
        stack.pop()
        visiting.discard(task_id)
        visited.add(task_id)

    for task in plan:
        visit(task.id)


# ─── dependency inference (text heuristics) ──────────────────────
def _infer_dependencies_for_task(
    task: DispatchPlanItem, previous_tasks: list[DispatchPlanItem]
) -> list[str]:
    inferred: set[str] = set()
    task_text = task.task

    if _has_dependency_signal(task_text):
        for previous in previous_tasks:
            if _contains_task_id_reference(task_text, previous.id):
                inferred.add(previous.id)

    consumed_topics = _get_consumed_artifact_topics(task_text)
    if consumed_topics:
        for previous in previous_tasks:
            produced_topics = _get_produced_artifact_topics(previous.task)
            if consumed_topics & produced_topics:
                inferred.add(previous.id)

    if _is_review_task(task_text):
        for previous in previous_tasks:
            if (
                task_expects_artifact(previous)
                or len(_get_produced_artifact_topics(previous.task)) > 0
            ):
                inferred.add(previous.id)

    # preserve previous-task order:
    return [p.id for p in previous_tasks if p.id in inferred]


_DEPENDENCY_SIGNAL_PATTERN = re.compile(
    r"(读取|基于|参考|根据|按照|依赖|等待|待.{0,12}完成|前序|上游|产物|输出|结果|审查|检查|"
    r"验收|read|review|artifact)",
    re.IGNORECASE,
)


def _has_dependency_signal(text: str) -> bool:
    return bool(_DEPENDENCY_SIGNAL_PATTERN.search(text))


def _contains_task_id_reference(text: str, task_id: str) -> bool:
    escaped = re.escape(task_id)
    return bool(
        re.search(rf"(^|[^A-Za-z0-9_-]){escaped}([^A-Za-z0-9_-]|$)", text, re.IGNORECASE)
    )


def _get_consumed_artifact_topics(text: str) -> set[str]:
    topics: set[str] = set()
    if _consumes_prd(text):
        topics.add("prd")
    if _consumes_ui_design(text):
        topics.add("ui_design")
    if _consumes_frontend(text):
        topics.add("frontend")
    return topics


def _get_produced_artifact_topics(text: str) -> set[str]:
    topics: set[str] = set()
    if _produces_prd(text):
        topics.add("prd")
    if _produces_ui_design(text):
        topics.add("ui_design")
    if _produces_frontend(text):
        topics.add("frontend")
    return topics


_CONSUMES_PRD_PATTERN = re.compile(
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|read|review).{0,40}(?:PRD|产品需求|需求文档)|"
    r"(?:PRD|产品需求|需求文档).{0,40}(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|符合|read|review)",
    re.IGNORECASE,
)
_CONSUMES_UI_PATTERN = re.compile(
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|read|review).{0,40}(?:UI|设计稿|设计方案|风格指南)|"
    r"(?:UI|设计稿|设计方案|风格指南).{0,40}(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|符合|read|review)",
    re.IGNORECASE,
)
_CONSUMES_FRONTEND_PATTERN = re.compile(
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|read|review).{0,48}"
    r"(?:前端|web_app|web app|HTML|网页|实现|代码)|"
    r"(?:前端|web_app|web app|HTML|网页|实现|代码).{0,48}"
    r"(?:读取|基于|参考|根据|按照|了解|审查|检查|验收|符合|产出|artifact|read|review)",
    re.IGNORECASE,
)
_PRODUCES_PRD_PATTERN = re.compile(
    r"(?:产出|输出|撰写|写入|生成|创建).{0,32}(?:PRD|产品需求|需求文档)|"
    r"(?:PRD|产品需求|需求文档).{0,32}(?:产出|输出|撰写|写入|生成|创建)",
    re.IGNORECASE,
)
_PRODUCES_UI_PATTERN = re.compile(
    r"(?:产出|输出|设计|写入|生成|创建).{0,32}(?:UI|设计稿|设计方案|风格指南)|"
    r"(?:UI|设计稿|设计方案|风格指南).{0,32}(?:产出|输出|写入|生成|创建)",
    re.IGNORECASE,
)
_PRODUCES_FRONTEND_PATTERN = re.compile(
    r"(?:实现|开发|输出|产出|写入|生成|创建).{0,48}(?:前端|web_app|web app|HTML|网页|代码|应用)|"
    r"(?:前端|web_app|web app|HTML|网页|代码|应用).{0,48}(?:实现|开发|输出|产出|写入|生成|创建)",
    re.IGNORECASE,
)
_REVIEW_TASK_PATTERN = re.compile(r"审查|检查|验收|review|inspect|validate", re.IGNORECASE)

_ARTIFACT_PRODUCE_PATTERN_A = re.compile(
    r"(?:输出|产出|写入|生成|创建|保存).{0,40}"
    r"(?:artifact|artifacts|产物|document|web_app|web app|diagram|mermaid|diff|code_file|"
    r"markdown|文档|报告|网页|应用|代码|PRD|设计|图)",
    re.IGNORECASE,
)
_ARTIFACT_PRODUCE_PATTERN_B = re.compile(
    r"(?:artifact|artifacts|产物|document|web_app|web app|diagram|mermaid|diff|code_file|"
    r"markdown|文档|报告|网页|应用|代码|PRD|设计|图).{0,40}(?:输出|产出|写入|生成|创建|保存)",
    re.IGNORECASE,
)
_ARTIFACT_TYPE_PATTERN = re.compile(
    r"(?:类型为|type\s*[:=]).{0,24}(?:document|web_app|web app|diagram|diff|code_file|image|markdown)",
    re.IGNORECASE,
)
_ARTIFACT_TITLE_PATTERN = re.compile(r"title\s*(?:为|:|=)", re.IGNORECASE)


def _consumes_prd(text: str) -> bool:
    return bool(_CONSUMES_PRD_PATTERN.search(text))


def _consumes_ui_design(text: str) -> bool:
    return bool(_CONSUMES_UI_PATTERN.search(text))


def _consumes_frontend(text: str) -> bool:
    return bool(_CONSUMES_FRONTEND_PATTERN.search(text))


def _produces_prd(text: str) -> bool:
    return bool(_PRODUCES_PRD_PATTERN.search(text))


def _produces_ui_design(text: str) -> bool:
    return bool(_PRODUCES_UI_PATTERN.search(text))


def _produces_frontend(text: str) -> bool:
    return bool(_PRODUCES_FRONTEND_PATTERN.search(text))


def _is_review_task(text: str) -> bool:
    return bool(_REVIEW_TASK_PATTERN.search(text))


# ─── primitive readers ──────────────────────
def _read_non_empty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value.strip()) == 0:
        raise ValueError(f"Invalid dispatch plan: {label} must be a non-empty string")
    return value


def _read_optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid dispatch plan: {label} must be a string")
    trimmed = value.strip()
    return trimmed if len(trimmed) > 0 else None


def _read_optional_boolean(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"Invalid dispatch plan: {label} must be a boolean")
    return value


def _read_optional_positive_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    # bool is an int subclass; reject it explicitly to match the TS Number.isInteger check.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Invalid dispatch plan: {label} must be a positive integer")
    return value


def _read_optional_task_kind(value: object, label: str) -> DispatchTaskKind | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in _DISPATCH_TASK_KINDS:
        joined = ", ".join(sorted(_DISPATCH_TASK_KINDS))
        raise ValueError(f"Invalid dispatch plan: {label} must be one of {joined}")
    return value  # type: ignore[return-value]


def _read_expected_output_type(value: object, label: str) -> DispatchExpectedOutputType:
    if not isinstance(value, str) or value not in _EXPECTED_OUTPUT_TYPES:
        joined = ", ".join(sorted(_EXPECTED_OUTPUT_TYPES))
        raise ValueError(f"Invalid dispatch plan: {label} must be one of {joined}")
    return value  # type: ignore[return-value]


def _is_record(value: object) -> bool:
    return isinstance(value, dict)


def _agent_id_of(agent: object) -> str:
    if isinstance(agent, dict):
        return agent["id"]
    return agent.id  # type: ignore[attr-defined]


# ─── dynamic re-planning ──────────────────────
@dataclass
class ReplanTaskView:
    task_id: str
    agent_id: str
    status: str  # 'complete' | 'failed' | 'skipped' | 'aborted'
    error: str | None = None


@dataclass
class ReplanConflictView:
    path: str
    task_ids: list[str]


def should_replan(views: list[ReplanTaskView], conflicts: list[ReplanConflictView]) -> bool:
    """A remediation round is needed if any task is not complete, or there are conflicts."""
    return any(v.status != "complete" for v in views) or len(conflicts) > 0


def _json_str(value: object) -> str:
    """JS JSON.stringify of a string (compact, non-ascii preserved)."""
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_replan_context(
    views: list[ReplanTaskView],
    conflicts: list[ReplanConflictView],
) -> str:
    """Summarise the previous round (done / failed / conflicts) as a plan-stage prefix."""
    done = [v for v in views if v.status == "complete"]
    failed = [v for v in views if v.status != "complete"]
    lines: list[str] = ["<previous_round_results>"]
    for v in done:
        lines.append(f'  <task id="{v.task_id}" agent="{v.agent_id}" status="complete" />')
    for v in failed:
        err = f" error={_json_str(v.error)}" if v.error else ""
        lines.append(f'  <task id="{v.task_id}" agent="{v.agent_id}" status="{v.status}"{err} />')
    lines.append("</previous_round_results>")
    if conflicts:
        lines.append("<file_conflicts>")
        for c in conflicts:
            lines.append(
                f"  <conflict path={_json_str(c.path)} tasks={_json_str(', '.join(c.task_ids))} />"
            )
        lines.append("</file_conflicts>")
    lines.extend(
        [
            "",
            "上一轮存在未完成任务或写冲突。请围绕 original_request 的原始目标输出补救 plan_tasks，只修复未完成 / 冲突 / 缺失证据的部分：可换更合适的 agent、把写同一文件的任务用 dependsOn 串行化、或把任务拆得更细。不要把实现任务缩小成静态审查、总结或解释；除非用户明确同意缩小范围，否则补救计划必须继续追踪原始目标的未完成验收。已 complete 的任务不要重做；补救任务需要基于已 complete 任务时，可以在 dependsOn / inputs 中引用上一轮的 task id，系统会把它当作已解析的外部依赖。若判断无需或无法补救，就不要调用 plan_tasks（直接进入总结）。",
        ]
    )
    return "\n".join(lines)


def build_revise_context(current_plan: list[DispatchPlanItem], feedback: str) -> str:
    """Combine the pending plan + user's free-text feedback as a re-plan prefix."""
    lines: list[str] = ["<current_plan>"]
    for t in current_plan:
        deps = (
            f" dependsOn={_json_str(', '.join(t.depends_on))}"
            if t.depends_on and len(t.depends_on) > 0
            else ""
        )
        lines.append(f'  <task id="{t.id}" agent="{t.agent_id}"{deps}>{t.task}</task>')
    lines.append("</current_plan>")
    lines.extend(
        [
            "<user_revision_request>",
            feedback,
            "</user_revision_request>",
            "",
            "用户对上面这份待执行计划提出了修改意见。请据此调整，重新调用 plan_tasks 输出**完整的新计划**：保留未被要求改动的任务，只改动用户要求的部分（依赖、执行者、任务描述、拆分等）。",
        ]
    )
    return "\n".join(lines)
