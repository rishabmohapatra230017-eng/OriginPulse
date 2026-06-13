# OriginPulse: Architecture & Reasoning

## The Problem

After each meeting, a coordinator manually reads transcripts, identifies action items, creates Jira tickets one by one, and posts a summary to the relevant Slack channel. This takes 30–45 minutes per meeting. Action items are frequently missed, assigned to the wrong person, or forgotten entirely.

The goal was to automate this workflow end-to-end: transcript in, Jira tickets and Slack summary out — with enough reliability and transparency that a clinical or product team would trust it.

---

## Tool Selection

### Python

Python is the orchestration layer. It is easy to version, test, run in CI, and deploy to a scheduled job or event-driven runtime. A code-first implementation makes it possible to add validation rules, logging, retries, idempotency checks, and environment-specific configuration through normal software engineering practices — things that are difficult or impossible to express in no-code tools.

### Groq for Extraction

Groq is used for the extraction step because it provides very fast LLM inference and supports strict structured JSON outputs. Meeting transcripts are inherently ambiguous: they include interruptions, implied ownership, multi-part decisions, and relative due dates like "by Friday" or "end of day tomorrow." A rules-based parser would be brittle, require constant tuning, and still miss edge cases.

The script constrains the model with a strict system prompt and a `json_schema` response format (`additionalProperties: false`). This makes the output machine-readable and predictable before any API calls are made. The model is not free-form — it must return exactly the structure the downstream steps expect.

### Jira Cloud REST API

Jira is integrated through its REST API rather than a no-code connector because the workflow requires control over issue type, labels, ADF descriptions, due dates, and assignee mapping. The API also makes it possible to add idempotency checks, retry logic, and partial failure recovery — none of which are easy in tools like Zapier or Make when the workflow gets complex.

### Slack Block Kit

Slack is used for the team-facing summary. Block Kit is chosen over plain text because it produces a structured, scannable message with a meeting summary, clickable Jira ticket links, assignees, and due dates in a single channel post. The script supports both bot token and incoming webhook auth so it works in any Slack app configuration.

---

## How Ambiguity Is Handled

### Relative Due Dates

The script builds a `DATE_CONTEXT` block every time it runs — a short calendar showing today's date, tomorrow, and the names of the next ten days mapped to ISO dates. This block is injected into every extraction request alongside the transcript. When the model sees "by Friday," it can look up the upcoming Friday from the context and return `2026-06-13` rather than an unparseable string.

### Missing Assignees and Due Dates

The system prompt instructs the model to use `"Unassigned"` when ownership is unclear and `"TBD"` when the due date cannot be inferred. These are not silent gaps — they are explicit values that downstream systems can act on. Unassigned items receive a `needs-triage` label in Jira so they surface in triage queues rather than disappearing.

### Post-Extraction Validation

After the LLM responds, every action item is normalized before Jira is called. Empty strings become safe defaults. Items with no task description are logged and skipped. This layer ensures that a degraded LLM response — one that technically parses as valid JSON but contains empty fields — does not create broken Jira tickets.

### Assumptions Made

- The meeting transcript is in plain text or Markdown. If audio or video transcription is needed, that would be a pre-processing step (Whisper, AssemblyAI, etc.).
- First names in the transcript (Sarah, Alex, Jamie) are sufficient for display. Mapping to Jira account IDs is supported via `JIRA_ASSIGNEE_MAP_JSON` but not required.
- The meeting date is known at run time. The script defaults to today if not provided.
- A single meeting produces a single workflow run. Multi-meeting batches would need a queue and idempotency keys.

---

## Failure Handling

The workflow touches three external services (Groq, Jira, Slack) in sequence. Each has different failure modes, so they are handled independently.

**Groq failure** — if the request times out, the API returns an error, or the response is not valid JSON, the script stops before creating any Jira tickets. There is no partial result to clean up.

**Jira failure** — if one ticket fails (validation error, rate limit, network timeout), the script logs it and continues with the remaining action items. A single bad payload does not block the entire meeting workflow. All successfully created ticket URLs are logged so nothing is lost even if the run is incomplete.

**Slack failure** — if Slack fails after Jira tickets have already been created, the ticket URLs are still in the logs. In production, this would be paired with a workflow state record so a retry can post the Slack message without recreating Jira tickets.

**Pre-flight validation** — before any live API call is made, the script checks that all required credentials are present and non-placeholder. A missing Slack token will abort the run before a single Jira ticket is created, preventing the partial-success state where tickets exist but no one is notified.

All HTTP calls use explicit timeouts (30–60 seconds) and `raise_for_status()` so authentication errors, rate limits, and server failures are surfaced immediately with clear log messages.

---

## What I Would Improve Given More Time

**Idempotency** is the most important missing piece. Right now, running the script twice on the same transcript creates duplicate Jira tickets. The fix is to generate a deterministic external reference for each action item (a hash of the meeting ID + task text), set it on the Jira issue, and search for existing issues with that reference before creating new ones.

**Identity resolution** — the script displays names from the transcript but only maps them to Jira account IDs when `JIRA_ASSIGNEE_MAP_JSON` is populated. In production, this would be connected to an HR directory or identity service so assignments are automatic.

**Transcript source connectors** — currently the script reads local files. In a production deployment, it would pull transcripts directly from Zoom, Gong, Google Meet, or a meeting-notes system via webhook or polling.

**Human approval** — for high-stakes meetings (patient safety decisions, partner commitments), a lightweight approval screen before Jira ticket creation would prevent automated errors from propagating into real project boards.

**Automated tests** — the workflow has clear seams (Groq response → normalization → Jira payload → Slack blocks) that are well-suited for unit tests with mocked API responses. These would catch regressions if the Groq schema, Jira API version, or Slack Block Kit format changes.

**Deployment** — the script is currently run locally. The natural next step is an AWS Lambda function or Cloud Run job triggered by a webhook when a meeting recording is processed. The script's single-file, argument-based design makes it straightforward to containerize.

**Observability** — centralized logs, extraction accuracy metrics, Jira creation failure rate, Slack notification failure rate, and manual correction rate (how often a human edits an auto-created ticket) would make it possible to monitor and improve the system over time.

**Schema extension** — the extraction schema could be enriched with a `priority` field (urgent / normal), a `source_quote` field (the exact transcript sentence that generated the action item, for auditability), a `confidence` score for low-certainty items, and a `clinical_category` tag relevant to Origin Medical's domain.

---

## Why Not No-Code?

Zapier, Make, and similar tools are appropriate for simple trigger-action flows. This workflow is not that. It requires:

- LLM extraction with a structured schema and fallback handling
- Relative date resolution with meeting-date anchoring
- Per-item failure isolation across seven or more Jira API calls
- Assignee identity mapping with a triage path for unknowns
- Dual Slack auth paths (bot token or webhook)
- Pre-flight validation to prevent partial results

These requirements are easier to express, test, and maintain in code. The result is also more auditable: every decision the system makes is visible in logs, and every API call is traceable to a specific line of the script.

---

*This solution is intentionally kept small and demonstrable. The architecture is designed so that the path from local script to production workflow is incremental and each step adds operational value without requiring a full rewrite.*
