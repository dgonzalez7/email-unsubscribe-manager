"""
Component 2: Review Queue Builder

Reads scan_results.json from Component 1, deduplicates sender domains
against Notion databases (Review Queue, Whitelist, Blacklist), creates
new entries in the Review Queue, and posts a Slack summary.

Scheduled: Nightly at 1:20 AM via Windows Task Scheduler.
"""

import json
import os
import sys
import time
from datetime import date

import requests

# ── Windows UTF-8 fix ────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

NOTION_VERSION = "2022-06-28"
NOTION_BASE = "https://api.notion.com/v1"

DB_REVIEW_QUEUE = "9e26e2f7-47f4-4849-bafe-09edb7f868ea"
DB_WHITELIST    = "19609548-d7b4-434f-832e-7841a2177b5a"
DB_BLACKLIST    = "52a7a921-b46f-44f5-bfa6-a08ba38ab440"

ALL_DBS = {
    "Review Queue": DB_REVIEW_QUEUE,
    "Whitelist":    DB_WHITELIST,
    "Blacklist":    DB_BLACKLIST,
}


# ── Config ───────────────────────────────────────────────────────────────────

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
    """Make a Notion API request with simple exponential backoff on 429."""
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
    return resp  # return last response after exhausting retries


def domain_in_db(domain: str, db_id: str, headers: dict) -> bool:
    """Return True if the domain exists in the given Notion database."""
    url = f"{NOTION_BASE}/databases/{db_id}/query"
    body = {
        "filter": {
            "property": "Sender Domain",
            "rich_text": {"equals": domain},
        }
    }
    resp = notion_request("POST", url, headers, json=body)
    if resp.status_code != 200:
        print(f"[WARN] Notion query failed (db={db_id}, domain={domain}): "
              f"{resp.status_code} {resp.text[:200]}", file=sys.stderr)
        return False
    data = resp.json()
    return len(data.get("results", [])) > 0


def find_domain_in_any_db(domain: str, headers: dict) -> str | None:
    """Return the name of the first database that contains the domain, or None."""
    for db_name, db_id in ALL_DBS.items():
        if domain_in_db(domain, db_id, headers):
            return db_name
    return None


def create_review_queue_entry(entry: dict, headers: dict) -> bool:
    """
    Create a page in the Review Queue database.
    Returns True on success, False on failure.
    """
    url = f"{NOTION_BASE}/pages"
    today = date.today().isoformat()

    properties: dict = {
        "Sender": {
            "title": [{"text": {"content": entry["sender_name"] or ""}}]
        },
        "Sender Domain": {
            "rich_text": [{"text": {"content": entry["sender_domain"]}}]
        },
        "Subject Sample": {
            "rich_text": [{"text": {"content": (entry.get("subject_sample") or "")[:2000]}}]
        },
        "One-Click": {
            "checkbox": bool(entry.get("one_click", False))
        },
        "Source Folder": {
            "select": {"name": entry.get("source_folder") or "INBOX"}
        },
        "Date Added": {
            "date": {"start": today}
        },
    }

    # Optional fields — only include if non-null
    if entry.get("sender_email"):
        properties["Sender Email"] = {"email": entry["sender_email"]}

    if entry.get("unsubscribe_url"):
        properties["Unsubscribe URL"] = {"url": entry["unsubscribe_url"]}

    body = {
        "parent": {"database_id": DB_REVIEW_QUEUE},
        "properties": properties,
    }

    resp = notion_request("POST", url, headers, json=body)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to create Review Queue entry for "
              f"{entry['sender_name']} ({entry['sender_domain']}): "
              f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return False
    return True


# ── Slack ─────────────────────────────────────────────────────────────────────

def post_slack(webhook_url: str, message: str) -> None:
    try:
        resp = requests.post(
            webhook_url,
            json={"text": message},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[WARN] Slack webhook returned {resp.status_code}: {resp.text[:200]}",
                  file=sys.stderr)
    except Exception as exc:
        print(f"[WARN] Slack post failed: {exc}", file=sys.stderr)


def build_slack_message(
    total: int,
    known: int,
    created: int,
    failed: int,
    new_entries: list[dict],
) -> str:
    lines = [
        "*Email Unsubscribe Manager — Review Queue Builder*",
        f"• Total sender domains scanned: *{total}*",
        f"• Already known (Review Queue / Whitelist / Blacklist): *{known}*",
        f"• New entries created: *{created}*",
    ]
    if failed:
        lines.append(f"• Failed to create: *{failed}*")
    if new_entries:
        lines.append("\n*New senders added to Review Queue:*")
        for e in new_entries:
            lines.append(f"  – {e['sender_name']} (`{e['sender_domain']}`)")
    else:
        lines.append("\n_No new senders found._")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    api_token = cfg["notion"]["api_token"]
    webhook_url = cfg["slack"]["webhook_url"]
    headers = notion_headers(api_token)

    # 1. Load scan_results.json
    scan_path = os.path.join(SCRIPT_DIR, "scan_results.json")
    try:
        with open(scan_path, encoding="utf-8") as f:
            scan_results: list[dict] = json.load(f)
    except FileNotFoundError:
        msg = f"*Review Queue Builder error:* `scan_results.json` not found at `{scan_path}`"
        print(f"[ERROR] {msg}", file=sys.stderr)
        post_slack(webhook_url, msg)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        msg = f"*Review Queue Builder error:* `scan_results.json` is invalid JSON: {exc}"
        print(f"[ERROR] {msg}", file=sys.stderr)
        post_slack(webhook_url, msg)
        sys.exit(1)

    total = len(scan_results)
    print(f"[INFO] Loaded {total} entries from scan_results.json", file=sys.stderr)

    # 2. Deduplicate against Notion databases
    known_count = 0
    new_entries: list[dict] = []

    for entry in scan_results:
        domain = entry["sender_domain"]
        print(f"[INFO] Checking domain: {domain}", file=sys.stderr, end=" — ")
        found_in = find_domain_in_any_db(domain, headers)
        if found_in:
            print(f"found in {found_in}", file=sys.stderr)
            known_count += 1
        else:
            print("new", file=sys.stderr)
            new_entries.append(entry)

    print(f"[INFO] Known: {known_count}  |  New: {len(new_entries)}", file=sys.stderr)

    # 3. Create Review Queue entries for new senders
    created = 0
    failed = 0
    created_entries: list[dict] = []

    for entry in new_entries:
        print(f"[INFO] Creating Review Queue entry: "
              f"{entry['sender_name']} ({entry['sender_domain']})", file=sys.stderr)
        ok = create_review_queue_entry(entry, headers)
        if ok:
            created += 1
            created_entries.append(entry)
        else:
            failed += 1

    # 4. Post Slack summary
    message = build_slack_message(total, known_count, created, failed, created_entries)
    post_slack(webhook_url, message)
    print("[INFO] Slack summary posted", file=sys.stderr)

    print(f"[INFO] Done. Total={total}  Known={known_count}  "
          f"Created={created}  Failed={failed}", file=sys.stderr)


if __name__ == "__main__":
    main()
