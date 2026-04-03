"""
Component 2: Review Queue Builder

Reads scan_results.json from Component 1, deduplicates sender domains
against Notion databases (Review Queue, Whitelist, Blacklist), creates
new entries in the Review Queue, and posts a Slack summary.

Scheduled: Nightly at 1:20 AM via Windows Task Scheduler.
"""
