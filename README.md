# email-unsubscribe-manager

Automated email unsubscribe management for Fidei/Roundcube email accounts. Scans IMAP folders for mailing list emails, routes them through a Notion-based triage workflow, and executes unsubscribe requests automatically.

## What it does

This system runs as four discrete components, each triggered on its own schedule:

1. **Component 1 — IMAP Scanner** (`component1_scan.py`): Connects to your IMAP server, scans Inbox, Junk, and Trash for emails containing `List-Unsubscribe` headers, deduplicates by sender domain, and writes results to `scan_results.json`.

2. **Component 2 — Review Queue Builder** (`component2_review.py`): Reads `scan_results.json`, checks sender domains against existing Notion databases (Review Queue, Whitelist, Blacklist), creates new entries in the Notion Review Queue for unknown senders, and posts a Slack summary.

3. **Component 3 — Selection Processor** (`component3_selection.py`): Reads triage decisions (Keep / Unsubscribe / Skip) you've made in Notion, routes entries to the Whitelist or Blacklist accordingly, and posts a Slack summary. Run this manually after completing triage in Notion.

4. **Component 4 — Unsubscribe Executor** (`component4_unsubscribe.py`): Reads Blacklist entries with unsubscribe URLs, executes RFC 8058 one-click POST requests to unsubscribe, logs results to the Notion Action Log, and posts a Slack summary.

## Setup

1. Copy the example config and fill in your credentials:

   ```
   cp config.json.example config.json
   ```

2. Edit `config.json` with your IMAP server details, Notion API token, and Slack webhook URL.

3. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

## Scheduling (Windows Task Scheduler)

| Component | Trigger |
|-----------|---------|
| Component 1 — IMAP Scanner | Nightly at 1:00 AM |
| Component 2 — Review Queue Builder | Nightly at 1:20 AM |
| Component 3 — Selection Processor | Manual (run after Notion triage) |
| Component 4 — Unsubscribe Executor | Weekly, Sunday at 3:00 AM |

## Dependencies

- **Notion** — used as the database layer for Review Queue, Whitelist, Blacklist, and Action Log
- **Slack** — receives summary notifications after each component runs
- **IMAP** — connects directly to your email server (stdlib `imaplib`, no third-party email library needed)

## Security

`config.json` is listed in `.gitignore` and must never be committed. It contains your IMAP password, Notion API token, and Slack webhook URL. Only `config.json.example` (with empty placeholder values) is tracked by git.
