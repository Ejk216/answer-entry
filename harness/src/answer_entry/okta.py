"""Unattended school login: Okta email + password + SMS code.

Path: SP -> Okta identifier -> password -> choose SMS authenticator ->
code from the Mac Messages watcher -> back to the SP. Single attempt,
no retries (hammering SSO risks lockout); any unexpected screen aborts
with a state dump so one joint run maps whatever changed. Passwords and
codes never touch logs, files, or output — the password lives in the
macOS Keychain, the code in process memory.
"""
from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Any

from . import http_engine, sms

if TYPE_CHECKING:
    from playwright.sync_api import Page

KEYCHAIN_SERVICE = "answer-entry-msu"
EMAIL_FILE = http_engine.PROFILE_DIR / "okta_email"

# Okta's verify screen defaults to the enrolled authenticator (here: Okta
# Verify push) with a link to pick another. Observed link/option wordings
# go here as they're confirmed; misses fail loud via the state dump.
SWITCH_TEXT = r"verify with something else|other options|select.*authenticator|choose.*authenticator"
SMS_TEXT = r"\bSMS\b|text message|^phone$|receive .* sms|send .* sms"


def keychain_password() -> str:
    """MSU password from the Keychain, or a setup error (never the pw)."""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-w"], capture_output=True, text=True, timeout=15)
    except FileNotFoundError as e:
        raise ValueError("macOS `security` CLI not found") from e
    if out.returncode != 0:
        raise ValueError(
            "no MSU password in the Keychain; store it once with:\n"
            "  security add-generic-password -s answer-entry-msu "
            "-a '<msu-email>' -w")
    return out.stdout.strip()


def page_state(page: "Page") -> dict[str, Any]:
    """Shape of the current screen for failure reports. Names and labels
    only — never field values."""
    try:
        buttons = page.locator("button, input[type=submit]").evaluate_all(
            "els => els.map(e => (e.innerText || e.value || '').trim())"
            ".filter(Boolean).slice(0, 12)")
        inputs = page.locator("input").evaluate_all(
            "els => els.filter(e => e.offsetParent !== null).map(e => "
            "({type: e.type, name: e.name || null}))")
        text = page.locator("body").inner_text()[:300]
    except Exception as e:  # noqa: BLE001 — state dump must not throw
        return {"error": f"unreadable: {e}"}
    return {"url": page.url[:120], "title": (page.title() or "")[:80],
            "buttons": buttons, "inputs": inputs, "text": text}


def _fill(page: "Page", selectors: list[str], value: str, what: str,
          human: bool = False) -> None:
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=8000)
            if human:
                # Trusted keystrokes for bot-sensitive fields; length-only
                # read-back proves the fill landed without exposing it.
                loc.click()
                loc.press_sequentially(value, delay=12)
                if not loc.input_value():
                    raise ValueError(f"{what}: fill did not land")
            else:
                loc.fill(value)
            return
        except ValueError:
            raise
        except Exception:  # noqa: BLE001 — try the next selector
            continue
    raise ValueError(f"{what}: field not found")


def _click_text(page: "Page", pattern: str, what: str,
                timeout_ms: int = 8000) -> bool:
    """Click visible text matching pattern; False when absent (skippable)."""
    loc = page.get_by_text(re.compile(pattern, re.IGNORECASE)).first
    try:
        loc.wait_for(state="visible", timeout=timeout_ms)
    except Exception:  # noqa: BLE001 — absence means the step was skipped
        return False
    loc.click()
    return True


