"""Page-aware chunks, bilingual lexical retrieval and optional exact-vector RRF."""
import math
import re
from collections import Counter
from .query_terms import expand_query
from .papers import LIGATURES


def tokenize(text):
    text = text.translate(LIGATURES).lower()
    tokens = re.findall(r"[a-z0-9_]+", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            tokens.append(run)
    return tokens


def split_text(text, size=900, overlap=120):
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must exceed overlap")
    text = text.replace("\x00", "").replace("\r\n", "\n")
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = max(text.rfind("\n", start + size // 2, end), text.rfind("。", start + size // 2, end))
            if boundary > start:
                end = boundary + 1
        segment = text[start:end]
        fragment = segment.strip()
        if fragment:
            leading = len(segment) - len(segment.lstrip())
            trailing = len(segment) - len(segment.rstrip())
            line = text.count("\n", 0, start + leading) + 1
            last_line = text.count("\n", 0, end - trailing) + 1
            yield fragment, line, last_line
        if end == len(text):
            break
        start = end - overlap


def bm25(query, documents):
    query_tokens = set(tokenize(query))
    counts = [Counter(tokenize(d)) for d in documents]
    if not counts:
        return []
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths) or 1
    frequency = Counter(t for c in counts for t in c)
    scores = []
    for c, length in zip(counts, lengths):
        value = 0.0
        for token in query_tokens:
            freq = c.get(token, 0)
            if not freq:
                continue
            inverse = math.log(1 + (len(counts) - frequency[token] + 0.5) / (frequency[token] + 0.5))
            value += inverse * freq * 2.5 / (freq + 1.5 * (0.25 + 0.75 * length / average))
        scores.append(value)
    return scores


def cosine(a, b):
    if len(a) != len(b) or not a:
        return 0.0
    divisor = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / divisor if divisor else 0.0


def rank(query, chunks, k=5, query_vector=None):
    documents = [c["name"] + " " + c["locator"] + " " + c.get("structure", {}).get("section", "") + " " + c["text"] for c in chunks]
    scores = bm25(query, documents)
    expansion = expand_query(query)
    tokens = [set(tokenize(d)) for d in documents]
    # Require every term of a phrase; matching only "model" is not evidence for
    # "degradation model". Use the strongest alternative, not synonym counts.
    for concept in expansion:
        concept_scores = [0.0] * len(chunks)
        for phrase in concept["alternatives"]:
            phrase_tokens = set(tokenize(phrase))
            for i, score in enumerate(bm25(phrase, documents)):
                if phrase_tokens and phrase_tokens <= tokens[i]:
                    concept_scores[i] = max(concept_scores[i], score + 2)
        scores = [score + extra for score, extra in zip(scores, concept_scores)]
    # Diagram labels remain searchable, but prose is generally better evidence.
    scores = [score * ({"visual": 0.4, "caption": 0.75}.get(c.get("structure", {}).get("type"), 1))
              for score, c in zip(scores, chunks)]
    equation = re.search(r"公式\s*[（(]?\s*(\d{1,3})", query)
    if equation:
        # Equation numbers must appear as '(n)' in actual text, never just the
        # page locator, a table value, or a bibliography citation '[n]'.
        pattern = re.compile(r"[（(]\s*" + equation[1] + r"\s*[)）]")
        scores = [score + 20 if pattern.search(c["text"]) and c.get("structure", {}).get("math") else 0
                  for score, c in zip(scores, chunks)]
    lexical = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: scores[i], reverse=True)
    if query_vector is None:
        return [{**chunks[i], "score": round(scores[i], 4), "retrieval": "BM25 + 中英术语" if expansion else "BM25", "query_expansion": expansion} for i in lexical[:k]]
    vector_scores = {i: cosine(query_vector, c["vector"]) for i, c in enumerate(chunks) if c.get("vector")}
    semantic = sorted((i for i in vector_scores if vector_scores[i] > 0), key=lambda i: vector_scores[i], reverse=True)
    if equation:
        semantic = [i for i in semantic if scores[i] > 0]
    fused = Counter()
    for ordering in (lexical, semantic):
        for place, i in enumerate(ordering):
            fused[i] += 1 / (60 + place + 1)
    return [{**chunks[i], "score": round(score, 5), "retrieval": "BM25 + vector / RRF", "query_expansion": expansion}
            for i, score in fused.most_common(k)]
