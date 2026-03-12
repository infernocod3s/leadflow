# GrowthPal Architecture

## What GrowthPal Does

GrowthPal takes a raw CSV of leads (just names + emails + companies) and turns them into fully enriched, qualified, personalized outreach-ready contacts — then pushes them to Smartlead for automated email campaigns. It's a Clay.com replacement that costs ~$0.05/lead instead of $0.50+.

---

## System Overview

```
                         YOU (Browser)
                              |
                    +---------+---------+
                    |                   |
              Dashboard UI         CLI (Terminal)
           (Vercel / Next.js)      (growthpal command)
                    |                   |
                    +--------+----------+
                             |
                      Supabase (DB)
                    PostgreSQL + REST API
                             |
                    +--------+----------+
                    |                   |
              Railway Worker(s)    Smartlead API
            (Python, runs 24/7)   (Email campaigns)
                    |
         +----------+----------+
         |          |          |
      OpenAI    Email APIs   Deepline
      (GPT-4o)  (Prospeo,   (15+ data
               TryKitt,     providers)
               BetterContact,
               Reoon, BounceBan)
```

---

## The Three Deployments

### 1. Dashboard (Vercel) — What the user sees

```
https://dashboard-black-one-12.vercel.app

Pages:
  /                    → Campaign list + global stats
  /campaigns/new       → Create new campaign (form)
  /campaigns/[slug]    → Campaign detail + leads table
                         + Import CSV, Export CSV, Push to Smartlead, Edit Config
  /costs               → Cost analytics by step and campaign
  /settings            → API key management
```

- **Next.js 14** with Tailwind CSS, dark theme
- Talks directly to **Supabase** (reads leads, campaigns, enrichment_logs)
- Has one **API route** (`/api/push-smartlead`) for server-side Smartlead calls
- Auto-refreshes every 10 seconds

### 2. Worker (Railway) — The engine that processes leads

```
Railway Service: worker
Runs 24/7, $5-20/mo

worker/main.py        → Entry point (starts FastAPI + processor loop)
worker/processor.py   → Main loop: poll → claim → process → release
worker/db.py          → Supabase REST API client
worker/api.py         → Health check endpoints (/health, /stats)
worker/config.py      → Environment variables
```

- Polls Supabase every 30 seconds for campaigns with pending leads
- Claims leads atomically (no duplicates across workers)
- Runs each lead through the 9-step pipeline
- Logs every API call with cost/tokens to `enrichment_logs`

### 3. Database (Supabase) — The brain

```
Tables:
  clients              → Company grouping (e.g. "Acme Corp")
  campaigns            → Campaign config + slug + Smartlead ID
  leads                → All lead data (raw → enriched)
  enrichment_logs      → Every API call logged (cost tracking)
  pipeline_runs        → Batch execution records
  settings             → API keys stored from dashboard
```

---

## The Pipeline: What Happens to Each Lead

When a lead enters the system (via CSV upload), it goes through **9 enrichment steps** in order. Three of these are **GATE steps** that can disqualify a lead early, saving money on subsequent steps.

```
CSV Upload
    |
    v
+------------------+
| 1. COMPANY       |  Scrape company website → GPT-4o summarizes
|    RESEARCH      |  Output: company_summary, industry, employee_count
+------------------+
    |
    v
+------------------+
| 2. ICP           |  GPT-4o checks: Does this company match our
|    QUALIFICATION |  ideal customer profile (ICP)?
|    [GATE]        |  If NO → DISQUALIFIED (stop here, save $$$)
+------------------+
    |
    v
+------------------+
| 3. EMAIL         |  Waterfall: try Prospeo first, then TryKitt,
|    FINDING       |  then BetterContact. Stops at first success.
+------------------+
    |
    v
+------------------+
| 4. EMAIL         |  Waterfall: Reoon first, then BounceBan.
|    VERIFICATION  |  Skip if BetterContact found email (pre-verified)
|    [GATE]        |  If INVALID → DISQUALIFIED
+------------------+
    |
    v
+------------------+
| 5. JOB TITLE     |  GPT-4o-mini normalizes: "VP Mktg" → "VP Marketing"
|    CLEANING      |
+------------------+
    |
    v
+------------------+
| 6. NAME          |  GPT-4o-mini cleans: "JOHN" → "John",
|    CLEANING      |  "acme corp inc." → "Acme Corp"
+------------------+
    |
    v
+------------------+
| 7. JOB TITLE     |  GPT-4o-mini: Is "VP Marketing" relevant to our
|    ICP CHECK     |  target titles like "CMO", "Head of Growth"?
|    [GATE]        |  If NO → DISQUALIFIED
+------------------+
    |
    v
+------------------+
| 8. SIGNAL        |  GPT-4o detects: tech stack, recent funding,
|    DETECTION     |  hiring signals, growth indicators
+------------------+
    |
    v
+------------------+
| 9. EMAIL         |  GPT-4o generates personalized cold email
|    GENERATION    |  using company summary + signals + value prop
|                  |  Output: email_subject, email_body
+------------------+
    |
    v
Ready to push to Smartlead!
(status: email_generated)
```

