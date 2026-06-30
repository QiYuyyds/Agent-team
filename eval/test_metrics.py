#!/usr/bin/env python
"""Unit tests for eval/metrics.py — is_hit, recall_at_k, mrr, ndcg_at_k.

Run from the eval/ directory:
    cd eval && python -m pytest test_metrics.py -v
or:
    cd eval && python test_metrics.py
"""

import math
import os
import sys

# Ensure eval/ is on the path so we can import metrics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from metrics import is_hit, recall_at_k, precision_at_k, mrr, ndcg_at_k


# ═══════════════════════════════════════════════════════════════════════════
#  Test fixtures
# ═══════════════════════════════════════════════════════════════════════════

DOC_A = (
    '2023年7月20日，应急管理部、财政部联合下发《因灾倒塌、损坏住房恢复重建救助工作规范》'
    '的通知，进一步规范因灾倒塌、损坏住房恢复重建救助相关工作。'
)
DOC_B = (
    '2023年7月28日，国家卫生健康委在全国范围内开展“启明行动”——防控儿童青少年近视健康促进活动，'
    '发布《防控儿童青少年近视核心知识十条》。'
)
DOC_C = (
    '2023年8月15日，教育部发布通知，要求各地中小学加强体育锻炼，确保学生每天运动一小时以上。'
)

RELEVANT_DOCS = [DOC_A, DOC_B]


# ─── is_hit tests ───────────────────────────────────────────────────────────

def test_is_hit_chunk_from_relevant_doc():
    """Chunk content that is a substring of a relevant document → True."""
    chunk = DOC_A[:80]  # First 80 chars of DOC_A
    assert is_hit(chunk, RELEVANT_DOCS) is True


def test_is_hit_irrelevant_chunk():
    """Chunk content from an irrelevant document → False."""
    chunk = DOC_C[:80]
    assert is_hit(chunk, RELEVANT_DOCS) is False


def test_is_hit_empty_chunk():
    """Empty or whitespace-only chunk content → False."""
    assert is_hit("", RELEVANT_DOCS) is False
    assert is_hit("   ", RELEVANT_DOCS) is False
    assert is_hit("\n\t", RELEVANT_DOCS) is False


def test_is_hit_reverse_matching():
    """Relevant doc prefix appears in chunk content (reverse direction) → True."""
    # A chunk that contains the beginning of DOC_B but doesn't start with it
    chunk = "some prefix text " + DOC_B[:50] + " more text"
    assert is_hit(chunk, RELEVANT_DOCS) is True


def test_is_hit_no_relevant_docs():
    """Empty relevant_docs list → False."""
    assert is_hit(DOC_A[:80], []) is False


# ─── recall_at_k tests ──────────────────────────────────────────────────────

def test_recall_perfect_retrieval():
    """All relevant docs found in top-K → recall = 1.0."""
    # Two chunks, each from a different relevant doc
    retrieved = [DOC_A[:80], DOC_B[:80]]
    assert recall_at_k(retrieved, RELEVANT_DOCS, k=5) == 1.0


def test_recall_no_hits():
    """No relevant chunks retrieved → recall = 0.0."""
    retrieved = [DOC_C[:80], DOC_C[80:160]]
    assert recall_at_k(retrieved, RELEVANT_DOCS, k=5) == 0.0


def test_recall_partial():
    """1 of 2 relevant docs found → recall = 0.5."""
    retrieved = [DOC_A[:80], DOC_C[:80]]  # Only DOC_A is found
    assert recall_at_k(retrieved, RELEVANT_DOCS, k=5) == 0.5


def test_recall_empty_retrieved():
    """Empty retrieved list → recall = 0.0."""
    assert recall_at_k([], RELEVANT_DOCS, k=5) == 0.0


def test_recall_empty_relevant():
    """Empty relevant_docs → recall = 0.0."""
    assert recall_at_k([DOC_A[:80]], [], k=5) == 0.0


def test_recall_k_limits_results():
    """K limits the number of retrieved chunks considered."""
    # DOC_A chunk at position 3, k=2 → not found
    retrieved = [DOC_C[:80], DOC_C[80:160], DOC_A[:80]]
    assert recall_at_k(retrieved, RELEVANT_DOCS, k=2) == 0.0
    # With k=3, DOC_A is found
    assert recall_at_k(retrieved, RELEVANT_DOCS, k=3) == 0.5


# ─── precision_at_k tests ───────────────────────────────────────────────────

