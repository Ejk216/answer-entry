"""Pure-logic tests: answer-file schema. No browser needed."""
import json

import pytest

from answer_entry.model import load_answers


def write(tmp_path, obj):
    p = tmp_path / "answers.json"
    p.write_text(json.dumps(obj))
    return p


def valid():
    return {
        "set_url": "https://webwork2.example.edu/Course/Set/",
        "problems": [
            {"n": 1, "answers": [
                {"value": "-\\frac{1}{2},3"},
                {"value": "42", "type": "select"},
                {"value": ["A", "C"], "type": "checkbox"},
            ]},
            {"n": 2, "url": "https://webwork2.example.edu/Course/Set/2/",
             "answers": [{"value": "red", "type": "radio"}]},
        ],
    }


def test_valid_file(tmp_path):
    af = load_answers(write(tmp_path, valid()))
    assert [p.n for p in af.problems] == [1, 2]
    assert af.problem_url(af.problems[0]) == "https://webwork2.example.edu/Course/Set/1/"
    assert af.problem_url(af.problems[1]).endswith("/Set/2/")
    assert af.problems[0].answers[2].value == ["A", "C"]


def test_problems_must_be_nonempty_list(tmp_path):
    with pytest.raises(ValueError, match="non-empty list"):
        load_answers(write(tmp_path, {"problems": []}))


def test_duplicate_n_rejected(tmp_path):
    obj = valid()
    obj["problems"].append({"n": 1, "answers": [{"value": "x"}]})
    with pytest.raises(ValueError, match="duplicate problem n=1"):
        load_answers(write(tmp_path, obj))


def test_unknown_type_rejected(tmp_path):
    obj = valid()
    obj["problems"][0]["answers"][0]["type"] = "slider"
    with pytest.raises(ValueError, match="unknown type"):
        load_answers(write(tmp_path, obj))


def test_checkbox_requires_list(tmp_path):
    obj = valid()
    obj["problems"][0]["answers"][2]["value"] = "A"
    with pytest.raises(ValueError, match="checkbox value must be a list"):
        load_answers(write(tmp_path, obj))


def test_non_checkbox_requires_string(tmp_path):
    obj = valid()
    obj["problems"][0]["answers"][0]["value"] = ["x"]
    with pytest.raises(ValueError, match="value must be a string"):
        load_answers(write(tmp_path, obj))


def test_missing_url_and_set_url(tmp_path):
    obj = {"problems": [{"n": 1, "answers": [{"value": "x"}]}]}
    af = load_answers(write(tmp_path, obj))
    with pytest.raises(ValueError, match="no url and no set_url"):
        af.problem_url(af.problems[0])
