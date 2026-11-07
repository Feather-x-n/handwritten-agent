import math
import sys

from rich import print as rprint

from .loader import load_chunks

 
K1 = 1.2
B = 0.75
UNIGRAM_WEIGHT = 0.5
 
 
def grams(text: str, n: int) -> set[str]:
    """把文本切成 n 字一组，去空白。n=2 是 bigram，n=1 是单字。"""
    text = "".join(ch for ch in text.lower() if not ch.isspace())
    return {text[i:i + n] for i in range(len(text) - n + 1)}
 
 
def score_basic(query: str, text: str) -> float:
    """旧算法：query 的 bigram 有多大比例出现在段落里。"""
    q = grams(query, 2)
    if not q:
        return 0.0
    return len(q & grams(text, 2)) / len(q)
 
 
def build_stats(chunks: list[dict]) -> dict:
    """统计每个单字/bigram 出现在多少段，以及平均段长。"""
    df1, df2 = {}, {}
    for chunk in chunks:
        for t in grams(chunk["text"], 1):
            df1[t] = df1.get(t, 0) + 1
        for t in grams(chunk["text"], 2):
            df2[t] = df2.get(t, 0) + 1
    avgdl = sum(len(c["text"]) for c in chunks) / len(chunks)
    return {"df1": df1, "df2": df2, "n": len(chunks), "avgdl": avgdl}
 
 
def _idf(df: dict, n: int, term: str) -> float:
    d = df.get(term, 0)
    return math.log((n - d + 0.5) / (d + 0.5) + 1)
 
 
def score_bm25(query: str, text: str, stats: dict, n_gram: int) -> float:
    """BM25 打分，n_gram=2 用 bigram，=1 用单字。"""
    df = stats["df1"] if n_gram == 1 else stats["df2"]
    q = grams(query, n_gram)
    if not q:
        return 0.0
    dl = len(text)
    num = 0.0
    for t in q:
        tf = text.count(t)
        if tf == 0:
            continue
        num += _idf(df, stats["n"], t) * tf * (K1 + 1) / (
            tf + K1 * (1 - B + B * dl / stats["avgdl"])
        )
    den = sum(_idf(df, stats["n"], t) for t in q)
    return num / den if den else 0.0
 
 
def score_hybrid(query: str, text: str, stats: dict) -> float:
    return (
        (1 - UNIGRAM_WEIGHT) * score_bm25(query, text, stats, 2)
        + UNIGRAM_WEIGHT * score_bm25(query, text, stats, 1)
    )
 
 
def search(query: str, top_k: int = 3, method: str = "hybrid") -> list[dict]:
    chunks = load_chunks("docs")
    if not chunks:
        return []
    stats = build_stats(chunks)
 
    if method == "basic":
        scorer = score_basic
    elif method == "bm25":
        scorer = lambda q, t: score_bm25(q, t, stats, 2)
    else:
        scorer = lambda q, t: score_hybrid(q, t, stats)
 
    scored = []
    for chunk in chunks:
        s = scorer(query, chunk["text"])
        if s > 0:
            scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
 
    return [
        {"score": s, "text": c["text"], "source": c["source"], "index": c["index"]}
        for s, c in scored[:top_k]
    ]
# #旧算法
# def bigrams(text: str) -> set[str]:
#     text = "".join(ch for ch in text.lower() if not ch.isspace())
#     return {text[i:i+2] for i in range(len(text) - 1)}
# def score(query:str,text:str)->float:
#     """query 的 bigram 有多大比例出现在 text 里，0~1。"""
#     query_set = bigrams(query)
#     if not query_set:
#         return 0.0
#     text_set = bigrams(text)
#     return len(query_set & text_set) / len(query_set)
# def search(query:str,top_k:int=3)->list[dict]:
#     """返回 top_k 个最相关的段落"""
#     chunks = load_chunks("docs")
#     scored_chunks = []
#     for chunk in chunks:
#         s = score(query, chunk["text"])
#         if s > 0:
#             scored_chunks.append((s, chunk))
#     scored_chunks.sort(key=lambda x: x[0], reverse=True)
#     return [
#         {
#             "score":score,
#             "text":chunk["text"],
#             "source": chunk["source"],
#             "index": chunk["index"],
#         }
#         for score, chunk in scored_chunks[:top_k]
#         ]
if __name__ == "__main__":
    rprint(search(sys.argv[1]))