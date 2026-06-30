#!/usr/bin/env python
"""RAG evaluation metrics module.

Provides:
  - Content-based hit detection: is_hit()
  - Retrieval-layer metrics (pure computation):
      recall_at_k, precision_at_k, mrr, ndcg_at_k
  - Generation-layer metrics (LLM-as-judge):
      faithfulness, answer_relevance, answer_quality

All retrieval metrics use is_hit() for relevance determination and return 0.0
on empty input. Generation metrics use dedicated prompt templates that
constrain the LLM to output only a numeric score in [0.0, 1.0].
"""

import math
import re
from typing import Callable

# Type alias for the LLM generate function signature
LLMFn = Callable[[str, str], str]


# ═══════════════════════════════════════════════════════════════════════════
#  Hit Detection
# ═══════════════════════════════════════════════════════════════════════════

def is_hit(chunk_content: str, relevant_docs: list[str], prefix_len: int = 50) -> bool:
    """Determine whether a retrieved chunk is relevant via bidirectional substring matching.

    Matching logic:
      1. Extract the first `prefix_len` characters of `chunk_content`.
      2. Check if that prefix appears as a substring in any relevant doc.
      3. Also check if the first `prefix_len` characters of any relevant doc
         appear as a substring in `chunk_content` (reverse direction).

    Args:
        chunk_content: The content text of a retrieved chunk.
        relevant_docs: List of ground-truth relevant document full texts.
        prefix_len: Number of characters to use as matching prefix (default 50).

    Returns:
        True if the chunk matches any relevant doc, False otherwise.
        Returns False for empty or whitespace-only prefixes.
    """
    prefix = chunk_content[:prefix_len].strip()
    if not prefix:
        return False

    for doc in relevant_docs:
        if not doc:
            continue
        # Forward: chunk prefix is a substring of the relevant doc
        if prefix in doc:
            return True
        # Reverse: relevant doc's prefix is a substring of the chunk
        doc_prefix = doc[:prefix_len].strip()
        if doc_prefix and doc_prefix in chunk_content:
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
#  Retrieval-Layer Metrics
# ═══════════════════════════════════════════════════════════════════════════

def recall_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float:
    """Fraction of relevant documents found in the top-K retrieved chunks.

    A relevant document is "found" if at least one of the top-K retrieved
    chunks matches it via is_hit().

    Returns 0.0 if retrieved is empty or relevant_docs is empty.
    """
    if not retrieved or not relevant_docs:
        return 0.0

    top_k = retrieved[:k]
    found_count = 0
    for doc in relevant_docs:
        for chunk in top_k:
            if is_hit(chunk, relevant_docs=[doc]):
                found_count += 1
                break

    return found_count / len(relevant_docs)


def precision_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float:
    """Fraction of top-K retrieved chunks that are relevant.

    Returns 0.0 if retrieved is empty.
    """
    if not retrieved:
        return 0.0

    top_k = retrieved[:k]
    if not top_k:
        return 0.0

    hit_count = sum(1 for chunk in top_k if is_hit(chunk, relevant_docs))
    return hit_count / len(top_k)


def mrr(retrieved: list[str], relevant_docs: list[str]) -> float:
    """Reciprocal rank of the first relevant chunk.

    Returns 1/rank (1-indexed) of the first retrieved chunk that matches
    any relevant doc. Returns 0.0 if no hit is found or retrieved is empty.
    """
    if not retrieved:
        return 0.0

    for rank, chunk in enumerate(retrieved, start=1):
        if is_hit(chunk, relevant_docs):
            return 1.0 / rank

    return 0.0


