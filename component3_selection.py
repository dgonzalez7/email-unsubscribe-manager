"""
Component 3: Email Selection Processor

Reads triage decisions (Keep/Unsubscribe/Skip) from the Notion Review Queue,
routes entries to Whitelist or Blacklist accordingly, archives processed entries,
and posts a Slack summary.

Triggered: Manually after user completes triage in Notion.
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
    return resp  # return last response after exhausting retries


def get_text(prop: dict) -> str:
    """Extract plain text from a rich_text property."""
    parts = prop.get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_title(prop: dict) -> str:
    """Extract plain text from a title property."""
    parts = prop.get("title", [])
    return "".join(p.get("plain_text", "") for p in parts)


def get_select(prop: dict) -> str:
    """Extract the name from a select property."""
    sel = prop.get("select")
    return sel["name"] if sel else ""


def get_email(prop: dict) -> str:
    return prop.get("email") or ""


def get_url(prop: dict) -> str:
    return prop.get("url") or ""


def get_checkbox(prop: dict) -> bool:
    return bool(prop.get("checkbox", False))


# ── Query Review Queue ────────────────────────────────────────────────────────

def query_triaged_entries(headers: dict) -> list[dict]:
    """
    Return all Review Queue pages where Status is Keep, Unsubscribe, or Skip.
    Handles pagination automatically.
    """
    url = f"{NOTION_BASE}/databases/{DB_REVIEW_QUEUE}/query"
    body = {
        "filter": {
            "or": [
                {"property": "Status", "select": {"equals": "Keep"}},
                {"property": "Status", "select": {"equals": "Unsubscribe"}},
                {"property": "Status", "select": {"equals": "Skip"}},
            ]
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
            print(f"[ERROR] Failed to query Review Queue: "
                  f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
            break

        data = resp.json()
        results.extend(data.get("results", []))
        print(f"[INFO] Fetched {len(data.get('results', []))} entries "
              f"(total so far: {len(results)})", file=sys.stderr)

        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break

    return results


def parse_entry(page: dict) -> dict:
    """Extract relevant fields from a Notion page object."""
    props = page.get("properties", {})
    return {
        "page_id":       page["id"],
        "sender":        get_title(props.get("Sender", {})),
        "sender_email":  get_email(props.get("Sender Email", {})),
        "sender_domain": get_text(props.get("Sender Domain", {})),
        "subject_sample":get_text(props.get("Subject Sample", {})),
        "unsubscribe_url":get_url(props.get("Unsubscribe URL", {})),
        "one_click":     get_checkbox(props.get("One-Click", {})),
        "source_folder": get_select(props.get("Source Folder", {})),
        "status":        get_select(props.get("Status", {})),
        "date_added":    (props.get("Date Added", {}).get("date") or {}).get("start", ""),
    }


# ── Routing ───────────────────────────────────────────────────────────────────

def create_whitelist_entry(entry: dict, headers: dict) -> bool:
    """Create a page in the Whitelist database. Returns True on success."""
    url = f"{NOTION_BASE}/pages"
    today = date.today().isoformat()

    properties: dict = {
        "Sender": {
            "title": [{"text": {"content": entry["sender"] or ""}}]
        },
        "Sender Domain": {
            "rich_text": [{"text": {"content": entry["sender_domain"]}}]
        },
        "Date Added": {
            "date": {"start": today}
        },
    }
    if entry["sender_email"]:
        properties["Sender Email"] = {"email": entry["sender_email"]}

    body = {
        "parent": {"database_id": DB_WHITELIST},
        "properties": properties,
    }

    resp = notion_request("POST", url, headers, json=body)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to create Whitelist entry for {entry['sender']}: "
              f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return False
    return True


def create_blacklist_entry(entry: dict, headers: dict) -> bool:
    """Create a page in the Blacklist database. Returns True on success."""
    url = f"{NOTION_BASE}/pages"
    today = date.today().isoformat()

    properties: dict = {
        "Sender": {
            "title": [{"text": {"content": entry["sender"] or ""}}]
        },
        "Sender Domain": {
            "rich_text": [{"text": {"content": entry["sender_domain"]}}]
        },
        "One-Click": {
            "checkbox": entry["one_click"]
        },
        "Date Added": {
            "date": {"start": today}
        },
        "Unsubscribed": {
            "checkbox": False
        },
    }
    if entry["sender_email"]:
        properties["Sender Email"] = {"email": entry["sender_email"]}
    if entry["unsubscribe_url"]:
        properties["Unsubscribe URL"] = {"url": entry["unsubscribe_url"]}

    body = {
        "parent": {"database_id": DB_BLACKLIST},
        "properties": properties,
    }

    resp = notion_request("POST", url, headers, json=body)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Failed to create Blacklist entry for {entry['sender']}: "
              f"{resp.status_code} {resp.text[:300]}", file=sys.stderr)
        return False
    return True


def archive_page(page_id: str, headers: dict) -> bool:
    """Archive a Notion page. Returns True on success."""
    url = f"{NOTION_BASE}/pages/{page_id}"
    resp = notion_request("PATCH", url, headers, json={"archived": True})
    if resp.status_code != 200:
        print(f"[ERROR] Failed to archive page {page_id}: "
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
    kept: list[str],
    unsubscribed: list[str],
    skipped: list[str],
    failed: int,
) -> str:
    lines = [
        "*Email Unsubscribe Manager — Selection Processor*",
        f"• Total entries processed: *{total}*",
        f"• Keep → Whitelist: *{len(kept)}*",
        f"• Unsubscribe → Blacklist: *{len(unsubscribed)}*",
        f"• Skip → archived: *{len(skipped)}*",
    ]
    if failed:
        lines.append(f"• Errors (routing/archive failed): *{failed}*")

    if kept:
        lines.append("\n*Kept (Whitelist):*")
        for name in kept:
            lines.append(f"  – {name}")

    if unsubscribed:
        lines.append("\n*Unsubscribe (Blacklist):*")
        for name in unsubscribed:
            lines.append(f"  – {name}")

    if skipped:
        lines.append("\n*Skipped:*")
        for name in skipped:
            lines.append(f"  – {name}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    api_token = cfg["notion"]["api_token"]
    webhook_url = cfg["slack"]["webhook_url"]
    headers = notion_headers(api_token)

    # 1. Query Review Queue for triaged entries
    print("[INFO] Querying Review Queue for triaged entries...", file=sys.stderr)
    pages = query_triaged_entries(headers)
    print(f"[INFO] Found {len(pages)} triaged entries", file=sys.stderr)

    if not pages:
        msg = "*Email Selection Processor:* No triaged entries found in Review Queue."
        print(f"[INFO] {msg}", file=sys.stderr)
        post_slack(webhook_url, msg)
        return

    # 2. Process each entry
    kept: list[str] = []
    unsubscribed: list[str] = []
    skipped: list[str] = []
    failed = 0

    for page in pages:
        entry = parse_entry(page)
        status = entry["status"]
        name = entry["sender"] or entry["sender_domain"] or entry["page_id"]
        print(f"[INFO] Processing [{status}]: {name}", file=sys.stderr)

        routed_ok = True

        try:
            if status == "Keep":
                routed_ok = create_whitelist_entry(entry, headers)
                if routed_ok:
                    kept.append(name)

            elif status == "Unsubscribe":
                routed_ok = create_blacklist_entry(entry, headers)
                if routed_ok:
                    unsubscribed.append(name)

            elif status == "Skip":
                skipped.append(name)
                # No routing needed — just archive below

            else:
                print(f"[WARN] Unknown status '{status}' for {name}, skipping", file=sys.stderr)
                continue

        except Exception as exc:
            print(f"[ERROR] Exception routing {name}: {exc}", file=sys.stderr)
            routed_ok = False

        if not routed_ok:
            failed += 1
            continue  # Don't archive if routing failed

        # 3. Archive the Review Queue entry
        archived = archive_page(entry["page_id"], headers)
        if not archived:
            print(f"[WARN] Routing succeeded but archive failed for {name}", file=sys.stderr)
            failed += 1

    total = len(kept) + len(unsubscribed) + len(skipped)
    print(f"[INFO] Done. Keep={len(kept)}  Unsubscribe={len(unsubscribed)}  "
          f"Skip={len(skipped)}  Errors={failed}", file=sys.stderr)

    # 4. Post Slack summary
    message = build_slack_message(total, kept, unsubscribed, skipped, failed)
    post_slack(webhook_url, message)
    print("[INFO] Slack summary posted", file=sys.stderr)


if __name__ == "__main__":
    main()
