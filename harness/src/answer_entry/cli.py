"""`harness` — scripted hands beneath the answer-entry skill."""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

from . import chunks, http_engine, webwork
from .browser import HARNESS_ROOT, HarnessBrowser
from .http_engine import Engine
from .model import load_answers, parse_answers_dict
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
    engine = Engine()
    tracker = Tracker()
    if args.answers.startswith("http"):
        stubs = [{"n": n, "url": u}
                 for n, u in http_engine.enumerate_set(engine, args.answers)]
        print(f"enumerated {len(stubs)} problems from set page")
    else:
        answers = load_answers(args.answers)
        stubs = [{"n": p.n, "url": answers.problem_url(p)} for p in answers.problems]
    urls = [s["url"] for s in stubs]
    pages = engine.fetch_all(urls, workers=args.workers, tracker=tracker)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dumps = []
    failed = []
    with tracker.phase("parse"):
        for s in stubs:
            n, url = s["n"], s["url"]
            try:
                parsed = http_engine.parse_problem(pages[url], url)
                html = pages[url]
            except ValueError:
                try:  # transient bounce: retry serially before giving up
                    parsed, html = http_engine.get_problem_page(engine, url)
                except ValueError as e:
                    failed.append((n, str(e)))
                    continue
            (out / f"problem-{n}.html").write_text(html)
            dumps.append({"n": n, "url": url, "text": parsed.text,
                          "blanks": parsed.blanks, "images": parsed.images})
    if failed:
        print("failed to fetch: " + ", ".join(f"p{n}" for n, _ in failed))
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
    return 1 if failed else 0


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


