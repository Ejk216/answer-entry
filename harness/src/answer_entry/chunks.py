"""Split/merge helpers for parallel solving.

Workflow: `split` divides a fetched problems.json into chunks, each chunk is
solved independently (agents work well here), and `merge` recombines the
chunk answer files into one validated answers.json.
"""
from __future__ import annotations

from typing import Any


def split_problems(problems: list[dict[str, Any]], n_chunks: int) -> list[list[dict[str, Any]]]:
    """Divide problems into contiguous chunks (stable, readable ranges)."""
    if n_chunks < 1:
        raise ValueError("n_chunks must be positive")
    if not problems:
        raise ValueError("nothing to split")
    k, m = divmod(len(problems), n_chunks)
    out: list[list[dict[str, Any]]] = []
    start = 0
    for i in range(n_chunks):
        end = start + k + (1 if i < m else 0)
        if start < end:
            out.append(problems[start:end])
        start = end
    return out


def merge_answer_dicts(dicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine chunk answer files; caller validates with model.parse_answers_dict."""
    problems: list[dict[str, Any]] = []
    for d in dicts:
        if not isinstance(d, dict) or not isinstance(d.get("problems"), list):
            raise ValueError("chunk answer file must be {'problems': [...]}")
        problems.extend(d["problems"])
    problems.sort(key=lambda p: p["n"])
    return {"problems": problems}


def chunk_name(index: int) -> str:
    return f"chunk-{index + 1}.json"


def answers_name(index: int) -> str:
    return f"chunk-{index + 1}.answers.json"