### Why Gate Steps Matter

Gates disqualify leads **early** so you don't waste money on later expensive steps:

```
100 leads imported
    |
    | Step 2 (ICP Gate): 30 fail → DISQUALIFIED
    |
70 leads continue
    |
    | Step 4 (Email Gate): 15 invalid emails → DISQUALIFIED
    |
55 leads continue
    |
    | Step 7 (Title Gate): 10 irrelevant titles → DISQUALIFIED
    |
45 leads fully enriched → email_generated → push to Smartlead

Cost savings: Instead of running all 9 steps on 100 leads,
steps 5-9 only run on 55 leads (45% savings)
```

---

## How the Worker Processes Leads

```
                    WORKER LOOP (every 30 seconds)
                              |
                              v
                 +---------------------------+
                 | 1. Release stale claims   |  (every 5 min)
                 |    from crashed workers   |  Leads stuck > 30 min
                 +---------------------------+  get released
                              |
                              v
                 +---------------------------+
                 | 2. Find campaigns with    |
                 |    pending leads          |  status = 'imported'
                 +---------------------------+
                              |
                              v
                 +---------------------------+
                 | 3. claim_leads()          |  Atomic PostgreSQL:
                 |    (batch of 50)          |  FOR UPDATE SKIP LOCKED
                 |                           |  Prevents duplicates
                 +---------------------------+  across workers
                              |
                              v
                 +---------------------------+
                 | 4. Process batch          |  20 leads in parallel
                 |    concurrently           |  (asyncio semaphore)
                 |    (9 pipeline steps      |
                 |     per lead)             |
                 +---------------------------+
                              |
                              v
                 +---------------------------+
                 | 5. Update lead statuses   |  enriched / disqualified
                 |    Log costs              |  / email_generated / error
                 +---------------------------+
```

### Multiple Workers (Scaling)

```
Worker A (Railway)          Worker B (Railway)
    |                            |
    | claim_leads(50)            | claim_leads(50)
    |                            |
    v                            v
[Lead 1-50]                [Lead 51-100]     ← No overlap!
                                               FOR UPDATE SKIP LOCKED
    |                            |               ensures atomic claiming
    v                            v
Process in parallel        Process in parallel
```

---

## Data Flow: CSV to Smartlead

```
+------------+     +----------+     +-------------------+     +-----------+
|            |     |          |     |                   |     |           |
|  CSV File  +---->+ Supabase +---->+  Railway Worker   +---->+ Smartlead |
|  (upload)  |     | (leads   |     |  (9-step pipeline)|     | (email   |
|            |     |  table)  |     |                   |     |  campaign)|
+------------+     +----------+     +-------------------+     +-----------+
                        ^                    |
                        |                    | Logs every API call:
                        |                    | - step name
                        +--------------------+ - model used
                    enrichment_logs table     | - input/output tokens
                                             | - cost in USD
                                             | - duration
                                             | - success/failure
```

### Status Lifecycle of a Lead

```
imported → in_progress → enriched → email_generated → pushed
                |
                +→ disqualified  (gate step failed)
                +→ error         (API failure)
```

---

## Cost Tracking

Every single API call is logged to `enrichment_logs`:

```
+----------------+--------+--------+--------+----------+---------+
| step_name      | model  | tokens | tokens | cost     | success |
|                |        | (in)   | (out)  | (USD)    |         |
+----------------+--------+--------+--------+----------+---------+
| company_research| gpt-4o|   500  |   500  | $0.0063  |  true   |
| icp_qualification| gpt-4o|  300  |   200  | $0.0028  |  true   |
| email_finding  | prospeo|    0   |     0  | $0.0000  |  true   |
| email_verify   | reoon  |    0   |     0  | $0.0020  |  true   |
| job_title_clean| gpt-4o-mini| 100|   50   | $0.0000  |  true   |
| name_cleaning  | gpt-4o-mini| 80 |   40   | $0.0000  |  true   |
| job_title_icp  | gpt-4o-mini|100 |   50   | $0.0000  |  true   |
| signal_detect  | gpt-4o |  800  |   800  | $0.0100  |  true   |
| email_generate | gpt-4o |  600  |   400  | $0.0055  |  true   |
+----------------+--------+--------+--------+----------+---------+
                                      TOTAL: ~$0.03/lead
```

