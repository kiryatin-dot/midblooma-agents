# n8n Setup Guide — Midblooma AI Team

## Prerequisites
- n8n running (cloud or self-hosted)
- Python 3.11+ installed on the same server as n8n
- `ANTHROPIC_API_KEY` set in environment

---

## Step 1 — Install Python dependencies

```bash
cd /path/to/midblooma-agents
pip install -r requirements.txt
```

## Step 2 — Start the agent server

```bash
# Development
python server.py

# Production (recommended)
gunicorn server:app --timeout 300 --workers 1 --bind 0.0.0.0:5000
```

The server exposes all 8 agents at `http://localhost:5000/agents/<name>`.
Test it: `curl http://localhost:5000/health`

---

## Step 3 — Configure n8n environment variables

In n8n Settings → Environment Variables, add:

| Variable | Value |
|---|---|
| `NUFAR_EMAIL` | nufar@midblooma.com |
| `TREND_LOG_SHEET_ID` | Google Sheet ID (from the URL) |

---

## Step 4 — Set up Google Sheets

Create one Google Sheet with these tabs:

| Tab name | Columns |
|---|---|
| **Trend Log** | date, run_id, rank, source, title, url, engagement_score, pain_point, content_angle |
| **Content Log** | date, run_id, topic |
| **Performance Log** | date, run_id, checker_uses, new_members, total_members, social_reach, newsletter_open_rate, anomaly_count |
| **Execution Log** | run_id, week_of, executed_count, skipped_count, summary |

---

## Step 5 — Set up n8n credentials

### Google Sheets OAuth
1. n8n → Credentials → New → Google Sheets OAuth2
2. Follow the OAuth setup
3. Note the credential ID → replace `REPLACE_WITH_GOOGLE_CRED_ID` in both workflow JSON files

### Gmail OAuth
1. n8n → Credentials → New → Gmail OAuth2
2. Follow the OAuth setup
3. Note the credential ID → replace `REPLACE_WITH_GMAIL_CRED_ID` in both workflow JSON files

---

## Step 6 — Import workflows into n8n

1. n8n → Workflows → Import from file
2. Import `daily_workflow.json`
3. Import `weekly_workflow.json`
4. Open each workflow and update the credential IDs in the Google Sheets and Gmail nodes
5. In `daily_workflow.json`: replace the **"Fetch Platform Metrics"** Code node with a real HTTP Request to your analytics API or a Google Sheets read node

---

## Step 7 — Replace the Fetch Platform Metrics node

The `Fetch Platform Metrics` node in the daily workflow is a placeholder.
Replace it with one of:

**Option A — HTTP Request to your analytics API:**
- Node type: HTTP Request
- URL: your platform's metrics endpoint
- Map the response to `today_metrics` and `seven_day_averages`

**Option B — Google Sheets read (if you manually log metrics):**
- Node type: Google Sheets → Read
- Sheet: your metrics sheet
- Use a Code node to calculate the 7-day average from the last 7 rows

---

## Step 8 — Activate workflows

1. Open each workflow in n8n
2. Click **Activate** toggle (top right)
3. Daily workflow fires at 06:00 London time
4. Weekly workflow fires Monday 08:00 London time

---

## How the weekly chain handles Nufar's approval gates

| Gate | What happens |
|---|---|
| **Strategist needs_review** | Email sent to Nufar. Chain stops until next Monday unless restarted manually. |
| **QA blocked** | Email sent to Nufar with the full issues list. Chain stops. Fix the Writer prompt and re-run. |
| **Newsletter needs_review** | Email sent to Nufar with draft preview. **Newsletter is never auto-sent.** Nufar sends it manually from MailerLite/Gmail. |

---

## Running tests (once Python is installed)

```bash
# Unit tests (no API key needed)
pytest

# Integration tests (requires ANTHROPIC_API_KEY)
pytest -m integration
```
