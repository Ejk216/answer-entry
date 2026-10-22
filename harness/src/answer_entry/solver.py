"""API solver: problems.json in, proposed answers.json out. Never submits.

The solver only *proposes*: its output flows through the same
validate -> canary -> graded-verify gauntlet as human answers, and
`run answers` stays the only path to entry. Low-confidence problems
are held for a human instead of being guessed.

Provider: Anthropic Messages API over stdlib urllib (no new deps).
Key from the macOS Keychain (`anthropic-api-key`), never files/logs.
Cost is computed from returned usage against a price table and
refused up front when the worst case exceeds the cap.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

KEYCHAIN_SERVICE = "anthropic-api-key"
META_KEYCHAIN_SERVICE = "meta-model-api-key"
API_URL = "https://api.anthropic.com/v1/messages"
META_API_URL = "https://api.meta.ai/v1/messages"
API_VERSION = "2023-06-01"

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
META_DEFAULT_MODEL = "muse-spark-1.3-contributor"

# USD per million tokens (input, output). Contributor pricing trades
# 12-30x lower cost for Meta training on prompts and completions.
PRICES = {
    "claude-sonnet-4-5-20250929": (3.0, 15.0),
    "claude-opus-4-1-20250805": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "muse-spark-1.3": (1.25, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.20),
}
DEFAULT_PRICE = (3.0, 15.0)

CONFIDENCE = {"low": 1, "medium": 2, "high": 3}

SYSTEM = """You solve online math/statistics homework. For each problem:
show brief work, then commit to final answers.

Input problems carry blanks in page order with widget kinds and, for
choice widgets, the exact option labels. Attached figures belong to
the problem they follow — read values off graphs carefully. Rules:
- text-kind blanks: WeBWorK PG syntax in plain ASCII ONLY —
  sqrt(53), sin(x^6)/6, 6*x-6, 1/2. NEVER LaTeX backslash commands
  in a text blank. (Only mathquill-kind blanks take LaTeX.)
- Exact forms unless told otherwise; decimals to the stated
  precision; DNE for does-not-exist; intervals like [0,1] U (2,3);
  comma-separated lists where asked. Antiderivatives: no +C.
- Choice blanks: reply with the option LABEL exactly as printed, never
  an index. Checkbox blanks take a list of labels.
- One answer per blank, in order. Every problem gets a confidence:
  high (routine computation, double-checked), medium (interpretation
  or convention involved — name it), low (genuinely unsure: unreadable
  figure, interactive widget, missing data).
- Output ONLY this JSON (no prose, fences optional):
{"problems": [{"n": 1, "confidence": "high", "work": "...",
"answers": [{"value": "..."}]}]}
Checkbox answers add "type": "checkbox" with a list value.
"""

FIGURE_MEDIA = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".webp": "image/webp"}


@dataclass
class SolveResult:
    problems: list[dict[str, Any]]  # [{n, answers:[{value,(type)}]}]
    work: list[dict[str, Any]]  # [{n, confidence, work}]
    held: list[int]  # low-confidence ns needing a human
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


@dataclass
class Policy:
    max_usd: float = 2.0
    max_tokens: int = 8000
    min_confidence: str = "medium"
    held_action: str = "hold"  # hold low-confidence problems, never guess


def keychain_key(service: str = KEYCHAIN_SERVICE) -> str:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service,
             "-w"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError as e:
        raise ValueError("macOS `security` CLI not found") from e
    if out.returncode != 0:
        raise ValueError(
            f"no key '{service}' in the Keychain; store it once with:\n"
            f"  security add-generic-password -s {service} -a me -w")
    return out.stdout.strip()


def default_transport(url: str, headers: dict[str, str],
                      body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode())
        except Exception:  # noqa: BLE001 — raw code suffices
            detail = {"error": {"message": f"HTTP {e.code}"}}
        return e.code, detail


@dataclass
class Provider:
    api_key: str
    model: str = DEFAULT_MODEL
    api_url: str = API_URL
    auth: str = "x-api-key"  # or "bearer" (Meta Model API)
    transport: Callable[..., tuple[int, dict[str, Any]]] = default_transport

    def complete(self, system: str, user: str | list[dict[str, Any]],
                 max_tokens: int) -> dict[str, Any]:
        headers = {"anthropic-version": API_VERSION,
                   "content-type": "application/json"}
        if self.auth == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-api-key"] = self.api_key
        status, body = self.transport(
            self.api_url, headers,
            {"model": self.model, "max_tokens": max_tokens,
             "system": system,
             "messages": [{"role": "user", "content": user}]})
        if status in (401, 403):
            raise ValueError(f"API key rejected ({status}); check the "
                             f"Keychain item and funding")
        if status != 200:
            msg = body.get("error", {}).get("message", f"HTTP {status}")
            raise ValueError(f"solver API: {msg}")
        return body


def meta_provider(api_key: str,
                  model: str = META_DEFAULT_MODEL,
                  transport: Callable[..., tuple[int, dict[str, Any]]] | None = None,
                  ) -> Provider:
    """Meta Model API over its Anthropic-compatible Messages endpoint."""
    return Provider(api_key=api_key, model=model, api_url=META_API_URL,
                    auth="bearer",
                    transport=transport or default_transport)


def _strip_fences(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


def sanitize(problems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip solution-bearing fields before the model sees them.

    Fetched blanks carry `current` (the last submitted values) — sending
    them would let the solver copy instead of solve. Only the question
    shape goes out: text plus blank kinds, names, and option labels.
    """
    clean = []
    for p in problems:
        blanks = []
        for b in p["blanks"]:
            item: dict[str, Any] = {"kind": b["kind"], "name": b.get("name")}
            if "options" in b:
                item["options"] = [{"label": o["label"]} for o in b["options"]]
            blanks.append(item)
        clean.append({"n": p["n"], "text": p["text"], "blanks": blanks})
    return clean


