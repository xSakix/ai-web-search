from ai_web_search.engine.tokenizer import tokenize, tokenize_with_positions


def test_lowercases_input():
    assert "python" in tokenize("Python")


def test_strips_punctuation():
    assert "hello" in tokenize("hello, world!")
    assert "world" in tokenize("hello, world!")


def test_removes_stopwords():
    tokens = tokenize("the quick brown fox")
    assert "the" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens


def test_filters_single_chars():
    tokens = tokenize("a b c hello")
    assert "a" not in tokens
    assert "hello" in tokens


def test_empty_string():
    assert tokenize("") == []


def test_only_stopwords():
    assert tokenize("the and or but") == []


def test_positions_frequency():
    result = tokenize_with_positions("python python java")
    assert result["python"] == (2, [0, 1])
    assert result["java"] == (1, [2])


def test_positions_excludes_stopwords():
    result = tokenize_with_positions("the quick brown fox")
    assert "the" not in result
    assert "quick" in result


def test_hyphenated_terms():
    tokens = tokenize("state-of-the-art machine learning")
    assert "state" in tokens
    assert "art" in tokens
    assert "machin" in tokens  # Porter stem of "machine"
