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
from .browser import HARNESS_ROOT, PROFILE_DIR, HarnessBrowser
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


def known_email(explicit: str | None) -> str | None:
    from . import okta
    if explicit:
        okta.EMAIL_FILE.parent.mkdir(parents=True, exist_ok=True)
        okta.EMAIL_FILE.write_text(explicit.strip())
        return explicit.strip()
    try:
        return okta.EMAIL_FILE.read_text().strip() or None
    except FileNotFoundError:
        return None


def full_auth(url: str, email: str) -> dict[str, str]:
    """Unattended Okta email/password/SMS login, then export the jar."""
    from . import okta
    try:
        password = okta.keychain_password()
    except ValueError as e:
        return {"status": "no-password", "detail": str(e)}
    with HarnessBrowser(headless=True) as b:
        page = b.new_page()
        result = okta.full_login(page, url, email, password)
        if result["status"] != "ok":
            return result
        assert b.context is not None
        jar = http_engine.export_playwright_cookies(b.context.cookies())
    probe = Engine(jar_path=jar).get(url)
    if http_engine.auth_failure_kind(probe) is None:
        return {"status": "ok", "detail": "full login complete, jar saved"}
    return {"status": "flow-changed",
            "detail": "browser finished but HTTP still fails"}


def cmd_http_auth(args: argparse.Namespace) -> int:
    if args.full:
        email = known_email(args.email)
        if email is None:
            print("error: pass --email '<msu-email>' once; it is remembered",
                  file=sys.stderr)
            return 2
        print(f"unattended Okta login as {email} (one attempt, SMS code "
              f"from Messages)...")
        result = full_auth(args.url, email)
        print(f"full login: {result['status']} — {result['detail']}")
        return 0 if result["status"] == "ok" else 1
    if args.refresh:
        result = refresh_auth(args.url, headed=False)
        if result["status"] != "ok" and "bot-wall" in result.get("detail", ""):
            print("headless hit the bot-wall; retrying visibly...")
            result = refresh_auth(args.url, headed=True)
        print(f"refresh: {result['status']} — {result['detail']}")
        return 0 if result["status"] == "ok" else 1
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
    if "msu.edu" in args.url:
        print("Tip: check 'Keep me signed in' on the school login — "
              "it lets `http-auth --refresh` heal future expiries alone.")
    return 0


def refresh_auth(url: str, headed: bool = False,
                 timeout_s: int = 75) -> dict[str, str]:
    """Redo the login dance with profile cookies alone — no typing, no user.

    Works when the school SSO session is still alive (long-lived if 'Keep
    me signed in' was checked). Returns {status, detail}; status is ok,
    needs-you, or timeout.
    """
    end = time.time() + timeout_s
    needs_hits = 0
    with HarnessBrowser(headless=not headed) as b:
        page = b.new_page()
        page.goto(url)
        while time.time() < end:
            page.wait_for_timeout(3000)
            state, reason = http_engine.classify_refresh_page(
                page.url, page.content())
            if state == "ready":
                assert b.context is not None
                n = len(b.context.cookies())
                jar = http_engine.export_playwright_cookies(
                    b.context.cookies())
                probe = Engine(jar_path=jar).get(url)
                if http_engine.auth_failure_kind(probe) is None:
                    return {"status": "ok",
                            "detail": f"session renewed ({n} cookies)"}
                return {"status": "timeout",
                        "detail": "browser looked ready but HTTP still fails"}
            if state == "needs-you":
                needs_hits += 1
                if needs_hits >= 2:
                    return {"status": "needs-you", "detail": reason}
            else:
                needs_hits = 0
    return {"status": "timeout",
            "detail": f"no app content after {timeout_s}s"}


def prefetch_auth(url: str) -> Engine:
    """Engine with a live session. On expiry: headless refresh first,
    then one unattended Okta+SMS login when set up, else the exact user
    command. Call before any HTTP run. keepalive never calls this — a
    scheduler must not fire SMS logins on its own."""
    engine = Engine()
    try:
        html = engine.get(url)
    except Exception:  # noqa: BLE001 — network errors aren't auth errors
        return engine
    if http_engine.auth_failure_kind(html) is None:
        return engine
    print("session expired; attempting headless refresh...")
    result = refresh_auth(url)
    print(f"refresh: {result['status']} — {result['detail']}")
    if result["status"] == "ok":
        return Engine()
    email = known_email(None)
    if result["status"] == "needs-you" and email is not None:
        print("refresh needs you; attempting one Okta+SMS login...")
        full = full_auth(url, email)
        print(f"full login: {full['status']} — {full['detail']}")
        if full["status"] == "ok":
            return Engine()
    raise ValueError(
        "session expired and unattended login is not set up or failed: run "
        f"`harness http-auth '{url}'` (check 'Keep me signed in'), or set "
        "up `http-auth --full` with --email plus a Keychain password")