def figure_blocks(problems: list[dict[str, Any]],
                  base_dir: str | Path | None) -> dict[int, list[dict[str, Any]]]:
    """Local figure files -> Anthropic image blocks per problem n.

    Best effort: unreadable or odd-typed figures are skipped (the model
    then judges confidence without them) rather than failing the run.
    """
    out: dict[int, list[dict[str, Any]]] = {}
    if base_dir is None:
        return out
    for p in problems:
        blocks = []
        for rel in p.get("figures", []) or []:
            try:
                raw = (Path(base_dir) / rel).read_bytes()
            except OSError:
                continue
            media = FIGURE_MEDIA.get(Path(rel).suffix.lower())
            if media is None:
                continue
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": media,
                                      "data": base64.b64encode(raw).decode()}})
        if blocks:
            out[p["n"]] = blocks
    return out


def solve_problems(provider: Provider, problems: list[dict[str, Any]],
                   policy: Policy | None = None,
                   base_dir: str | Path | None = None) -> SolveResult:
    """One API call solves every problem; shape-checked before return."""
    policy = policy or Policy()
    clean = sanitize(problems)
    prompt_text = json.dumps(clean)
    figs = figure_blocks(problems, base_dir)
    if figs:
        content: str | list[dict[str, Any]] = []
        for p in clean:
            for b in figs.get(p["n"], []):
                content.append(b)
            content.append({"type": "text",
                            "text": f"Problem {p['n']}: " + json.dumps(p)})
    else:
        content = prompt_text
    user = content
    # Worst-case cost gate BEFORE spending (input ~chars/4 tokens).
    in_price, out_price = PRICES.get(provider.model, DEFAULT_PRICE)
    worst = (len(user) / 4 / 1e6) * in_price + \
        (policy.max_tokens / 1e6) * out_price
    if worst > policy.max_usd:
        raise ValueError(
            f"solve would risk ${worst:.2f} over the ${policy.max_usd:.2f} "
            f"cap; raise --max-usd or split the set")
    last_error: ValueError | None = None
    solved: list[dict[str, Any]] = []
    total_in = total_out = 0
    # Contributor-tier calls occasionally come back with empty text;
    # prompt caching makes a retry cost almost nothing.
    for _ in range(3):
        body = provider.complete(SYSTEM, user, policy.max_tokens)
        usage = body.get("usage", {})
        total_in += usage.get("input_tokens", 0)
        total_out += usage.get("output_tokens", 0)
        text = "".join(b.get("text", "") for b in body.get("content", [])
                       if b.get("type") == "text")
        try:
            raw = json.loads(_strip_fences(text))
            solved = raw["problems"]
            last_error = None
            break
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            last_error = ValueError(
                f"solver returned unparsable output: {e}")
    if last_error is not None:
        raise last_error
    by_n = {p["n"]: p for p in problems}
    out: list[dict[str, Any]] = []
    work: list[dict[str, Any]] = []
    held: list[int] = []
    for entry in solved:
        n = entry.get("n")
        if n not in by_n:
            raise ValueError(f"solver answered unknown problem {n!r}")
        want = len(by_n[n]["blanks"])
        got = entry.get("answers", [])
        if len(got) != want:
            raise ValueError(f"solver gave {len(got)} answers for problem "
                             f"{n} with {want} blanks")
        conf = str(entry.get("confidence", "low")).lower()
        if conf not in CONFIDENCE:
            raise ValueError(f"problem {n}: bad confidence {conf!r}")
        if CONFIDENCE[conf] < CONFIDENCE[policy.min_confidence]:
            held.append(n)
        out.append({"n": n, "answers": [
            {"value": a["value"], **({"type": a["type"]} if "type" in a else {})}
            for a in got]})
        work.append({"n": n, "confidence": conf,
                     "work": entry.get("work", "")})
    missing = sorted(set(by_n) - {e["n"] for e in solved})
    if missing:
        raise ValueError(f"solver skipped problems {missing}")
    cost = total_in / 1e6 * in_price + total_out / 1e6 * out_price
    out.sort(key=lambda p: p["n"])
    work.sort(key=lambda p: p["n"])
    return SolveResult(problems=out, work=work, held=sorted(held),
                       input_tokens=total_in, output_tokens=total_out,
                       cost_usd=cost, model=provider.model)
