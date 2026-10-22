"""Solver: parsing, shape checks, caps, costs. Fake transport, no network."""
import json

import pytest

from answer_entry import solver
from answer_entry.solver import Policy, Provider, solve_problems

PROBLEMS = [
    {"n": 1, "text": "2+2?", "blanks": [{"kind": "text", "name": "a"}]},
    {"n": 2, "text": "pick", "blanks": [{"kind": "radio", "name": "b",
                                          "options": [{"label": "x"},
                                                      {"label": "y"}]}]},
]

BODY = {"problems": [
    {"n": 1, "confidence": "high", "work": "4", "answers": [{"value": "4"}]},
    {"n": 2, "confidence": "medium", "work": "x", "answers": [{"value": "x"}]},
]}


def provider(payload=BODY, usage=None, status=200, seen=None):
    usage = {"input_tokens": 1000, "output_tokens": 500} if usage is None else usage

    def transport(url, headers, body):
        assert url.endswith("/v1/messages")
        assert headers["x-api-key"] == "k" and body["model"]
        if seen is not None:
            seen.append(body)
        return status, {"content": [{"type": "text",
                                     "text": "```json\n" + json.dumps(payload)
                                     + "\n```"}],
                        "usage": usage}

    return Provider(api_key="k", transport=transport)


def test_happy_path():
    seen = []
    r = solve_problems(provider(seen=seen), PROBLEMS)
    assert [p["n"] for p in r.problems] == [1, 2]
    assert r.problems[1]["answers"] == [{"value": "x"}]
    assert r.held == [] and r.cost_usd == pytest.approx(0.0105)
    prompt = json.dumps(seen[0])
    assert "2+2?" in prompt and "blanks" in prompt


def test_low_confidence_held():
    low = {"problems": [dict(BODY["problems"][0], confidence="low"),
                         BODY["problems"][1]]}
    r = solve_problems(provider(low), PROBLEMS)
    assert r.held == [1]
    strict = solve_problems(provider(), PROBLEMS,
                            Policy(min_confidence="high"))
    assert strict.held == [2]


def test_shape_errors():
    short = {"problems": BODY["problems"][:1]}
    with pytest.raises(ValueError, match="skipped problems"):
        solve_problems(provider(short), PROBLEMS)
    wrong = {"problems": [dict(BODY["problems"][0]),
                           dict(BODY["problems"][1],
                                answers=[{"value": "x"}, {"value": "y"}])]}
    with pytest.raises(ValueError, match="2 answers for problem 2"):
        solve_problems(provider(wrong), PROBLEMS)
    with pytest.raises(ValueError, match="unparsable"):
        solve_problems(provider("not json {{{", usage={}), PROBLEMS)


def test_empty_output_retried_with_summed_usage():
    calls = []

    def transport(url, headers, body):
        calls.append(1)
        if len(calls) == 1:
            text, usage = "", {"input_tokens": 100, "output_tokens": 50}
        else:
            text, usage = json.dumps(BODY), {"input_tokens": 100,
                                             "output_tokens": 60}
        return 200, {"content": [{"type": "text", "text": text}],
                     "usage": usage}

    r = solve_problems(Provider(api_key="k", transport=transport),
                       PROBLEMS)
    assert [p["n"] for p in r.problems] == [1, 2]
    assert (r.input_tokens, r.output_tokens) == (200, 110)
    assert len(calls) == 2


def test_cap_refuses_before_spending():
    called = []
    p = provider(seen=called)
    with pytest.raises(ValueError, match="over the \\$0.00 cap"):
        solve_problems(p, PROBLEMS, Policy(max_usd=0.0))
    assert called == []  # refused before any API call


def test_401_is_key_error():
    p = provider(status=401)
    with pytest.raises(ValueError, match="key rejected"):
        solve_problems(p, PROBLEMS)


def test_meta_provider_uses_bearer_and_meta_url():
    seen = []

    def transport(url, headers, body):
        seen.append((url, headers, body))
        return 200, {"content": [{"type": "text",
                                  "text": json.dumps(BODY)}],
                     "usage": {"input_tokens": 10, "output_tokens": 5}}

    p = solver.meta_provider("mk", transport=transport)
    assert p.model == "muse-spark-1.3-contributor"
    r = solve_problems(p, PROBLEMS)
    url, headers, body = seen[0]
    assert url == "https://api.meta.ai/v1/messages"
    assert headers["Authorization"] == "Bearer mk"
    assert "x-api-key" not in headers
    assert body["model"] == "muse-spark-1.3-contributor"
    assert r.cost_usd == pytest.approx(10 / 1e6 * 0.10 + 5 / 1e6 * 0.20)


def test_figures_attach_as_image_blocks(tmp_path):
    png = (tmp_path / "f.png")
    png.write_bytes(b"\x89PNG\r\n\x1a" + b"\0" * 16)
    (tmp_path / "note.txt").write_text("not an image")
    seen = []
    probs = [dict(PROBLEMS[0], figures=["f.png", "note.txt", "missing.png"]),
             PROBLEMS[1]]
    one = {"problems": [BODY["problems"][0],
                         dict(BODY["problems"][1])]}

    def transport(url, headers, body):
        seen.append(body)
        return 200, {"content": [{"type": "text", "text": json.dumps(one)}],
                     "usage": {"input_tokens": 10, "output_tokens": 5}}

    p = Provider(api_key="k", transport=transport)
    solve_problems(p, probs, base_dir=tmp_path)
    content = seen[0]["messages"][0]["content"]
    kinds = [c["type"] for c in content]
    assert kinds == ["image", "text", "text"]
    assert content[0]["source"]["media_type"] == "image/png"


def test_currents_never_reach_the_model():
    seen = []
    dirty = [{"n": 1, "text": "2+2?",
              "blanks": [{"kind": "text", "name": "a", "current": "4"}]}]
    one = {"problems": [BODY["problems"][0]]}
    solve_problems(provider(one, seen=seen), dirty)
    sent = json.dumps(seen[0])
    assert '"current"' not in sent
    assert solver.sanitize(dirty) == [
        {"n": 1, "text": "2+2?",
         "blanks": [{"kind": "text", "name": "a"}]}]