def cmd_split(args: argparse.Namespace) -> int:
    problems = json.loads(Path(args.problems).read_text())
    parts = chunks.split_problems(problems, args.chunks)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(parts):
        (out / chunks.chunk_name(i)).write_text(json.dumps(part, indent=1))
        (out / chunks.answers_name(i)).write_text(json.dumps(
            {"problems": [{"n": p["n"], "url": p["url"], "answers": []}
                           for p in part]}, indent=1))
        ns = [p["n"] for p in part]
        print(f"{chunks.chunk_name(i)}: problems {ns[0]}-{ns[-1]} "
              f"(solve into {chunks.answers_name(i)})")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    dicts = [json.loads(Path(f).read_text()) for f in args.files]
    merged = chunks.merge_answer_dicts(dicts)
    answers = parse_answers_dict(merged)  # validates shape, dupes, types
    Path(args.o).write_text(json.dumps(merged, indent=1))
    print(f"merged {len(answers.problems)} problems "
          f"({[p.n for p in answers.problems]}) -> {args.o}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with HarnessBrowser() as b:
        result = webwork.set_status(b.new_page(), args.set_url)
    print(json.dumps(result, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    from .validate import validate_answers
    answers = load_answers(args.answers)
    problems = json.loads(Path(args.problems).read_text())
    result = validate_answers(problems, answers)
    for e in result.errors:
        print(f"error: {e}")
    for w in result.warnings:
        print(f"warning: {w}")
    print(f"validate: {len(result.errors)} errors, "
          f"{len(result.warnings)} warnings "
          f"({len(answers.problems)} problems checked)")
    return 1 if result.errors else 0


def cmd_recon(args: argparse.Namespace) -> int:
    """Headed browser + API traffic log. Drive the site yourself; every
    XHR/fetch request/response lands in JSONL for offline analysis."""
    log: list[dict] = []

    # Auth endpoints carry passwords/tokens in the clear: log the URL and
    # status, never the bodies. (Oct 2026: a recon run captured an MSU
    # password from a login POST before this guard existed.)
    sensitive = ("auth", "login", "signin", "token", "jwt", "password",
                 "session", "sso", "oauth")

    def on_response(resp) -> None:
        try:
            req = resp.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            entry = {"method": req.method, "url": req.url,
                     "status": resp.status}
            if any(k in req.url.lower() for k in sensitive):
                entry["request"] = "<redacted: auth endpoint>"
                entry["response"] = "<redacted: auth endpoint>"
            else:
                entry["request"] = (req.post_data or "")[:2000]
                try:
                    ctype = resp.headers.get("content-type", "")
                    body = resp.text()
                    entry["response"] = (body[:4000] if "json" in ctype
                                         else f"<{ctype}, {len(body)} bytes>")
                except Exception as e:  # noqa: BLE001 — log the failure, keep going
                    entry["response"] = f"<unreadable: {e}>"
            log.append(entry)
        except Exception:  # noqa: BLE001 — recon must never break browsing
            pass

    with HarnessBrowser(headless=False) as b:
        page = b.new_page()
        page.on("response", on_response)
        page.goto(args.url)
        print("Drive the site (answer, save, navigate), then press Enter here.")
        try:
            input()
        except EOFError:
            pass
    out = Path(args.out)
    out.write_text("\n".join(json.dumps(e) for e in log) + "\n")
    print(f"captured {len(log)} API calls -> {out}")
    return 0


def cmd_d2l_dump(args: argparse.Namespace) -> int:
    from . import d2l
    with HarnessBrowser() as b:
        page = b.new_page()
        page.goto(args.url)
        frame = d2l.find_quiz_frame(page)
        if frame is None:
            print("error: no frame holds quiz radios; sign in first?",
                  file=sys.stderr)
            return 1
        dump = d2l.dump_quiz(frame)
    dump["url"] = args.url
    if args.json:
        print(json.dumps(dump, indent=2))
    else:
        for q in dump["questions"]:
            mark = "answered" if q["answered"] else "UNANSWERED"
            print(f"-- Q{q['n']} [{mark}] {q['stem']}")
            for i, o in enumerate(q["options"]):
                tick = " [x]" if o["checked"] else ""
                print(f"     ({i}) {o['label']!r}{tick}")
        f = dump["footer"]
        print(f"footer: {f['raw'] if f else 'no counter found'}")
        print(f"answered pattern: {dump['answered_pattern']} "
              f"(confirm against the navigator before entering)")
    return 0


def cmd_d2l_enter(args: argparse.Namespace) -> int:
    from . import d2l
    answers = load_answers(args.answers)
    if not answers.set_url:
        print("error: answers file needs set_url (the quiz attempt URL)",
              file=sys.stderr)
        return 2
    with HarnessBrowser() as b:
        report = d2l.enter_quiz(b.new_page(), answers.set_url, answers,
                                dry_run=args.dry_run)
    print(f"status: {report['status']} — {report.get('detail', '')}")
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report["status"] in ("ok", "dry_run_ok") else 1


def cmd_th_auth(args: argparse.Namespace) -> int:
    from . import tophat
    with HarnessBrowser(headless=False) as b:
        page = b.new_page()
        page.goto(args.url)
        print("Sign in, then press Enter here.")
        try:
            input()
        except EOFError:
            pass
    tokens = tophat.read_tokens_from_profile()
    exp = tophat.token_expiry(tokens["access"])
    print(f"saved Top Hat JWT -> {tophat.TOKEN_FILE} "
          f"(expires {time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))})")
    return 0


def _th_client_with_course(urls: list[str], folder: str | None):
    from . import tophat
    if not urls:
        raise ValueError("need at least one Top Hat URL (/e/<code>/...)")
    client = tophat.Client()
    course = client.course_id(tophat.public_code(urls[0]))
    items: list[tuple[str, str]] = []  # (display, content id)
    if folder:
        tree = client.tree(course)
        mappings = client.id_mappings(course)
        for nid, name in tophat.enumerate_folder(tree, folder):
            if nid in mappings:
                items.append((name, mappings[nid]))
        if not items:
            raise ValueError(f"folder {folder!r}: no items bridge to content")
    for u in urls:
        m = re.search(r"/item/(\d+::[0-9a-f-]+)", u)
        if m and all(cid != m.group(1) for _, cid in items):
            items.append((m.group(1), m.group(1)))
    if not items:
        raise ValueError("no content items: pass item URLs and/or --folder")
    return client, course, items


def cmd_th_fetch(args: argparse.Namespace) -> int:
    from . import tophat
    client, course, items = _th_client_with_course(args.urls, args.folder)
    print(f"course {course}, {len(items)} items")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dumps = []
    failed = []
    for n, (display, cid) in enumerate(items, 1):
        try:
            q = client.fetch_item(course, cid)
        except ValueError as e:
            failed.append((display, str(e)))
            continue
        (out / f"item-{n}.json").write_text(json.dumps(
            {"cid": cid, "title": q.title, "stem": q.stem,
             "options": q.options, "can_submit": q.can_submit,
             "profile": q.profile}, indent=1))
        text = q.stem + "\n" + "\n".join(
            f"({o['id']}) {o['label']}" for o in q.options)
        dumps.append({"n": n, "url": args.urls[0], "cid": cid,
                      "title": q.title, "text": text,
                      "blanks": [{"kind": "radio", "name": q.part,
                                  "options": [{"label": o["label"],
                                               "value": str(o["id"])}
                                              for o in q.options]}],
                      "images": []})
        print(f"  [{n}] {q.title or display}: {len(q.options)} options")
    (out / "problems.json").write_text(json.dumps(dumps, indent=2))
    for display, e in failed:
        print(f"  FAILED {display}: {e}")
    print(f"fetched {len(dumps)}/{len(items)} -> {out / 'problems.json'}")
    return 1 if failed else 0


def cmd_th_enter(args: argparse.Namespace) -> int:
    from . import tophat
    answers = load_answers(args.answers)
    problems = {p["n"]: p for p in
                json.loads(Path(args.problems).read_text())}
    client = tophat.Client()
    course = client.course_id(tophat.public_code(answers.set_url or ""))
    only = set(args.only) if args.only else None
    reports = []
    for p in answers.problems:
        if only is not None and p.n not in only:
            continue
        dump = problems.get(p.n)
        if dump is None or "cid" not in dump:
            print(f"question {p.n}: no fetch dump; run th-fetch first")
            break
        if len(p.answers) != 1 or not isinstance(p.answers[0].value, str):
            print(f"question {p.n}: want exactly 1 string answer")
            break
        r = tophat.enter_question(client, course, p.n, dump["cid"],
                                  p.answers[0].value,
                                  dry_run=args.dry_run)
        reports.append(dataclasses.asdict(r))
        print(f"question {p.n}: {r.status} — {r.detail}")
        if r.status not in ("ok", "submitted", "dry_run_ok"):
            print("stopping: nothing further submitted.", file=sys.stderr)
            break
    if args.json:
        print(json.dumps(reports, indent=2))
    bad = [r for r in reports if r["status"] not in ("ok", "dry_run_ok")]
    return 1 if bad else 0


def cmd_th_status(args: argparse.Namespace) -> int:
    from . import tophat
    client, course, items = _th_client_with_course(args.urls, args.folder)
    done = client.answered(course)
    by_cid = {cid: nid for nid, cid in
              client.id_mappings(course).items()}
    for n, (display, cid) in enumerate(items, 1):
        nid = by_cid.get(cid)
        mark = ("answered" if nid in done else "OPEN") if nid else "?"
        print(f"  [{n}] {display}: {mark}")
    print(f"course {course}: {len(done)} answered ids total")
    return 0


def cmd_http_status(args: argparse.Namespace) -> int:
    engine = Engine()
    rows = http_engine.fetch_set_status(engine, args.set_url)
    for r in rows:
        pct = f"{r['percent:g']}%" if r["percent"] is not None else "no score yet"
        print(f"problem {r['n']}: {pct}")
    full = sum(1 for r in rows if r["percent"] == 100)
    print(f"{full}/{len(rows)} at 100%")
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

    s = sub.add_parser("http-fetch", help="parallel HTTP fetch + parse from answers.json or a set URL")
    s.add_argument("answers", help="answers.json file or set page URL")
    s.add_argument("--out", default="dumps/http-set", help="output directory")
    s.add_argument("--figures", action="store_true", help="also download figure images")
    s.add_argument("--workers", type=int, default=2, help="parallel fetch workers")
    s.set_defaults(func=cmd_http_fetch)

    s = sub.add_parser("split", help="split problems.json into chunks for parallel solving")
    s.add_argument("problems")
    s.add_argument("--out", default="dumps/chunks", help="output directory")
    s.add_argument("--chunks", type=int, default=3, help="number of chunks")
    s.set_defaults(func=cmd_split)

    s = sub.add_parser("merge", help="merge chunk answer files into one validated answers.json")
    s.add_argument("files", nargs="+", help="chunk-N.answers.json files")
    s.add_argument("-o", required=True, help="output answers.json")
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("http-enter", help="HTTP fill + submit (validated live on 2.19)")
    s.add_argument("answers")
    s.add_argument("--dry-run", action="store_true", help="preview POST, never submit")
    s.add_argument("--only", type=int, nargs="*", default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_http_enter)

    s = sub.add_parser("validate", help="offline answers.json check against problems.json")
    s.add_argument("answers")
    s.add_argument("--problems", required=True, help="problems.json from http-fetch")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("http-status", help="per-problem scores from a set page (HTTP)")
    s.add_argument("set_url")
    s.set_defaults(func=cmd_http_status)

    s = sub.add_parser("recon", help="headed browser that logs API traffic to JSONL")
    s.add_argument("url")
    s.add_argument("--out", default="dumps/recon.jsonl", help="output file")
    s.set_defaults(func=cmd_recon)

    s = sub.add_parser("d2l-dump", help="dump a D2L quiz attempt (shadow-DOM traversal)")
    s.add_argument("url")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_d2l_dump)

    s = sub.add_parser("d2l-enter", help="D2L fill + Save All (never submits)")
    s.add_argument("answers", help="answers.json with set_url = attempt URL")
    s.add_argument("--dry-run", action="store_true", help="plan clicks, make none")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_d2l_enter)

    s = sub.add_parser("th-auth", help="headed Top Hat sign-in, export JWT")
    s.add_argument("url")
    s.set_defaults(func=cmd_th_auth)

    s = sub.add_parser("th-fetch", help="fetch Top Hat items (single-part MC)")
    s.add_argument("urls", nargs="+", help="item URLs (any /e/<code>/ URL works)")
    s.add_argument("--folder", default=None, help="course-tree folder title")
    s.add_argument("--out", default="dumps/th-set", help="output directory")
    s.set_defaults(func=cmd_th_fetch)

    s = sub.add_parser("th-enter", help="Top Hat submit + instant grade (single-part MC)")
    s.add_argument("answers")
    s.add_argument("--problems", required=True, help="problems.json from th-fetch")
    s.add_argument("--dry-run", action="store_true", help="resolve labels, never POST")
    s.add_argument("--only", type=int, nargs="*", default=None)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_th_enter)

    s = sub.add_parser("th-status", help="answered? per Top Hat item")
    s.add_argument("urls", nargs="+")
    s.add_argument("--folder", default=None)
    s.set_defaults(func=cmd_th_status)

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
