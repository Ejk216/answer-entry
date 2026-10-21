"""Offline answers-vs-fetch validation. Pure logic, no network."""
from answer_entry.model import parse_answers_dict
from answer_entry.validate import validate_answers

PROBLEMS = [
    {"n": 1, "url": "http://x/set/1/", "text": "t1", "blanks": [
        {"kind": "text", "name": "AnSwEr0001", "current": ""},
        {"kind": "radio", "name": "c", "options": [
            {"label": "red", "value": "r"},
            {"label": "green", "value": "g"}]},
        {"kind": "checkbox", "name": "o", "options": [
            {"label": "A", "value": "A"},
            {"label": "B", "value": "B"}]},
    ], "images": []},
    {"n": 2, "url": "http://x/set/2/", "text": "t2", "blanks": [
        {"kind": "mathquill", "name": "AnSwEr0002", "current": ""},
        {"kind": "select", "name": "s", "options": [
            {"label": "42", "value": "1"},
            {"label": "43", "value": "2"}]},
    ], "images": []},
]


def check(answers_raw, problems=None):
    return validate_answers(problems if problems is not None else PROBLEMS,
                            parse_answers_dict(answers_raw))


def test_clean_file_validates():
    raw = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": "green"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    assert check(raw).ok


def test_count_mismatch_is_error():
    raw = {"problems": [{"n": 1, "answers": [{"value": "14"}]}]}
    v = check(raw)
    assert not v.ok
    assert "1 answers but 3 blanks" in v.errors[0]


def test_bad_option_label_lists_valid_labels():
    raw = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": "gren"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    v = check(raw)
    assert not v.ok
    assert "gren" in v.errors[0] and "green" in v.errors[0]


def test_option_value_also_accepted_and_index_range_checked():
    good = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": "index:1"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "1"}]},
    ]}
    assert check(good).ok
    bad = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": "index:9"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    assert "out of range" in check(bad).errors[0]


def test_checkbox_str_list_mixups():
    str_for_check = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": "green"},
                             {"value": "A"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    v = check(str_for_check)
    assert not v.ok and "list value" in v.errors[0]
    list_for_radio = {"problems": [
        {"n": 1, "answers": [{"value": "14"}, {"value": ["green"],
                             "type": "checkbox"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    v = check(list_for_radio)
    assert not v.ok and "checkbox blank, not 'radio'" in v.errors[0]


def test_text_mathquill_interchange_but_other_types_strict():
    raw = {"problems": [
        {"n": 1, "answers": [{"value": "14", "type": "mathquill"},
                             {"value": "green"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2", "type": "text"},
                             {"value": "42"}]},
    ]}
    assert check(raw).ok
    raw["problems"][0]["answers"][0] = {"value": "14", "type": "radio"}
    assert "declares type" in check(raw).errors[0]


def test_missing_dump_is_error_missing_answers_is_warning():
    raw = {"problems": [{"n": 9, "answers": [{"value": "14"}]}]}
    v = check(raw)
    assert not v.ok and "no fetch dump" in v.errors[0]
    raw = {"problems": [{"n": 1, "answers": [
        {"value": "14"}, {"value": "green"},
        {"value": ["A"], "type": "checkbox"}]}]}
    v = check(raw)
    assert v.ok  # --only flows omit problems legitimately
    assert "problem 2" in v.warnings[0] and "will not be entered" in v.warnings[0]


def test_empty_string_warns():
    raw = {"problems": [
        {"n": 1, "answers": [{"value": ""}, {"value": "green"},
                             {"value": ["A"], "type": "checkbox"}]},
        {"n": 2, "answers": [{"value": "x^2"}, {"value": "42"}]},
    ]}
    v = check(raw)
    assert v.ok and "unanswered" in v.warnings[0]