The dashboard shows this data in real-time:
- Total spend per campaign
- Cost per lead
- Cost per step
- Success/failure rates

---

## Email Finding Waterfall

The system tries multiple providers in order, stopping at the first success:

```
Lead needs email for: "John Smith" at "acme.com"
    |
    v
+----------+
| Prospeo  |  Try LinkedIn finder + domain finder
| (free*)  |  Success? → Use email, mark needs verification
+----------+  Fail? ↓
    |
    v
+----------+
| TryKitt  |  Try domain-based finder
| (paid)   |  Success? → Use email, mark needs verification
+----------+  Fail? ↓
    |
    v
+--------------+
| BetterContact|  Try domain + LinkedIn
| (paid)       |  Success? → Use email, SKIP verification
+--------------+  (BetterContact self-verifies)
    |
    v
No email found → Lead continues without email
```

---

## Campaign Configuration

Each campaign has a JSONB config stored in the `campaigns` table:

```json
{
  "icp_description": "B2B SaaS, 50-500 employees, Series A+",
  "target_titles": ["VP Marketing", "CMO", "Head of Growth"],
  "target_industries": ["SaaS", "Fintech"],
  "excluded_domains": ["gmail.com", "yahoo.com"],
  "email_tone": "professional",
  "email_cta": "Book a 15-minute call",
  "sender_name": "John Smith",
  "sender_company": "GrowthPal",
  "sender_value_prop": "We help SaaS companies book 30+ meetings/month"
}
```

This config controls:
- **Steps 2 & 7**: What makes a lead "qualified" (ICP + title matching)
- **Step 9**: How the email is written (tone, CTA, sender identity)
- **Step 3**: Which domains to exclude from email finding

---

## Database Schema (Key Tables)

```
clients
├── id (UUID)
├── name ("Acme Corp")
└── created_at

campaigns
├── id (UUID)
├── client_id → clients.id
├── slug ("acme-q1-2026")
├── config (JSONB — ICP, email settings, etc.)
├── smartlead_campaign_id (INT)
└── created_at, updated_at

leads
├── id (UUID)
├── campaign_id → campaigns.id
├── Raw fields: raw_email, raw_first_name, raw_last_name, raw_company, raw_title
├── Cleaned fields: email, first_name, last_name, company_name, job_title
├── Enrichment: company_summary, icp_qualified, icp_reason, title_relevant
├── Signals: signals, tech_stack (JSONB)
├── Email: email_subject, email_body
├── Pipeline: pipeline_status, current_step, error_message
├── Worker: claimed_by, claimed_at
└── created_at, updated_at

enrichment_logs
├── id (UUID)
├── lead_id → leads.id
├── campaign_id → campaigns.id
├── step_name, model
├── input_tokens, output_tokens, cost
├── duration_ms, success, error_message
└── created_at

settings
├── key ("smartlead_api_key")
├── value (encrypted string)
└── updated_at
```

---

## Tech Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Next.js 14, Tailwind CSS | Dashboard UI |
| **Hosting (Frontend)** | Vercel | Auto-deploy from GitHub |
| **Backend Workers** | Python 3.12, asyncio | Lead processing pipeline |
| **Hosting (Workers)** | Railway | 24/7 worker containers |
| **Database** | Supabase (PostgreSQL) | Central data store + REST API |
| **AI** | OpenAI GPT-4o / GPT-4o-mini | Company research, ICP check, email gen |
| **Email Finding** | Prospeo, TryKitt, BetterContact | Waterfall email discovery |
| **Email Verification** | Reoon, BounceBan | Waterfall email validation |
| **Outreach** | Smartlead | Automated email campaigns |
| **Data Enrichment** | Deepline (optional) | 15+ provider waterfall |

---

## Typical Workflow

```
1. User creates campaign        →  /campaigns/new (set ICP, titles, email settings)
2. User uploads CSV             →  /campaigns/[slug] → "Import CSV" button
3. Railway worker picks up      →  Automatically, every 30 seconds
4. Pipeline runs (3-5 min)      →  Dashboard shows live progress
5. User reviews results         →  Click leads to see enrichment details
6. User pushes to Smartlead     →  "Push to Smartlead" button
7. User exports CSV             →  "Export CSV" button (backup/analysis)
```

**Cost for 1,000 leads**: ~$30-50 (vs $500+ on Clay.com)
**Time for 1,000 leads**: ~30-60 minutes (single worker, 20 concurrent)
