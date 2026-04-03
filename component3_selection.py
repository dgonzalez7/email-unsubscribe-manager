"""
Component 3: Email Selection Processor

Reads triage decisions (Keep/Unsubscribe/Skip) from the Notion Review Queue,
routes entries to Whitelist or Blacklist accordingly, and posts a Slack summary.

Triggered: Manually after user completes triage in Notion.
"""