def ndcg_at_k(retrieved: list[str], relevant_docs: list[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain at K.

    Uses binary relevance (rel = 1 if is_hit, 0 otherwise).
    DCG@K  = sum_{i=1}^{K}  rel_i / log2(i + 1)
    IDCG@K = sum_{i=1}^{min(K, R)}  1 / log2(i + 1)   (R = num relevant docs)
    NDCG@K = DCG@K / IDCG@K

    Returns 0.0 if retrieved is empty, relevant_docs is empty, or IDCG is 0.
    """
    if not retrieved or not relevant_docs:
        return 0.0

    top_k = retrieved[:k]
    num_relevant = len(relevant_docs)

    # DCG: actual ranking
    dcg = 0.0
    for i, chunk in enumerate(top_k):
        rank = i + 1  # 1-indexed
        rel = 1 if is_hit(chunk, relevant_docs) else 0
        if rel > 0:
            dcg += rel / math.log2(rank + 1)

    # IDCG: ideal ranking (all relevant docs at the top)
    ideal_hits = min(k, num_relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))

    if idcg == 0:
        return 0.0

    return dcg / idcg


# ═══════════════════════════════════════════════════════════════════════════
#  Generation-Layer Metrics (LLM-as-judge)
# ═══════════════════════════════════════════════════════════════════════════

def _parse_score(raw_response: str) -> float:
    """Extract a numeric score from the LLM response.

    Looks for a float/int in the response string. Clamps to [0.0, 1.0].
    Returns 0.0 if no number is found.
    """
    if not raw_response:
        return 0.0
    # Find the first number (int or float) in the response
    match = re.search(r"(\d+\.?\d*)", raw_response.strip())
    if not match:
        return 0.0
    try:
        score = float(match.group(1))
    except ValueError:
        return 0.0
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))


def faithfulness(question: str, answer: str, context: str, llm_fn: LLMFn) -> float:
    """Evaluate whether the answer is fully grounded in the provided context.

    Faithfulness measures the degree to which the answer contains only
    information present in the context (no fabrication/hallucination).

    Args:
        question: The user's question.
        answer: The generated answer to evaluate.
        context: The retrieved context provided to the generator.
        llm_fn: LLM function with signature (system_prompt, user_msg) -> str.

    Returns:
        Float score in [0.0, 1.0], where 1.0 = fully faithful.
    """
    system_prompt = (
        "你是一个严格的事实核查员。请评估以下回答是否完全基于提供的上下文信息，"
        "没有捏造或添加上下文中不存在的信息。\n\n"
        "评分标准：\n"
        "- 1.0：回答完全基于上下文，无任何捏造信息\n"
        "- 0.5：回答部分基于上下文，包含少量未在上下文中出现的信息\n"
        "- 0.0：回答完全脱离上下文，包含大量捏造信息\n\n"
        "请只输出一个0到1之间的数字（可保留小数），不要输出任何其他内容。"
    )
    user_msg = (
        f"【上下文】\n{context}\n\n"
        f"【问题】\n{question}\n\n"
        f"【待评估回答】\n{answer}\n\n"
        f"请评估该回答的忠实度（faithfulness），只输出一个0到1之间的数字："
    )
    try:
        response = llm_fn(system_prompt, user_msg)
        return _parse_score(response)
    except Exception:
        return 0.0


def answer_relevance(question: str, answer: str, llm_fn: LLMFn) -> float:
    """Evaluate whether the answer directly addresses the question.

    Answer relevance measures the degree to which the answer is responsive
    to the specific question asked.

    Args:
        question: The user's question.
        answer: The generated answer to evaluate.
        llm_fn: LLM function with signature (system_prompt, user_msg) -> str.

    Returns:
        Float score in [0.0, 1.0], where 1.0 = perfectly relevant.
    """
    system_prompt = (
        "你是一个专业的问答评估员。请评估以下回答是否直接且准确地回应了用户的问题。\n\n"
        "评分标准：\n"
        "- 1.0：回答完全且准确地回应了问题\n"
        "- 0.5：回答部分回应了问题，但不够完整或略有偏题\n"
        "- 0.0：回答完全没有回应问题或答非所问\n\n"
        "请只输出一个0到1之间的数字（可保留小数），不要输出任何其他内容。"
    )
    user_msg = (
        f"【问题】\n{question}\n\n"
        f"【待评估回答】\n{answer}\n\n"
        f"请评估该回答的相关性（answer relevance），只输出一个0到1之间的数字："
    )
    try:
        response = llm_fn(system_prompt, user_msg)
        return _parse_score(response)
    except Exception:
        return 0.0


def answer_quality(ground_truth: str, generated: str, llm_fn: LLMFn) -> float:
    """Evaluate semantic consistency between the generated answer and ground truth.

    Answer quality measures the degree of semantic agreement between the
    model's generated answer and the reference (ground truth) answer.

    Args:
        ground_truth: The reference/correct answer.
        generated: The generated answer to evaluate.
        llm_fn: LLM function with signature (system_prompt, user_msg) -> str.

    Returns:
        Float score in [0.0, 1.0], where 1.0 = semantically identical.
    """
    system_prompt = (
        "你是一个专业的答案质量评估员。请比较生成的回答与标准答案之间的语义一致性。\n\n"
        "评分标准：\n"
        "- 1.0：生成的回答与标准答案语义完全一致\n"
        "- 0.5：生成的回答与标准答案部分一致，但存在差异\n"
        "- 0.0：生成的回答与标准答案完全不一致\n\n"
        "注意：评估的是语义一致性而非字面完全相同。只要核心意思一致即可给高分。\n"
        "请只输出一个0到1之间的数字（可保留小数），不要输出任何其他内容。"
    )
    user_msg = (
        f"【标准答案】\n{ground_truth}\n\n"
        f"【生成的回答】\n{generated}\n\n"
        f"请评估生成回答的质量（answer quality），只输出一个0到1之间的数字："
    )
    try:
        response = llm_fn(system_prompt, user_msg)
        return _parse_score(response)
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  Aggregated metric names for report generation
# ═══════════════════════════════════════════════════════════════════════════

RETRIEVAL_METRICS = ["recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"]
GENERATION_METRICS = ["faithfulness", "answer_relevance", "answer_quality"]
ALL_METRICS = RETRIEVAL_METRICS + GENERATION_METRICS
