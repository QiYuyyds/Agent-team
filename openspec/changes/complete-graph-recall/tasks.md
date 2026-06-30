## 1. 公共图扩展方法（D3）

- [x] 1.1 在 `backend/app/memory/long_term.py` 中添加 `_graph_expand(seed_items, top_k)` 私有方法：对种子 items 的每个 id 调用 `self.graph_memory.find_related(id)`，收集扩展 mem_id 集合，从 `self.items` 中查找匹配项，构造 score=0.45 的 Item 副本，排除已在种子中的 id，合并种子+扩展后按 score 降序排序并截断 top_k
- [x] 1.2 图扩展逻辑包裹在 try/except 中，失败时 logger.warning 并仅返回种子 items

## 2. recall() 集成图扩展

- [x] 2.1 修改 `LongTerm.recall()` 方法：在现有语义搜索得到 seed items 之后、return 之前，调用 `self._graph_expand(seed_items, top_k)` 替代当前的直接返回
- [x] 2.2 当 `self.graph_memory is None` 或种子为空时，跳过图扩展，保持原有行为

## 3. recall_by_filter() 集成图扩展

- [x] 3.1 修改 `LongTerm.recall_by_filter()` 方法：在现有 filtered 语义搜索得到 candidates 之后、return 之前，调用 `self._graph_expand(candidates, top_k)` 替代当前的直接返回
- [x] 3.2 图扩展条目同样受 category 过滤约束：扩展条目的 category 不在 filter 要求范围内时排除

## 4. 测试验证

- [x] 4.1 运行现有测试 `pytest backend/tests/` 确认无回归（尤其 test_memory_graph.py 和 test_memory_long_term.py）
- [x] 4.2 验证：构造含 FOLLOWS 边的图结构，调用 recall() 确认返回结果包含图扩展条目且 score=0.45
- [x] 4.3 验证：graph_memory 为 None 时 recall() 行为不变（无扩展、无报错）
- [x] 4.4 验证：find_related() 抛异常时 recall() 仅返回种子条目
