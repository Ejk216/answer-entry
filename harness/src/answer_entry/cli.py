"""`harness` — scripted hands beneath the answer-entry skill."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import webwork
from .browser import HARNESS_ROOT, HarnessBrowser
from .model import load_answers


def cmd_login(args: argparse.Namespace) -> int:
    with HarnessBrowser(headless=False) as b:
        page = b.new_page()
        if args.url:
            page.goto(args.url)
        print("Sign in to every site this homework needs, then press Enter here.")
        try:
            input()
        except EOFError:
            pass
    print(f"Profile saved under {HARNESS_ROOT / '.profile'} — sessions persist.")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    with HarnessBrowser(headless=args.headless) as b:
        page = b.new_page()
        dump = webwork.read_problem(page, args.url)
        buttons = page.locator("button, input[type=submit], input[type=button]").evaluate_all(
            "els => els.map(e => (e.innerText || e.value || '').trim()).filter(Boolean)")
        dump["buttons"] = buttons
        if args.save_html:
            out = Path(args.save_html)
            out.write_text(page.content())
            dump["saved_html"] = str(out)
    print(json.dumps(dump, indent=2)[: args.chars])
    return 0


def cmd_read_problem(args: argparse.Namespace) -> int:
    with HarnessBrowser() as b:
        dump = webwork.read_problem(b.new_page(), args.url)
    if args.json:
        print(json.dumps(dump, indent=2))
    else:
        print(f"== {dump['url']} (text via {dump['text_via']}, {dump['text_confidence']} confidence)")
        print(dump["text"])
        print(f"-- {len(dump['widgets'])} widgets --")
        for i, w in enumerate(dump["widgets"]):
            print(f"[{i}] {w['kind']}" + (f" name={w.get('name')}" if w.get("name") else ""))
            for o in w.get("options", []):
                print(f"      {o.get('label')!r}")
    return 0


def cmd_read_set(args: argparse.Namespace) -> int:
    answers = load_answers(args.answers)
    with HarnessBrowser() as b:
        assert b.context is not None
        dumps = webwork.read_set(b.context, answers)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "problems.json").write_text(json.dumps(dumps, indent=2))
    print(f"read {len(dumps)} problems -> {out / 'problems.json'}")
    for d in dumps:
        print(f"  {d['url']}: {len(d['widgets'])} widgets, text {d['text_confidence']}")
    return 0


def cmd_enter(args: argparse.Namespace) -> int:
    answers = load_answers(args.answers)
    only = set(args.only) if args.only else None
    reports = []
    with HarnessBrowser(headless=args.headless) as b:
        page = b.new_page()
        for p in answers.problems:
            if only is not None and p.n not in only:
                continue
            url = answers.problem_url(p)
            report = webwork.enter_problem(page, p, url, dry_run=args.dry_run)
            reports.append(report)
            print(f"problem {p.n}: {report['status']} — {report.get('detail', '')}")
            if report["status"] not in ("ok", "submitted", "dry_run_ok"):
                print("stopping: nothing further submitted.", file=sys.stderr)
                break
    if args.json:
        print(json.dumps(reports, indent=2))
    bad = [r for r in reports if r["status"] not in ("ok", "dry_run_ok")]
    return 1 if bad else 0


def cmd_status(args: argparse.Namespace) -> int:
    with HarnessBrowser() as b:
        result = webwork.set_status(b.new_page(), args.set_url)
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="harness", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("login", help="headed sign-in; sessions persist in .profile/")
    s.add_argument("url", nargs="?", help="page to open for sign-in")
    s.set_defaults(func=cmd_login)

    s = sub.add_parser("probe", help="dump page structure JSON (selector development)")
    s.add_argument("url")
    s.add_argument("--save-html", default=None, help="also save raw HTML here")
    s.add_argument("--chars", type=int, default=6000, help="max JSON chars to print")
    s.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    s.set_defaults(func=cmd_probe)

    s = sub.add_parser("read-problem", help="print one problem's text + widget inventory")
    s.add_argument("url")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_read_problem)

    s = sub.add_parser("read-set", help="read every problem listed in an answers file")
    s.add_argument("answers", help="answers.json (only n/url used)")
    s.add_argument("--out", default="dumps/set", help="output directory")
    s.set_defaults(func=cmd_read_set)

    s = sub.add_parser("enter", help="fill, verify, submit every problem in answers.json")
    s.add_argument("answers")
    s.add_argument("--dry-run", action="store_true", help="fill + verify, never submit")
    s.add_argument("--only", type=int, nargs="*", default=None, help="problem numbers to enter")
    s.add_argument("--json", action="store_true", help="also print full reports as JSON")
    s.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    s.set_defaults(func=cmd_enter)

    s = sub.add_parser("status", help="per-problem status from a set page (best effort)")
    s.add_argument("set_url")
    s.set_defaults(func=cmd_status)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