def test_precision_perfect():
    """All top-K chunks are relevant → precision = 1.0."""
    retrieved = [DOC_A[:80], DOC_B[:80]]
    assert precision_at_k(retrieved, RELEVANT_DOCS, k=2) == 1.0


def test_precision_no_hits():
    """No relevant chunks in top-K → precision = 0.0."""
    retrieved = [DOC_C[:80], DOC_C[80:160]]
    assert precision_at_k(retrieved, RELEVANT_DOCS, k=2) == 0.0


def test_precision_partial():
    """1 of 2 top-K chunks is relevant → precision = 0.5."""
    retrieved = [DOC_A[:80], DOC_C[:80]]
    assert precision_at_k(retrieved, RELEVANT_DOCS, k=2) == 0.5


def test_precision_empty_retrieved():
    """Empty retrieved → precision = 0.0."""
    assert precision_at_k([], RELEVANT_DOCS, k=5) == 0.0


# ─── mrr tests ───────────────────────────────────────────────────────────────

def test_mrr_first_hit():
    """First retrieved chunk is relevant → MRR = 1.0."""
    retrieved = [DOC_A[:80], DOC_C[:80]]
    assert mrr(retrieved, RELEVANT_DOCS) == 1.0


def test_mrr_second_hit():
    """Second retrieved chunk is relevant → MRR = 0.5."""
    retrieved = [DOC_C[:80], DOC_B[:80]]
    assert mrr(retrieved, RELEVANT_DOCS) == 0.5


def test_mrr_no_hits():
    """No relevant chunks → MRR = 0.0."""
    retrieved = [DOC_C[:80], DOC_C[80:160]]
    assert mrr(retrieved, RELEVANT_DOCS) == 0.0


def test_mrr_empty_retrieved():
    """Empty retrieved → MRR = 0.0."""
    assert mrr([], RELEVANT_DOCS) == 0.0


def test_mrr_third_hit():
    """Third retrieved chunk is relevant → MRR = 1/3."""
    retrieved = [DOC_C[:80], DOC_C[80:160], DOC_A[:80]]
    assert abs(mrr(retrieved, RELEVANT_DOCS) - 1.0 / 3.0) < 1e-6


# ─── ndcg_at_k tests ─────────────────────────────────────────────────────────

def test_ndcg_perfect_retrieval():
    """All relevant docs in top positions → NDCG = 1.0."""
    retrieved = [DOC_A[:80], DOC_B[:80]]
    assert ndcg_at_k(retrieved, RELEVANT_DOCS, k=5) == 1.0


def test_ndcg_no_hits():
    """No relevant chunks → NDCG = 0.0."""
    retrieved = [DOC_C[:80], DOC_C[80:160]]
    assert ndcg_at_k(retrieved, RELEVANT_DOCS, k=5) == 0.0


def test_ndcg_partial_with_ranking():
    """Hit at position 2 with 2 relevant docs → NDCG reflects discounted position."""
    retrieved = [DOC_C[:80], DOC_A[:80]]  # Hit at rank 2
    # DCG = 0/log2(2) + 1/log2(3) = 0 + 1/1.585 = 0.6309
    # IDCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.6309 = 1.6309
    # NDCG = 0.6309 / 1.6309 = 0.3869
    expected = (1.0 / math.log2(3)) / (1.0 / math.log2(2) + 1.0 / math.log2(3))
    result = ndcg_at_k(retrieved, RELEVANT_DOCS, k=5)
    assert abs(result - expected) < 1e-4


def test_ndcg_empty_retrieved():
    """Empty retrieved → NDCG = 0.0."""
    assert ndcg_at_k([], RELEVANT_DOCS, k=5) == 0.0


def test_ndcg_empty_relevant():
    """Empty relevant_docs → NDCG = 0.0."""
    assert ndcg_at_k([DOC_A[:80]], [], k=5) == 0.0


def test_ndcg_k_limits():
    """K limits the number of retrieved chunks considered."""
    # Hit at position 3, k=2 → not counted
    retrieved = [DOC_C[:80], DOC_C[80:160], DOC_A[:80]]
    assert ndcg_at_k(retrieved, RELEVANT_DOCS, k=2) == 0.0
    # With k=3, the hit is counted
    assert ndcg_at_k(retrieved, RELEVANT_DOCS, k=3) > 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  Test runner (allows running without pytest)
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Collect all test functions
    test_functions = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]

    passed = 0
    failed = 0
    for name, fn in test_functions:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {len(test_functions)} total")
    if failed > 0:
        sys.exit(1)
