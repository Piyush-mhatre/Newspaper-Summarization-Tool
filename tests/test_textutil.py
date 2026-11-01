import pytest

from pipeline.textutil import join_lines


@pytest.mark.parametrize("lines, expected", [
    (["Hello", "world"], "Hello world"),
    (["govern-", "ment said"], "government said"),                 # hyphenation repaired
    (["twenty-", "One people"], "twenty- One people"),             # capital next: keep hyphen
    (["a", "", "  b  "], "a b"),                                   # blanks and padding ignored
    (["perma-", "I nent provision"], "permanent provision"),        # column rule read as I
    pytest.param(["Well-", "I know"], "Well- I know", marks=pytest.mark.xfail(
        reason="KNOWN LIMIT: 'I nent' (rule + fragment) and 'I know' (real words) look the same "
               "without a dictionary. We accept this trade-off: it only happens after a line-end hyphen.")),
    ([], ""),
    (["   "], ""),
])
def test_join_lines(lines, expected):
    assert join_lines(lines) == expected
