"""Split/merge and CLI parsing tests. No network."""
import json

import pytest

from answer_entry import chunks
from answer_entry.cli import build_parser
from answer_entry.model import parse_answers_dict


def probs(ns):
    return [{"n": n, "url": f"http://x/{n}/", "text": "t", "blanks": []}
            for n in ns]


def test_split_contiguous():
    parts = chunks.split_problems(probs(range(1, 10)), 3)
    assert [[p["n"] for p in part] for part in parts] == [
        [1, 2, 3], [4, 5, 6], [7, 8, 9]]


def test_split_uneven_front_loads():
    parts = chunks.split_problems(probs(range(1, 9)), 3)
    assert [[p["n"] for p in part] for part in parts] == [
        [1, 2, 3], [4, 5, 6], [7, 8]]


def test_split_more_chunks_than_problems():
    parts = chunks.split_problems(probs([1, 2]), 5)
    assert [[p["n"] for p in part] for part in parts] == [[1], [2]]


def test_split_rejects_empty_and_zero():
    with pytest.raises(ValueError, match="nothing to split"):
        chunks.split_problems([], 3)
    with pytest.raises(ValueError, match="positive"):
        chunks.split_problems(probs([1]), 0)


def chunk(ns):
    return {"problems": [{"n": n, "url": f"http://x/{n}/",
                          "answers": [{"value": "v"}]} for n in ns]}


def test_merge_combines_and_sorts():
    merged = chunks.merge_answer_dicts([chunk([3, 4]), chunk([1, 2])])
    assert [p["n"] for p in merged["problems"]] == [1, 2, 3, 4]
    answers = parse_answers_dict(merged)  # validates shape
    assert [p.n for p in answers.problems] == [1, 2, 3, 4]


def test_merge_rejects_duplicates():
    with pytest.raises(ValueError, match="duplicate problem n=2"):
        parse_answers_dict(chunks.merge_answer_dicts([chunk([1, 2]), chunk([2, 3])]))


def test_merge_rejects_bad_shape():
    with pytest.raises(ValueError, match="must be"):
        chunks.merge_answer_dicts([{"nope": []}])


def test_cli_parsing(tmp_path):
    p = build_parser()
    a = p.parse_args(["http-fetch", "http://x/set/", "--workers", "5"])
    assert a.workers == 5 and a.func.__name__ == "cmd_http_fetch"
    a = p.parse_args(["http-fetch", "f.json"])
    assert a.workers == 2
    a = p.parse_args(["split", "p.json", "--out", "d", "--chunks", "4"])
    assert (a.problems, a.out, a.chunks) == ("p.json", "d", 4)
    a = p.parse_args(["merge", "a.json", "b.json", "-o", "out.json"])
    assert (a.files, a.o) == (["a.json", "b.json"], "out.json")
    with pytest.raises(SystemExit):
        p.parse_args(["merge", "a.json"])  # -o required