def cmd_keepalive(args: argparse.Namespace) -> int:
    import subprocess as _subprocess
    state_file = PROFILE_DIR / "keepalive_state.json"
    try:
        state = json.loads(state_file.read_text())
    except (FileNotFoundError, ValueError):
        state = {"consecutive_failures": 0}
    engine = Engine()
    try:
        html = engine.get(args.url)
    except Exception as e:  # noqa: BLE001 — report, don't crash from cron
        print(f"expired (fetch failed: {e})")
        failed = True
    else:
        kind = http_engine.auth_failure_kind(html)
        failed = kind is not None
        print("alive" if not failed else f"expired ({kind})")
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1 \
        if failed else 0
    try:
        state_file.write_text(json.dumps(state))
    except OSError:
        pass
    if failed and state["consecutive_failures"] >= 2:
        # Rot that pages instead of festering: two bad ticks in a row
        # means refresh isn't healing it. Best effort, never fatal.
        try:
            _subprocess.run(
                ["osascript", "-e",
                 'display notification "WeBWorK session expired and '
                 "auto-refresh isn't healing it. Run harness http-auth.\" "
                 'with title "answer-entry keepalive"'], timeout=15,
                capture_output=True)
        except Exception:  # noqa: BLE001 — notification is a courtesy
            pass
    return 1 if failed else 0


def run_smoke(checks: list[tuple[str, object]]) -> list[dict[str, object]]:
    """Run named zero-arg check callables -> [{name, ok, detail}].

    A check returns (ok, detail); raised exceptions become failures.
    Everything here must be read-only: smoke never submits, never
    fires SMS logins, never writes sessions.
    """
    results = []
    for name, fn in checks:
        assert callable(fn)
        try:
            ok, detail = fn()  # type: ignore[misc]
        except Exception as e:  # noqa: BLE001 — a crashed check is a failed check
            ok, detail = False, f"{type(e).__name__}: {e}"
        results.append({"name": name, "ok": bool(ok), "detail": str(detail)})
    return results


def cmd_smoke(args: argparse.Namespace) -> int:
    import subprocess as _subprocess
    from . import okta as _okta, sms as _sms

    def ww():
        html = Engine().get(args.ww_url)
        kind = http_engine.auth_failure_kind(html)
        return kind is None, "alive" if kind is None else f"expired ({kind})"

    def keychain():
        r = _subprocess.run(
            ["security", "find-generic-password", "-s",
             _okta.KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=15)
        return r.returncode == 0, ("present" if r.returncode == 0
                                   else "missing (see Unattended Okta login)")

    def smsdb():
        n = _sms.latest_rowid()
        return True, f"readable (marker {n})"

    def thjwt():
        from . import tophat as _th
        try:
            tokens = json.loads(_th.TOKEN_FILE.read_text())
        except (FileNotFoundError, ValueError):
            return False, "no saved tokens (run th-auth)"
        left = _th.token_expiry(tokens.get("access", "")) - time.time()
        if left > 3600:
            return True, f"fresh ({left / 3600:.1f}h left)"
        # Stale-between-uses is the normal idle state: th-* commands
        # refresh from the profile on next use. Not a failure.
        return True, "stale, refreshes on next use"

    checks: list[tuple[str, object]] = [
        ("webwork", ww), ("keychain", keychain), ("sms-db", smsdb)]
    if args.ww_url == "skip":
        checks = [c for c in checks if c[0] != "webwork"]
    if args.th_code:
        def thapi():
            from . import tophat as _th
            tokens = json.loads(_th.TOKEN_FILE.read_text())
            if _th.token_expiry(tokens.get("access", "")) < time.time() + 60:
                return True, "skipped (token sleeps; refreshes on use)"
            # Static token: smoke observes, never refreshes or writes.
            client = _th.Client(
                token_provider=lambda: tokens.get("access", ""))
            course = client.course_id(args.th_code)
            tree = client.tree(course)
            return True, (f"course {course}, "
                          f"{len(tree.get('children', []))} roots")
        checks.extend([("tophat-jwt", thjwt), ("tophat-api", thapi)])
    else:
        checks.append(("tophat-jwt", thjwt))
    results = run_smoke(checks)
    for r in results:
        print(f"[{'ok' if r['ok'] else 'FAIL'}] {r['name']}: {r['detail']}")
    bad = [r for r in results if not r["ok"]]
    print(f"smoke: {len(results) - len(bad)}/{len(results)} pass")
    return 1 if bad else 0


def cmd_http_fetch(args: argparse.Namespace) -> int:
    tracker = Tracker()
    if args.answers.startswith("http"):
        engine = prefetch_auth(args.answers)
        stubs = [{"n": n, "url": u}
                 for n, u in http_engine.enumerate_set(engine, args.answers)]
        print(f"enumerated {len(stubs)} problems from set page")
    else:
        answers = load_answers(args.answers)
        stubs = [{"n": p.n, "url": answers.problem_url(p)} for p in answers.problems]
        engine = prefetch_auth(stubs[0]["url"])
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
    engine = prefetch_auth(answers.problem_url(answers.problems[0]))
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
    engine = prefetch_auth(args.set_url)
    rows = http_engine.fetch_set_status(engine, args.set_url)
    for r in rows:
        pct = f"{r['percent']:g}%" if r["percent"] is not None else "no score yet"
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
    s.add_argument("--refresh", action="store_true",
                   help="cookie-only SSO re-dance, no interaction")
    s.add_argument("--full", action="store_true",
                   help="unattended Okta+SMS login (needs --email, Keychain pw)")
    s.add_argument("--email", default=None, help="MSU email (remembered)")
    s.set_defaults(func=cmd_http_auth)

    s = sub.add_parser("keepalive", help="report whether the HTTP session is alive (for cron)")
    s.add_argument("url")
    s.set_defaults(func=cmd_keepalive)

    s = sub.add_parser("smoke", help="read-only health of sessions/credentials/APIs")
    s.add_argument("--ww-url", default="skip", help="WeBWorK page to probe")
    s.add_argument("--th-code", default=None, help="Top Hat public code")
    s.set_defaults(func=cmd_smoke)

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
