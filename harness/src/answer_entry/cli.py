"""`harness` — scripted hands beneath the answer-entry skill."""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import urllib.parse
from pathlib import Path

from . import http_engine, webwork
from .browser import HARNESS_ROOT, HarnessBrowser
from .http_engine import Engine
from .model import load_answers
from .timing import Tracker


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
    tracker = Tracker()
    with HarnessBrowser() as b:
        assert b.context is not None
        with tracker.phase("read_set"):
            dumps = webwork.read_set(b.context, answers)
    print("timings:", tracker.summary())
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
    tracker = Tracker()
    with HarnessBrowser(headless=args.headless) as b:
        page = b.new_page()
        for p in answers.problems:
            if only is not None and p.n not in only:
                continue
            url = answers.problem_url(p)
            with tracker.phase(f"p{p.n}"):
                report = webwork.enter_problem(page, p, url, dry_run=args.dry_run)
            reports.append(report)
            print(f"problem {p.n}: {report['status']} — {report.get('detail', '')}")
            if report["status"] not in ("ok", "submitted", "dry_run_ok"):
                print("stopping: nothing further submitted.", file=sys.stderr)
                break
    print("timings:", tracker.summary())
    if args.json:
        print(json.dumps({"reports": reports, "timings": tracker.report()}, indent=2))
    bad = [r for r in reports if r["status"] not in ("ok", "dry_run_ok")]
    return 1 if bad else 0


def cmd_http_auth(args: argparse.Namespace) -> int:
    with HarnessBrowser(headless=False) as b:
        page = b.new_page()
        page.goto(args.url)
        print("Sign in, then press Enter here.")
        try:
            input()
        except EOFError:
            pass
        assert b.context is not None
        cookies = b.context.cookies()
    jar = http_engine.export_playwright_cookies(cookies)
    engine = Engine(jar_path=jar)
    html = engine.get(args.url)
    print(f"saved {len(cookies)} cookies -> {jar}; verify GET: {len(html)} chars")
    return 0


def cmd_http_fetch(args: argparse.Namespace) -> int:
    answers = load_answers(args.answers)
    engine = Engine()
    tracker = Tracker()
    urls = [answers.problem_url(p) for p in answers.problems]
    pages = engine.fetch_all(urls, tracker=tracker)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dumps = []
    with tracker.phase("parse"):
        for p in answers.problems:
            url = answers.problem_url(p)
            parsed = http_engine.parse_problem(pages[url], url)
            (out / f"problem-{p.n}.html").write_text(pages[url])
            dumps.append({"n": p.n, "url": url, "text": parsed.text,
                          "blanks": parsed.blanks, "images": parsed.images})
    (out / "problems.json").write_text(json.dumps(dumps, indent=2))
    if args.figures:
        with tracker.phase("figures"):
            figdir = out / "figures"
            figdir.mkdir(exist_ok=True)
            for d in dumps:
                for i, src in enumerate(d["images"]):
                    try:
                        ext = Path(urllib.parse.urlparse(src).path).suffix or ".img"
                        (figdir / f"p{d['n']}-{i}{ext}").write_bytes(
                            engine.get_bytes(src))
                    except Exception as e:  # noqa: BLE001 — one bad image kills nothing
                        print(f"  warning: figure {src} failed: {e}")
    print(f"fetched {len(dumps)} problems -> {out / 'problems.json'}")
    print("timings:", tracker.summary())
    return 0


def cmd_http_enter(args: argparse.Namespace) -> int:
    answers = load_answers(args.answers)
    only = set(args.only) if args.only else None
    engine = Engine()
    tracker = Tracker()
    reports = []
    for p in answers.problems:
        if only is not None and p.n not in only:
            continue
        url = answers.problem_url(p)
        values = [a.value for a in p.answers]
        with tracker.phase(f"p{p.n}"):
            r = http_engine.enter_problem(engine, p.n, url, values,
                                          dry_run=args.dry_run,
                                          tracker=tracker)
        reports.append(dataclasses.asdict(r))
        print(f"problem {p.n}: {r.status} — {r.detail}")
        if r.status not in ("ok", "submitted", "dry_run_ok"):
            print("stopping: nothing further submitted.", file=sys.stderr)
            break
    print("timings:", tracker.summary())
    if args.json:
        print(json.dumps({"reports": reports, "timings": tracker.report()}, indent=2))
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

    s = sub.add_parser("http-auth", help="headed sign-in, then export cookies to the HTTP engine")
    s.add_argument("url")
    s.set_defaults(func=cmd_http_auth)

    s = sub.add_parser("http-fetch", help="parallel HTTP fetch + parse of every problem in answers.json")
    s.add_argument("answers")
    s.add_argument("--out", default="dumps/http-set", help="output directory")
    s.add_argument("--figures", action="store_true", help="also download figure images")
    s.set_defaults(func=cmd_http_fetch)

    s = sub.add_parser("http-enter", help="HTTP fill + submit (validated live on 2.19)")
    s.add_argument("answers")
    s.add_argument("--dry-run", action="store_true", help="preview POST, never submit")
    s.add_argument("--only", type=int, nargs="*", default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_http_enter)

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
