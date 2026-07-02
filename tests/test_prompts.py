from layerlens.prompts import EXPLAIN_PROMPT


def test_explain_prompt_formats_without_error():
    # This is the exact call server.explain() makes; a stray literal `{`/`}` in the
    # prompt template would raise KeyError/IndexError here.
    result = EXPLAIN_PROMPT.format(topic="Test Topic")
    assert "Test Topic" in result


def test_explain_prompt_mentions_list_library_and_related():
    result = EXPLAIN_PROMPT.format(topic="x")
    assert "list_library" in result
    assert '"related"' in result
    assert "[[slug]]" in result or "[[slug|" in result