def full_login(page: "Page", url: str, email: str,
               password: str) -> dict[str, str]:
    """One unattended Okta pass. Returns {status, detail}; status is ok,
    flow-changed (with a state dump), or sms-timeout."""
    try:
        page.goto(url)
        page.wait_for_timeout(3000)
        state, _ = http_engine.classify_refresh_page(url, page.content())
        if state == "ready":
            return {"status": "ok", "detail": "already signed in"}
        # 1. identifier (skipped when Okta remembers it)
        try:
            _fill(page, ['input[name="identifier"]', 'input[type="email"]'],
                  email, "identifier")
            # "Keep me signed in" extends the SSO session for weeks, so
            # future cookie-only refreshes heal alone. Best effort.
            try:
                box = page.locator(
                    'input[name="rememberMe"], input[type="checkbox"]'
                    ).first
                if box.count() and not box.is_checked():
                    box.check()
            except Exception:  # noqa: BLE001 — the login works regardless
                pass
            page.locator('input[type="submit"], button[type="submit"]'
                         ).first.click()
            page.wait_for_timeout(2500)
        except ValueError:
            pass
        # 2. password (human-like keystrokes; Okta is bot-sensitive)
        _fill(page, ['input[name="credentials.passcode"]',
                     'input[type="password"]'], password, "password",
              human=True)
        page.locator('input[type="submit"], button[type="submit"]'
                     ).first.click()
        page.wait_for_timeout(4000)
        body_text = page.locator("body").inner_text()
        if "unable to sign in" in body_text.lower():
            return {"status": "bad-password",
                    "detail": "Okta rejected the password submit. Either "
                    "the stored password is wrong or Okta is risk-blocking "
                    "this automated context. Re-store with: security "
                    "delete-generic-password -s answer-entry-msu && security "
                    "add-generic-password -s answer-entry-msu -a "
                    "'<msu-email>' -w. Page text: " + body_text[:400]}
        # 3. switch from the default (push) authenticator to SMS. If no
        # switch link appears, Okta may already be on code entry.
        switched = _click_text(page, SWITCH_TEXT, "challenge list",
                               timeout_ms=12000)
        if switched:
            page.wait_for_timeout(2000)
            if not _click_text(page, SMS_TEXT, "SMS option",
                               timeout_ms=10000):
                raise ValueError("SMS authenticator not offered")
            page.wait_for_timeout(2000)
            # Phone options sometimes ask voice-vs-SMS next.
            _click_text(page, SMS_TEXT, "SMS delivery",
                        timeout_ms=4000)
            page.wait_for_timeout(1500)
        # 4. request the code when a send button is showing, then prove
        # we're on code entry BEFORE waiting (never burn 150s blind).
        mark = sms.latest_rowid()
        if _click_text(page, r"send code|resend", "send code",
                       timeout_ms=5000):
            mark = sms.latest_rowid()  # codes arrive after the request
            page.wait_for_timeout(2000)
        code_box = page.locator('input[autocomplete="one-time-code"], '
                                'input[inputmode="numeric"], '
                                'input[type="tel"]').first
        try:
            code_box.wait_for(state="visible", timeout=10000)
        except Exception:  # noqa: BLE001 — report the screen, don't wait blind
            raise ValueError("no code entry showing after SMS choice")
        # 5. enter the code from the Messages watcher
        try:
            code = sms.wait_for_code(mark, timeout_s=150)
        except TimeoutError as e:
            return {"status": "sms-timeout",
                    "detail": f"{e}; screen: {page_state(page)}"}
        _fill(page, ['input[autocomplete="one-time-code"]',
                     'input[inputmode="numeric"]',
                     'input[type="tel"]'],
              code, "code")
        page.locator('input[type="submit"], button[type="submit"]'
                     ).first.click()
        # 6. ride the redirect back to the app
        for _ in range(20):
            page.wait_for_timeout(3000)
            state, reason = http_engine.classify_refresh_page(
                page.url, page.content())
            if state == "ready":
                return {"status": "ok", "detail": "Okta+SMS login complete"}
            if state == "needs-you":
                return {"status": "flow-changed",
                        "detail": f"stuck post-code: {reason}; "
                                  f"{page_state(page)}"}
        return {"status": "flow-changed",
                "detail": f"no app content after code; {page_state(page)}"}
    except PermissionError as e:
        return {"status": "sms-blocked", "detail": str(e)}
    except ValueError as e:
        return {"status": "flow-changed",
                "detail": f"{e}; {page_state(page)}"}
