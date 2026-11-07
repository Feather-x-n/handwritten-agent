import json
from .search import search
#自检召回
#加载测试样例
def load_cases(path: str = "eval/qa.jsonl") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
def rank_of(results: list[dict], source: str, index: int) -> int | None:
    """在结果里找期望段落的名次，从 1 开始；没找到返回 None。"""
    for i, r in enumerate(results, 1):
        if r["source"] == source and r["index"] == index:
            return i
def main():
    cases = load_cases()
    positives = [c for c in cases if "expect_none" not in c]
    negatives = [c for c in cases if c.get("expect_none")]
 
    hits3 = 0
    top1 = 0
    mrr = 0.0
    misses = []
 
    for case in positives:
        results = search(case["question"], top_k=3)
        rank = rank_of(results, case["source"], case["index"])
        if rank is None:
            misses.append((case, results))
            continue
        hits3 += 1
        mrr += 1 / rank
        if rank == 1:
            top1 += 1
 
    n = len(positives)
    print(f"recall@3 = {hits3}/{n} = {hits3 / n:.1%}")
    print(f"top1     = {top1}/{n} = {top1 / n:.1%}")
    print(f"MRR      = {mrr / n:.3f}")
 
    if misses:
        print("\n漏检：")
        for case, results in misses:
            print(f"- {case['question']}  期望 {case['source']} #{case['index']}")
            for r in results:
                print(f"    {r['source']} #{r['index']}  {r['score']:.2f}")
            if not results:
                print("    （无结果）")
 
    print("\n无答案题：")
    for case in negatives:
        results = search(case["question"], top_k=1)
        if results:
            r = results[0]
            print(f"- {case['question']}  top1={r['source']} #{r['index']}  score={r['score']:.2f}")
        else:
            print(f"- {case['question']}  （无结果）")
 
 
if __name__ == "__main__":
    main()