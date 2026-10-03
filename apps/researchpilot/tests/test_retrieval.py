from researchpilot.retrieval import split_text, tokenize, rank, cosine


def test_chunk_coverage_and_overlap():
    text = "\n".join("paragraph " + str(i) + " content " * 15 for i in range(50))
    chunks = list(split_text(text, 300, 40))
    assert len(chunks) > 1
    assert all(len(fragment) <= 300 and end >= start >= 1 for fragment, start, end in chunks)
    assert chunks[0][0].startswith("paragraph 0")
    assert "paragraph 49" in chunks[-1][0]
    assert chunks[0][0][-40:].strip() in chunks[1][0]


def test_bilingual_tokens_and_unrelated_query():
    assert "训练" in tokenize("训练目标")
    assert "pytorch" in tokenize("PyTorch CUDA")
    chunks = [{"id":"1","name":"paper","locator":"p1","text":"训练目标是 MSE loss"},
              {"id":"2","name":"env","locator":"p2","text":"Python CUDA"}]
    assert rank("训练目标", chunks)[0]["id"] == "1"
    assert rank("astronomy", chunks) == []


def test_line_numbers_preserve_leading_blank_lines():
    fragments = list(split_text("\n\n  import torch\nprint('hello')\n\n"))
    assert fragments[0][1:] == (3, 4)


def test_vector_can_retrieve_without_lexical_overlap():
    chunks = [{"id":"1","name":"a","locator":"p1","text":"denoising", "vector":[1,0]},
              {"id":"2","name":"b","locator":"p2","text":"classification", "vector":[0,1]}]
    assert rank("图像去噪", chunks, query_vector=[1,0])[0]["id"] == "1"
    assert cosine([0,0],[1,2]) == 0
    assert cosine([1],[1,2]) == 0
