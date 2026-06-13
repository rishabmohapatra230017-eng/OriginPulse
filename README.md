# OriginPulse — Post-Meeting Workflow Automation

> **Role Challenge Submission · Workflow Automation Engineer Intern · Origin Medical**  
> Prepared by **Rishab Mohapatra** · June 2026

---

## What This Does

Clinical and product teams at Origin Medical run multiple meetings every week. After each meeting, a coordinator manually reads transcripts, identifies action items, creates Jira tickets one-by-one, and posts a summary to Slack — a process that takes 30–45 minutes per meeting and is prone to missed or misassigned tasks.

**OriginPulse automates this end-to-end:**

```
Meeting transcript (.md / .txt)
        │
        ▼
  Groq LLM (structured extraction)
        │
        ├──► Jira Cloud REST API  →  One ticket per action item
        │
        └──► Slack Block Kit API  →  Formatted channel summary
```

A single command reads any transcript, intelligently extracts action items with assignees and due dates, creates real Jira tickets, and posts a rich Slack summary — all in under 30 seconds.

---

## Live Proof (Already Executed)

The automation has been run live against real APIs. Evidence is in `assets/proof/`.

| Output | Result |
|---|---|
| Jira tickets created | **ORIG-1 through ORIG-7** at `rishabmohapatra7.atlassian.net` |
| Slack message posted | OriginPulse workspace · `#originpulse-bot` channel · 01:43 AM |
| Extraction accuracy | 7 action items from 112-line transcript — all correctly assigned |

---

## Project Structure

```
OriginPulse/
├── automate_meeting.py          # Core automation (Groq + Jira + Slack)
├── slack_oauth_server.js        # Local Slack OAuth helper (Node/Express)
├── requirements.txt             # Python dependencies
├── package.json                 # Node dependencies
├── .env.example                 # Credential template
│
├── transcripts/
│   └── mock_meeting_transcript.md   # The meeting used as input
│
├── docs/
│   ├── architecture_writeup.md      # Approach, decisions, failure handling
│   └── Origin_Medical_Role_Challenge_Rishab_Mohapatra.pdf  # Submission PDF
│
├── assets/proof/
│   ├── jira_board.png           # Jira board screenshot (ORIG-1 to ORIG-7)
│   └── slack_message.png        # Slack Block Kit summary screenshot
│
└── scripts/
    ├── build_submission_pdf.py      # Builds the final submission PDF
    └── convert_proof_to_png.py     # Converts proof PDFs → PNG (PyMuPDF)
```

---

## The Meeting Input

The transcript (`transcripts/mock_meeting_transcript.md`) is a 112-line Origin Medical clinical pilot sync between **Sarah** (PM), **Alex** (Engineering), and **Jamie** (Clinical). It covers:

- A gestational-age normalization bug in the Westbridge scan ingestion pipeline
- Risk-banding thresholding behaviour and a cautious fallback guardrail
- Annotation coverage for abdominal-wall anomaly findings
- Category-level monitoring dashboard changes
- UI copy updates to soften clinical language in the image viewer
- Partner-facing communication and pilot metrics scoping

The conversation uses natural language throughout — relative due dates ("by Friday", "end of day tomorrow", "next Wednesday"), implied ownership, and multi-part decisions — making it a strong test case for LLM-based extraction.

---

## Stack & Why

| Component | Tool | Reason |
|---|---|---|
| **Extraction** | Groq `openai/gpt-oss-120b` | Fast inference, strict JSON schema support, handles ambiguity |
| **Ticket creation** | Jira Cloud REST API v3 | Direct control, ADF descriptions, label tagging, due dates |
| **Team notification** | Slack Block Kit (webhook or bot) | Rich formatting, clickable ticket links, channel-native |
| **Orchestration** | Python 3.12 | Testable, versionable, extensible, CI-deployable |
| **OAuth helper** | Node/Express | Lightweight local server for Slack app authorization |

No-code tools (Zapier, Make) were deliberately avoided — the workflow has enough conditional logic, API error handling, identity mapping, and validation that code-first is the right approach at this complexity level.

---

## Setup

**Prerequisites:** Python 3.10+, Node 18+ (for Slack OAuth only)

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy and fill in credentials
Copy-Item .env.example .env
# Edit .env with your Groq, Jira, and Slack credentials
```

### Environment Variables (`.env`)

```env
# Groq — get a free key at console.groq.com
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b        # or openai/gpt-oss-20b for rate-limit safety

# Jira Cloud
JIRA_BASE_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token         # Settings → Security → API tokens
JIRA_PROJECT_KEY=ORIG
JIRA_ISSUE_TYPE=Task

