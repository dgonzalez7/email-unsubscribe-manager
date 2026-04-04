"""
Component 4: Unsubscribe Executor

Reads Blacklist entries from Notion where Unsubscribed = false, executes
one-click unsubscribe POST requests, updates Notion with results, and
posts a Slack summary.

Scheduled: Weekly (e.g. Mondays at 2:00 AM) via Windows Task Scheduler.
"""

import json
import os
import sys
import time

import requests

# ── Windows UTF-8 fix ────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"

DB_BLACKLIST = "52a7a921-b46f-44f5-bfa6-a08ba38ab440"

MAX_RETRIES = 3
UNSUBSCRIBE_TIMEOUT = 30
UNSUBSCRIBE_MAX_REDIRECTS = 5


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    path = os.path.join(SCRIPT_DIR, "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Notion helpers ────────────────────────────────────────────────────────────

def notion_headers(api_token: str) -> dict:
    return {
        "Authorization": f"Bearer {api_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_request(method: str, url: str, headers: dict, **kwargs) -> requests.Response:
    """Make a Notion API request with exponential backoff on 429."""
    delay = 1
    for attempt in range(5):
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", delay))
            print(f"[WARN] Notion rate limit hit; waiting {retry_after}s", file=sys.stderr)
            time.sleep(retry_after)
            delay = min(delay * 2, 60)
            continue
        return resp
    return resp


def get_text(prop: dict) -> str:
    parts = prop.get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_title(prop: dict) -> str:
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_email(prop: dict) -> str:
    return prop.get("email") or ""


def get_url(prop: dict) -> str:
    return prop.get("url") or ""


def get_checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox", False))


def get_number(prop: dict) -> int:
    val = prop.get("number")
    return int(val) if val is not None else 0


# ── Query Blacklist ───────────────────────────────────────────────────────────

def query_unsubscribed_false(headers: dict) -> list[dict]:
    """Return all Blacklist pages where Unsubscribed = false. Handles pagination."""
    url = f"{NOTION_BASE}/databases/{DB_BLACKLIST}/query"
    body = {
        "filter": {
            "property": "Unsubscribed",
            "checkbox": {"equals": False},
        }
    }

    results = []
    cursor = None

    while True:
        payload = dict(body)
        if cursor:
            payload["start_cursor"] = cursor

        resp = notion_request("POST", url, headers, json=payload)
        if resp.status_code != 200:
            print(f"[ERROR] Failed to query Blacklist: "
                  f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
            break

        data = resp.json()
        batch = data.get("results", [])
        results.extend(batch)
        print(f"[INFO] Fetched {len(batch)} entries (total so far: {len(results)})",
              file=sys.stderr)

        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break

    return results


def parse_blacklist_entry(page: dict) -> dict:
    props = page.get("properties", {})
    return {
        "page_id":         page["id"],
        "sender":          get_title(props.get("Sender", {})),
        "sender_domain":   get_text(props.get("Sender Domain", {})),
        "sender_email":    get_email(props.get("Sender Email", {})),
        "unsubscribe_url": get_url(props.get("Unsubscribe URL", {})),
        "one_click":       get_checkbox(props.get("One-Click", {})),
        "retry_count":     get_number(props.get("Retry Count", {})),
    }


# ── Notion updates ────────────────────────────────────────────────────────────

def mark_unsubscribed(page_id: str, headers: dict) -> bool:
    """Set Unsubscribed = true on a Blacklist page."""
    url = f"{NOTION_BASE}/pages/{page_id}"
    resp = notion_request("PATCH", url, headers,
                          json={"properties": {"Unsubscribed": {"checkbox": True}}})
    if resp.status_code != 200:
        print(f"[ERROR] Failed to mark page {page_id} as unsubscribed: "
              f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return False
    return True


def increment_retry_count(page_id: str, current_count: int, headers: dict) -> bool:
    """Increment Retry Count on a Blacklist page."""
    url = f"{NOTION_BASE}/pages/{page_id}"
    new_count = current_count + 1
    resp = notion_request("PATCH", url, headers,
                          json={"properties": {"Retry Count": {"number": new_count}}})
    if resp.status_code != 200:
        print(f"[ERROR] Failed to update Retry Count for page {page_id}: "
              f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return False
    return True


# ── Unsubscribe POST ──────────────────────────────────────────────────────────

def do_unsubscribe_post(url: str) -> tuple[bool, str]:
    """
    Send a one-click unsubscribe POST request.
    Returns (success: bool, detail: str).
    """
    try:
        session = requests.Session()
        session.max_redirects = UNSUBSCRIBE_MAX_REDIRECTS
        resp = session.post(
            url,
            data="List-Unsubscribe=One-Click",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "EmailUnsubscribeManager/1.0",
            },
            timeout=UNSUBSCRIBE_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code < 300:
            return True, f"HTTP {resp.status_code}"
        else:
            return False, f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, "timeout after 30s"
    except requests.exceptions.TooManyRedirects:
        return False, f"too many redirects (>{UNSUBSCRIBE_MAX_REDIRECTS})"
    except requests.exceptions.ConnectionError as exc:
        return False, f"connection error: {exc}"
    except Exception as exc:
        return False, f"unexpected error: {exc}"


# ── Slack ─────────────────────────────────────────────────────────────────────

def post_slack(webhook_url: str, message: str) -> None:
    try:
        resp = requests.post(webhook_url, json={"text": message}, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] Slack webhook returned {resp.status_code}: {resp.text[:200]}",
                  file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] Slack post failed: {exc}", file=sys.stderr)


def build_slack_message(
    total: int,
    successes: list[tuple[str, str]],
    failures: list[tuple[str, str]],
    abandoned: list[str],
    manual: list[str],
    no_url: list[str],
) -> str:
    lines = [
        "*Email Unsubscribe Manager \u2014 Unsubscribe Executor*",
        f"\u2022 Total pending entries (Unsubscribed = false): *{total}*",
        f"\u2022 Successfully unsubscribed: *{len(successes)}*",
        f"\u2022 Failed attempts (retry next run): *{len(failures)}*",
        f"\u2022 Abandoned (\u2265 {MAX_RETRIES} retries): *{len(abandoned)}*",
        f"\u2022 Manual unsubscribe needed (non-one-click): *{len(manual)}*",
        f"\u2022 No URL available: *{len(no_url)}*",
    ]

    if successes:
        lines.append("\n*Successfully Unsubscribed:*")
        for name, detail in successes:
            lines.append(f"  \u2013 {name} ({detail})")

    if failures:
        lines.append("\n*Failed Attempts:*")
        for name, reason in failures:
            lines.append(f"  \u2013 {name}: {reason}")

    if abandoned:
        lines.append(f"\n*Abandoned (\u2265 3 failed attempts):*")
        for name in abandoned:
            lines.append(f"  \u2013 {name}")

    if manual:
        lines.append("\n*Needs Manual Unsubscribe:*")
        for name in manual:
            lines.append(f"  \u2013 {name}")

    if no_url:
        lines.append("\n*No Unsubscribe URL:*")
        for name in no_url:
            lines.append(f"  \u2013 {name}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    api_token = cfg["notion"]["api_token"]
    webhook_url = cfg["slack"]["webhook_url"]
    headers = notion_headers(api_token)

    # 1. Query Blacklist for entries not yet unsubscribed
    print("[INFO] Querying Blacklist for entries with Unsubscribed = false...", file=sys.stderr)
    pages = query_unsubscribed_false(headers)
    total = len(pages)
    print(f"[INFO] Found {total} pending entries", file=sys.stderr)

    if not pages:
        msg = "*Unsubscribe Executor:* No pending entries in Blacklist (all unsubscribed)."
        print(f"[INFO] {msg}", file=sys.stderr)
        post_slack(webhook_url, msg)
        return

    # 2. Categorize and process
    successes: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []
    abandoned: list[str] = []
    manual: list[str] = []
    no_url: list[str] = []

    for page in pages:
        entry = parse_blacklist_entry(page)
        name = entry["sender"] or entry["sender_domain"] or entry["page_id"]
        retry_count = entry["retry_count"]
        url = entry["unsubscribe_url"]
        one_click = entry["one_click"]

        print(f"[INFO] Entry: {name!r}  one_click={one_click}  "
              f"retry_count={retry_count}  url={'yes' if url else 'no'}",
              file=sys.stderr)

        # Skip: abandoned after too many retries
        if retry_count >= MAX_RETRIES:
            print(f"  -> Abandoned after {retry_count} attempts", file=sys.stderr)
            abandoned.append(name)
            continue

        # Skip: no URL
        if not url:
            print(f"  -> No unsubscribe URL", file=sys.stderr)
            no_url.append(name)
            continue

        # Skip: not one-click
        if not one_click:
            print(f"  -> Manual unsubscribe needed (One-Click = false)", file=sys.stderr)
            manual.append(name)
            continue

        # Process: send one-click unsubscribe POST
        print(f"  -> POSTing to {url}", file=sys.stderr)
        success, detail = do_unsubscribe_post(url)

        if success:
            print(f"  -> Success: {detail}", file=sys.stderr)
            try:
                mark_unsubscribed(entry["page_id"], headers)
            except Exception as exc:
                print(f"  [ERROR] Failed to update Notion for {name}: {exc}", file=sys.stderr)
            successes.append((name, detail))
        else:
            print(f"  -> Failed: {detail}", file=sys.stderr)
            try:
                increment_retry_count(entry["page_id"], retry_count, headers)
            except Exception as exc:
                print(f"  [ERROR] Failed to increment retry count for {name}: {exc}",
                      file=sys.stderr)
            failures.append((name, detail))

    print(f"[INFO] Done. Success={len(successes)}  Failed={len(failures)}  "
          f"Abandoned={len(abandoned)}  Manual={len(manual)}  NoURL={len(no_url)}",
          file=sys.stderr)

    # 3. Post Slack summary
    message = build_slack_message(total, successes, failures, abandoned, manual, no_url)
    post_slack(webhook_url, message)
    print("[INFO] Slack summary posted", file=sys.stderr)


if __name__ == "__main__":
    main()
