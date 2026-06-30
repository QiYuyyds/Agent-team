"""Memory writer — LLM-based memory extraction and classification from assistant replies.

Ported from AGI-memory ``internal/agent/memory_writer.py``.
Adapted for AgentHub's async architecture (no threading, uses asyncio.create_task).

Key functions:
  - ``classify_memory_content(key, value)``: Rule-based classification
    (identity/preference/tool_failure/policy).
  - ``extract_memory_from_reply(generate_fn, embed_fn, ltm, content)``:
    Async extraction of k-v facts from assistant replies via LLM,
    followed by classification and ``ltm.store_classified()``.
"""

import json
import logging
import re
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _strip_code_fence(raw: str) -> str:
    """Remove markdown code fences from LLM output."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```json", "", raw)
    raw = re.sub(r"^```", "", raw)
    raw = re.sub(r"```$", "", raw)
    return raw.strip()


def _contains_any(s: str, *subs: str) -> bool:
    """Check if string contains any of the given substrings."""
    return any(sub in s for sub in subs)


# ── Rule-based classification ──────────────────────────────────────────────


def classify_memory_content(key: str, value: str) -> Tuple[str, List[str], str]:
    """Classify memory content using rules.

    Returns (category, tags, slot_hint).
    Returns empty strings if no rule matches (caller should use LLM fallback).

    Ported from AGI-memory classify_memory_content().
    """
    combined = f"{key}{value}"
    if _contains_any(combined, "叫", "名字", "姓名", "是我", "我是"):
        return "identity", ["name"], "profile"
    if _contains_any(combined, "喜欢", "偏好", "习惯", "爱好", "讨厌", "不喜欢", "prefer"):
        return "preference", ["preference"], "profile"
    if _contains_any(combined, "工具", "失败", "错误", "报错", "异常", "error", "bug"):
        return "tool_failure", ["tool", "error"], "tool_state"
    if _contains_any(combined, "禁止", "不要", "不能", "必须", "强制", "must", "never"):
        return "policy", ["constraint"], "constraints"
    return "", [], ""


# ── LLM extraction prompt ──────────────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = (
    "你是一个信息提取助手。从下面的AI回复中提取值得长期记住的客观事实或用户偏好信息。\n"
    "只提取明确的、非临时性的信息，忽略对话上下文和临时细节。\n"
    "输出 JSON 对象（key为信息名称，value为具体值），如果没有值得记忆的信息则输出 {}。\n"
    "只输出 JSON，不要有其他内容。"
)


# ── Async extraction from assistant reply ───────────────────────────────────


async def extract_memory_from_reply(
    generate_fn: Callable,
    embed_fn: Optional[Callable],
    ltm,
    content: str,
) -> None:
    """Extract k-v facts from assistant reply using LLM, classify, and store.

    Workflow:
      1. LLM extracts key-value facts from the reply.
      2. Each fact is classified via ``classify_memory_content()``.
      3. Embedding is computed for each fact.
      4. Facts are stored via ``ltm.store_classified()`` with dedup.

    Args:
        generate_fn: LLM generate function (system_prompt, user_msg) -> str
        embed_fn: Optional embedding function (text) -> list[float]
        ltm: LongTerm memory instance with ``store_classified()`` method
        content: The assistant reply text
    """
    if not content or not generate_fn:
        return

    # Step 1: LLM extraction
    prompt = f"回复：{content}"
    try:
        raw = generate_fn(_EXTRACTION_SYSTEM_PROMPT, prompt)
    except Exception as e:
        logger.warning("Memory extraction LLM call failed: %s", e)
        return

    raw = _strip_code_fence(raw)
    try:
        kvs = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Memory extraction: LLM output is not valid JSON")
        return

    if not isinstance(kvs, dict) or not kvs:
        return

    # Step 2-4: classify, embed, store each fact
    for k, v in kvs.items():
        if not k or v in (None, ""):
            continue

        fact_content = f"用户{k}: {v}"
        category, tags, slot_hint = classify_memory_content(str(k), str(v))
        if not category:
            category = "general"
            tags = []
            slot_hint = "general_knowledge"

        # Compute embedding
        emb = None
        if embed_fn:
            try:
                emb = embed_fn(fact_content)
            except Exception as e:
                logger.warning("Memory extraction embed failed: %s", e)

        importance = 0.7

        # Store via store_classified (with cosine dedup)
        try:
            inserted = await ltm.store_classified(
                fact_content,
                importance,
                emb,
                category,
                tags,
                slot_hint,
            )
            logger.info(
                "Memory extracted: %s = %s (category=%s, inserted=%s)",
                k, v, category, inserted,
            )
        except Exception as e:
            logger.warning("Memory extraction store failed: %s", e)
