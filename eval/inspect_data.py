import json
import os

# 1. Check split_merged.json structure
print("=== split_merged.json ===")
with open("CRUD_RAG-main/data/crud_split/split_merged.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"top-level type: {type(data)}")
if isinstance(data, list):
    print(f"top-level length: {len(data)}")
    for i, item in enumerate(data):
        if isinstance(item, dict):
            print(f"  item[{i}] keys: {list(item.keys())}")
        elif isinstance(item, list):
            print(f"  item[{i}] is list, len={len(item)}")
            if len(item) > 0 and isinstance(item[0], dict):
                print(f"    first element keys: {list(item[0].keys())}")
        else:
            print(f"  item[{i}] type: {type(item)}")
elif isinstance(data, dict):
    print(f"top-level keys: {list(data.keys())}")
    for k in list(data.keys())[:5]:
        v = data[k]
        print(f"  {k}: type={type(v)}, len={len(v) if isinstance(v, (list, str)) else 'N/A'}")

# 2. Check each QA file
print("\n=== QA Files ===")
qa_dir = "CRUD_RAG-main/data/crud/CRUD_Data"
for fname in ["1doc_QA.json", "2docs_QA.json", "3docs_QA.json"]:
    fpath = os.path.join(qa_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        qa_data = json.load(f)
    print(f"\n{fname}: {len(qa_data)} entries")
    if qa_data:
        sample = qa_data[0]
        print(f"  keys: {list(sample.keys())}")

# 3. Count unique news docs across all QA files
print("\n=== Unique News Documents ===")
news_set = set()
total_news = 0
for fname in ["1doc_QA.json", "2docs_QA.json", "3docs_QA.json"]:
    fpath = os.path.join(qa_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        qa_data = json.load(f)
    for item in qa_data:
        for key in ["news1", "news2", "news3"]:
            if key in item and item[key]:
                # Use first 100 chars as unique identifier
                news_set.add(item[key][:100])
                total_news += 1

print(f"Total news references across all QA: {total_news}")
print(f"Unique news docs (by first 100 chars): {len(news_set)}")

# 4. Count total lines in 80k docs
print("\n=== 80k Corpus Size ===")
docs_dir = "CRUD_RAG-main/data/80000_docs"
total_lines = 0
for fname in os.listdir(docs_dir):
    fpath = os.path.join(docs_dir, fname)
    with open(fpath, "r", encoding="utf-8") as f:
        count = sum(1 for _ in f)
    total_lines += count
print(f"Total documents in corpus: {total_lines}")

# 5. Estimate embedding cost
print("\n=== Cost Estimation ===")
# Assume chunk_size=200 chars, avg doc=500 chars => ~2.5 chunks per doc
avg_chunks_per_doc = 2.5
full_corpus_chunks = int(total_lines * avg_chunks_per_doc)
unique_qa_chunks = int(len(news_set) * avg_chunks_per_doc)
print(f"Full 80k corpus chunks: ~{full_corpus_chunks:,}")
print(f"QA-referenced docs chunks: ~{unique_qa_chunks:,}")
print(f"Full corpus embedding calls: ~{full_corpus_chunks:,}")
print(f"QA-only embedding calls: ~{unique_qa_chunks:,}")
print(f"Cost reduction if QA-only: {(1 - unique_qa_chunks/full_corpus_chunks)*100:.1f}%")
