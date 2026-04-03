"""
scan_unsubscribe.py — Scan IMAP folders for List-Unsubscribe headers.

Outputs a JSON array to stdout and writes scan_results.json.
All diagnostic output goes to stderr so stdout stays clean JSON.
"""

import imaplib
import email
import email.message
import email.utils
import json
import re
import sys
import os
from datetime import datetime, timedelta, timezone
from email.header import decode_header

# ── Windows UTF-8 fix ────────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── Config ───────────────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(SCRIPT_DIR, "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Header decoding ───────────────────────────────────────────────────────────

def decode_header_value(value: str | bytes | None) -> str:
    """
    Fully decode a MIME-encoded header value (handles QP, Base64, plain text,
    and multi-part encoded words).  This is the fix for the Torchy's Tacos bug
    in test_imap.py where List-Unsubscribe was parsed before decoding.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    parts = decode_header(value)
    result = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            result.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(chunk)
    return "".join(result)


# ── From header parsing ───────────────────────────────────────────────────────

def parse_from(raw_from: str) -> tuple[str, str, str]:
    """Return (display_name, email_address, domain)."""
    decoded = decode_header_value(raw_from)
    name, addr = email.utils.parseaddr(decoded)
    addr = addr.lower().strip()
    domain = addr.split("@", 1)[1] if "@" in addr else addr
    return name.strip(), addr, domain


# ── List-Unsubscribe parsing ──────────────────────────────────────────────────

def parse_list_unsubscribe(raw_header: str | None) -> dict:
    """
    Decode the header value FIRST, then extract HTTP URL and mailto address.

    RFC 2369 allows comma-separated angle-bracket entries, e.g.:
        <https://example.com/unsub>, <mailto:list@example.com>

    Also handles bare URLs (no angle brackets) as a fallback.
    Returns {"http_url": str|None, "mailto": str|None}.
    """
    if not raw_header:
        return {"http_url": None, "mailto": None}

    # CRITICAL: decode MIME encoding before parsing URLs
    decoded = decode_header_value(raw_header)

    http_url = None
    mailto = None

    # Primary: angle-bracket-enclosed entries per RFC 2369
    entries = re.findall(r"<([^>]+)>", decoded)
    for entry in entries:
        entry = entry.strip()
        if (entry.startswith("https://") or entry.startswith("http://")) and http_url is None:
            http_url = entry
        elif entry.startswith("mailto:") and mailto is None:
            mailto = entry

    # Fallback: bare URLs not wrapped in angle brackets
    if http_url is None:
        for segment in re.split(r",\s*", decoded):
            segment = segment.strip().strip("<>")
            if segment.startswith("https://") or segment.startswith("http://"):
                http_url = segment
                break

    return {"http_url": http_url, "mailto": mailto}


# ── IMAP date helpers ─────────────────────────────────────────────────────────

def imap_since_date(hours_ago: int) -> str:
    """Return an IMAP SINCE date string (DD-Mon-YYYY) for `hours_ago` hours back."""
    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return since_dt.strftime("%d-%b-%Y")


def message_date(msg: email.message.Message) -> datetime:
    """Parse the Date header into a timezone-aware datetime (UTC fallback)."""
    raw = msg.get("Date", "")
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


# ── Folder scanning ───────────────────────────────────────────────────────────

def scan_folder(imap: imaplib.IMAP4_SSL, folder_name: str, since_hours: int) -> list[dict]:
    """
    Scan a single IMAP folder for emails with List-Unsubscribe headers.
    Returns a list of result dicts.  Errors are printed to stderr.
    """
    results = []

    try:
        status, data = imap.select(folder_name, readonly=True)
    except Exception as exc:
        print(f"[WARN] Could not select '{folder_name}': {exc}", file=sys.stderr)
        return results

    if status != "OK":
        print(f"[WARN] Could not select '{folder_name}': {data}", file=sys.stderr)
        return results

    since_str = imap_since_date(since_hours)
    try:
        status, data = imap.search(None, f'SINCE "{since_str}"')
    except Exception as exc:
        print(f"[WARN] Search failed in '{folder_name}': {exc}", file=sys.stderr)
        return results

    if status != "OK" or not data or not data[0]:
        print(f"[INFO] No messages found in '{folder_name}' since {since_str}", file=sys.stderr)
        return results

    msg_ids = data[0].split()
    print(f"[INFO] '{folder_name}': {len(msg_ids)} messages since {since_str}", file=sys.stderr)

    for msg_id in msg_ids:
        try:
            status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[HEADER])")
        except Exception as exc:
            print(f"[WARN] fetch error on msg {msg_id} in '{folder_name}': {exc}", file=sys.stderr)
            continue

        if status != "OK":
            continue

        raw_header = None
        for part in msg_data:
            if isinstance(part, tuple):
                raw_header = part[1]
                break

        if raw_header is None:
            continue

        try:
            msg = email.message_from_bytes(raw_header)
        except Exception as exc:
            print(f"[WARN] parse error on msg {msg_id}: {exc}", file=sys.stderr)
            continue

        raw_unsub = msg.get("List-Unsubscribe")
        if not raw_unsub:
            continue  # skip emails without List-Unsubscribe

        raw_from = msg.get("From", "")
        raw_subject = msg.get("Subject", "")
        raw_unsub_post = msg.get("List-Unsubscribe-Post", "")

        sender_name, sender_email, sender_domain = parse_from(raw_from)
        subject = decode_header_value(raw_subject)
        unsub = parse_list_unsubscribe(raw_unsub)
        one_click = "List-Unsubscribe=One-Click" in decode_header_value(raw_unsub_post)
        date = message_date(msg)

        results.append({
            "sender_name": sender_name,
            "sender_email": sender_email,
            "sender_domain": sender_domain,
            "subject_sample": subject,
            "source_folder": folder_name,
            "unsubscribe_url": unsub["http_url"],
            "unsubscribe_mailto": unsub["mailto"],
            "one_click": one_click,
            "_date": date,          # internal; stripped before output
        })

    return results


# ── Deduplication ─────────────────────────────────────────────────────────────

def deduplicate_by_domain(results: list[dict]) -> list[dict]:
    """Keep only the most recent email per sender domain."""
    best: dict[str, dict] = {}
    for r in results:
        domain = r["sender_domain"]
        if domain not in best or r["_date"] > best[domain]["_date"]:
            best[domain] = r
    # Sort output: most recent first, then alphabetically by domain
    deduped = sorted(best.values(), key=lambda r: (-r["_date"].timestamp(), r["sender_domain"]))
    for r in deduped:
        del r["_date"]
    return deduped


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg = load_config()
    imap_cfg = cfg["imap"]
    folders_cfg = cfg.get("folders", {})
    defaults = cfg.get("defaults", {})

    since_hours = int(defaults.get("since_hours", 24))
    trash_since_hours = int(defaults.get("trash_since_hours", 24))

    inbox_folder = folders_cfg.get("inbox", "INBOX")
    junk_folder = folders_cfg.get("junk", "Junk")
    trash_folder = folders_cfg.get("trash", "Trash")

    print(f"[INFO] Connecting to {imap_cfg['host']}:{imap_cfg['port']} "
          f"as {imap_cfg['username']}", file=sys.stderr)

    try:
        imap = imaplib.IMAP4_SSL(imap_cfg["host"], int(imap_cfg["port"]))
        imap.login(imap_cfg["username"], imap_cfg["password"])
    except Exception as exc:
        print(f"[ERROR] IMAP connection/login failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("[INFO] Login successful", file=sys.stderr)

    all_results: list[dict] = []

    try:
        # Inbox and Junk share the same time window
        for folder in (inbox_folder, junk_folder):
            all_results.extend(scan_folder(imap, folder, since_hours))

        # Trash may have its own (often longer) window
        all_results.extend(scan_folder(imap, trash_folder, trash_since_hours))
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    print(f"[INFO] Total emails with List-Unsubscribe (before dedup): {len(all_results)}",
          file=sys.stderr)

    final = deduplicate_by_domain(all_results)

    print(f"[INFO] Unique sender domains after dedup: {len(final)}", file=sys.stderr)

    output_json = json.dumps(final, ensure_ascii=False, indent=2)

    # Write to stdout (the clean JSON channel)
    print(output_json)

    # Also persist to scan_results.json
    out_path = os.path.join(SCRIPT_DIR, "scan_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output_json)
        f.write("\n")
    print(f"[INFO] Results written to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