# Slack — use EITHER bot token + channel, OR an incoming webhook URL
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL_ID=C...
SLACK_WEBHOOK_URL=                    # alternative to bot token

# Runtime
MEETING_DATE=2026-06-11               # anchors relative due dates
DRY_RUN=true                          # set false to write to real APIs
```

---

## Running the Automation

### Safe test first (no external writes)

```powershell
python automate_meeting.py --transcript transcripts/mock_meeting_transcript.md --dry-run
```

This runs the full extraction pipeline and prints exactly what Jira tickets and Slack blocks would be created — without touching any APIs.

### Live run (creates real Jira tickets and posts to Slack)

```powershell
python automate_meeting.py \
  --transcript transcripts/mock_meeting_transcript.md \
  --meeting-date 2026-06-11 \
  --live
```

The `--live` flag overrides `DRY_RUN=true`. The script validates all credentials before creating any tickets — so it won't create partial results if Slack is misconfigured.

### Using your own transcript

Drop any `.md` or `.txt` meeting transcript in `transcripts/` and point to it:

```powershell
python automate_meeting.py --transcript transcripts/your_meeting.md --meeting-date 2026-06-13 --live
```

---

## How the Extraction Works

The script sends the transcript to Groq with a system prompt that enforces a strict JSON schema:

```json
{
  "summary": "One-paragraph executive summary of the meeting.",
  "action_items": [
    {
      "assignee": "Alex",
      "task": "Fix Westbridge gestational-age normalization bug and reprocess affected scans",
      "due_date": "2026-06-12"
    }
  ]
}
```

Key design decisions:
- **Relative date resolution** — the script builds a `DATE_CONTEXT` block (today, tomorrow, upcoming days by name) that it injects into every extraction request, so "by Friday" becomes `2026-06-13` deterministically.
- **Strict schema** — `additionalProperties: false` prevents hallucinated fields. If the model can't populate a field, it uses `"Unassigned"` or `"TBD"` rather than guessing.
- **Post-extraction validation** — every field is normalized after the LLM responds; malformed items are logged and skipped rather than crashing the workflow.

---

## Slack OAuth Setup (if needed)

If you have a Slack app with OAuth credentials rather than a raw bot token:

```powershell
# Add to .env:
# SLACK_CLIENT_ID=...
# SLACK_CLIENT_SECRET=...
# SLACK_REDIRECT_URI=http://localhost:3000/slack/oauth/callback

npm install
npm run slack:oauth
```

Open `http://localhost:3000/slack/install`, approve the app, and copy the printed `SLACK_BOT_TOKEN=xoxb-...` into `.env`.

---

## Build the Submission PDF

```powershell
# Optional: set your GitHub repo URL
$env:GITHUB_REPO_URL="https://github.com/yourusername/originpulse"

python scripts/build_submission_pdf.py
# → docs/Origin_Medical_Role_Challenge_Rishab_Mohapatra.pdf
```

To regenerate the proof images from live API data:

```powershell
python scripts/convert_proof_to_png.py
# Requires: pymupdf (pip install pymupdf) — already in requirements
```

---

## Failure Handling

| Failure | Behaviour |
|---|---|
| Groq returns empty/malformed JSON | Script stops — no Jira tickets created |
| A single Jira ticket fails (e.g. 400 validation) | Logged, skipped — remaining tickets continue |
| Slack post fails after tickets are created | Error logged with all created ticket URLs so nothing is lost |
| Missing required env var | Raises immediately with a clear message listing which vars are missing |
| Network timeout | HTTP timeouts on all calls (30–60 s); raises cleanly |

---

## What I'd Improve With More Time

1. **Idempotency** — store a meeting fingerprint per run; check Jira before creating tickets so re-running never creates duplicates
2. **Identity mapping** — connect first names to Jira account IDs via an HR directory or People API so assignees are set automatically
3. **Transcript source connectors** — pull directly from Zoom, Gong, Google Meet, or Notion instead of local files
4. **Human approval step** — surface extracted action items in a lightweight UI before committing to Jira
5. **Automated tests** — mock Groq, Jira, and Slack responses for unit and integration coverage
6. **Scheduled / event-driven** — deploy as an AWS Lambda or Cloud Run job triggered by a webhook when a meeting recording is processed
7. **Observability** — centralized logs, alerting on extraction accuracy, Jira creation failure rate

---

## Security Notes

- `.env` is listed in `.gitignore` and must never be committed
- Jira API tokens are scoped to the authenticated user's permissions
- The Slack OAuth helper only stores state tokens in memory; they expire after 10 minutes
- No patient data or clinical records are processed — only meeting coordination text

---

*Built for the Origin Medical Workflow Automation Engineer Intern role challenge.*  
*Questions? Reach out at rishabmohapatra7@gmail.com*
