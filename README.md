# LeadFlow

**CLI-powered lead enrichment pipeline** — an open-source alternative to Clay.com.

Import LinkedIn leads, enrich them with AI-powered company research, qualify against your ICP, find and verify emails through multi-provider waterfalls, generate personalized cold emails, and push directly to Smartlead — all from your terminal.

## Why LeadFlow?

| | Clay.com | LeadFlow |
|---|---|---|
| **Cost** | $149–499/mo + credits | Free — BYOK (bring your own keys) |
| **Email finding** | Built-in credits | Waterfall across Prospeo, TryKitt, BetterContact |
| **Verification** | Basic | Reoon + BounceBan fallback |
| **AI enrichment** | Fixed steps | Fully customizable via YAML prompts |
| **Data ownership** | Their servers | Your Supabase instance |
| **Extensibility** | Limited | Add any step with a Python class or YAML prompt |

## Pipeline

```
CSV Import (LinkedIn / AI-Ark leads)
  → Step 1: Company research (website scrape + GPT-4o summary)
  → Step 2: ICP qualification (GATE — skips rest if not a fit)
  → Step 3: Email finding waterfall (Prospeo → TryKitt → BetterContact)
  → Step 4: Email verification (GATE — Reoon → BounceBan)
  → Step 5: Job title cleaning (GPT-4o-mini)
  → Step 6: Name cleaning (GPT-4o-mini)
  → Step 7: Job title ICP match (GATE — skip irrelevant roles)
  → Step 8: Signal detection (GPT-4o — tech stack, funding, hiring)
  → [Custom AI steps from YAML]
  → Step 9: Email generation (GPT-4o — personalized cold emails)
  → Push to Smartlead
```

**GATE** steps save money — if a lead doesn't qualify, the pipeline stops processing it immediately. No wasted API calls on bad leads.

## Quick Start

### 1. Install

```bash
git clone https://github.com/prabeshkhanal/leadflow.git
cd leadflow
pip install -e .
```

### 2. Set up Supabase

Create a free project at [supabase.com](https://supabase.com), then run the migration:

```bash
leadflow migrate --db-url "postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres"
```

Or paste the contents of `leadflow/db/migrations/001_initial.sql` into the Supabase SQL Editor.

### 3. Configure

```bash
cp .env.example .env
# Fill in your API keys
```

Required keys:
- `SUPABASE_URL` + `SUPABASE_KEY` — from Supabase dashboard
- `OPENAI_API_KEY` — for AI enrichment steps

Optional (enable as needed):
- `PROSPEO_API_KEY` — email finding
- `TRYKITT_API_KEY` — email finding fallback
- `BETTERCONTACT_API_KEY` — email finding fallback (self-verifies)
- `REOON_API_KEY` — email verification
- `BOUNCEBAN_API_KEY` — verification fallback
- `SMARTLEAD_API_KEY` — for pushing leads to campaigns

### 4. Create a campaign config

```bash
cp configs/_template.yaml configs/my-campaign.yaml
# Edit with your ICP, target titles, email settings
```

### 5. Run

```bash
# Import leads from CSV
leadflow import -f leads.csv -c my-campaign --config configs/my-campaign.yaml

# Run the enrichment pipeline
leadflow run -c my-campaign --config configs/my-campaign.yaml

# Check stats
leadflow stats -c my-campaign

# Push to Smartlead
leadflow push -c my-campaign --smartlead-id 12345

# Export enriched leads to CSV
leadflow export -c my-campaign -o enriched.csv
```

## CLI Commands

| Command | Description |
|---|---|
| `leadflow import` | Import leads from CSV into a campaign |
| `leadflow run` | Run the enrichment pipeline |
| `leadflow push` | Push qualified leads to Smartlead |
| `leadflow export` | Export enriched leads to CSV |
| `leadflow stats` | View campaign statistics and costs |
| `leadflow campaigns` | List all campaigns |
| `leadflow steps` | List available enrichment steps |
| `leadflow inspect` | Inspect a single lead by email |
| `leadflow migrate` | Run database migrations |

## Custom AI Steps

Define any enrichment step using natural language prompts in your campaign YAML:

```yaml
custom_ai_steps:
  - name: "find_investors"
    prompt: |
      Research the investors and funding history for {{company_name}}.
      Website: {{website}}
      What rounds have they raised? Who led each round?
    output_field: "investors"
    model: "gpt-4o"
    scrape_website: true

  - name: "pain_points"
    prompt: |
      Based on this company profile, identify their top 3 pain points:
      Company: {{company_name}}
      Summary: {{company_summary}}
    output_field: "pain_points"
    model: "gpt-4o-mini"

  - name: "competitor_check"
    prompt: |
      Does {{company_name}} have direct competitors?
      List them if so.
    output_field: "competitors"
    model: "gpt-4o-mini"
    is_gate: true           # Stop pipeline if condition fails
    gate_field: "has_competitors"
```

Use `{{field_name}}` to inject any lead field into your prompts. Results are stored in the lead's `raw_extra` JSONB column.

## Email Finding Waterfall

LeadFlow tries multiple providers in order, stopping at the first success:

1. **Prospeo** — fast, reliable, free credits available
2. **TryKitt** — good coverage fallback
3. **BetterContact** — self-verifying (skips separate verification step)

Only the providers you configure API keys for are used.

## Email Verification

Two-layer verification to protect sender reputation:

1. **Reoon** — primary verifier
2. **BounceBan** — fallback when Reoon returns uncertain results

Leads from BetterContact skip verification (it's built-in).

## Deepline Integration (Optional)

[Deepline](https://deepline.com) waterfalls enrichment across 15+ data providers (Apollo, Hunter, People Data Labs, etc.). BYOK tier is free — you pay providers directly.

```bash
# Install Deepline CLI
curl -s "https://code.deepline.com/api/v2/cli/install" | bash

# Enable in campaign config
use_deepline: true
deepline_before_step: "company_research"
```

## Deploy to Railway (Workers)

Railway runs the lead processing workers 24/7. Scale to 50+ worker instances for massive throughput.

### 1. Push to GitHub (done)

### 2. Create a Railway project

- Go to [railway.app](https://railway.app)
- New Project -> Deploy from GitHub repo
- Select the `leadflow` repo

### 3. Set environment variables

In Railway dashboard -> Variables:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT.supabase.co:5432/postgres
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=your-service-role-key
OPENAI_API_KEY=sk-...
PROSPEO_API_KEY=...
TRYKITT_API_KEY=...
BETTERCONTACT_API_KEY=...
REOON_API_KEY=...
BOUNCEBAN_API_KEY=...
SMARTLEAD_API_KEY=...
BATCH_SIZE=50
CONCURRENCY=20
POLL_INTERVAL=5
```

### 4. Run the worker migration

```bash
leadflow migrate --db-url "postgresql://postgres:PASS@db.xxx.supabase.co:5432/postgres"
```

This adds the `claim_leads()` function for concurrent worker support.

### 5. Scale workers

In Railway -> Service -> Settings -> Replicas, increase to N instances. Each worker atomically claims batches using `FOR UPDATE SKIP LOCKED`, so they never process the same lead twice.

### Worker API

Each worker exposes health and monitoring endpoints:

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (used by Railway) |
| `GET /stats` | Worker instance stats (processed, errors, cost) |
| `GET /queue` | Global queue stats across all campaigns |
| `GET /campaigns` | Campaigns with pending leads |

## Deploy Dashboard to Vercel

The Next.js dashboard shows campaigns, leads, pipeline progress, and cost tracking.

### 1. Deploy

```bash
cd dashboard
npm install
npx vercel
```

Or connect the GitHub repo to Vercel and set the root directory to `dashboard/`.

### 2. Set environment variables

In Vercel dashboard -> Settings -> Environment Variables:

```
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Dashboard Pages

- **`/`** — Campaign list with global stats and pipeline progress bars
- **`/campaigns/[slug]`** — Campaign detail: lead table, status breakdown, step cost analysis, lead inspector modal
- **`/costs`** — Cost overview: spend by step, by campaign, tokens, averages

## Architecture

```
leadflow/               # Python package — enrichment pipeline
├── ai/                 # OpenAI client + prompt templates
├── db/                 # Supabase client, queries, migrations
├── enrichments/        # 9 built-in steps + custom AI
├── integrations/       # Prospeo, TryKitt, BetterContact, Reoon,
│                       # BounceBan, Smartlead, Deepline, CSV
├── pipeline/           # Batch processor, step registry, runner
├── scrapers/           # Website content scraper
├── utils/              # Logger, retry, rate limiter, cost tracker
├── cli.py              # CLI entry point
└── config.py           # .env + YAML config loader

worker/                 # Railway worker service
├── main.py             # Entry point (worker loop + API server)
├── processor.py        # Lead processing with atomic claiming
├── api.py              # FastAPI health/monitoring endpoints
├── db.py               # Direct Postgres access (psycopg2)
└── stats.py            # In-memory worker stats

dashboard/              # Vercel Next.js dashboard
├── app/                # App Router pages
│   ├── page.tsx        # Campaign overview
│   ├── campaigns/      # Campaign detail
│   └── costs/          # Cost analytics
└── lib/                # Supabase client + utilities

Dockerfile              # Railway container
railway.toml            # Railway deployment config
```

### Key Design Decisions

- **Railway workers** — scale horizontally with `FOR UPDATE SKIP LOCKED` for safe concurrent processing
- **Supabase** — free tier, instant REST API, real-time subscriptions for dashboard
- **GATE steps** — ICP qualification happens *before* email finding to save credits on bad leads
- **Waterfall providers** — try cheaper/faster providers first, fall back to expensive ones
- **YAML-driven custom steps** — non-technical users can add AI enrichment without writing Python
- **Per-lead cost tracking** — every API call is logged with token counts and costs

## Cost Tracking

Every API call is logged with:
- Token usage (input + output)
- Cost in USD
- Duration in ms
- Success/failure status

View costs via CLI or the dashboard:

```bash
leadflow stats -c my-campaign
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check .

# Run tests
pytest

# Run dashboard locally
cd dashboard && npm install && npm run dev
```

## Requirements

- Python 3.12+
- Supabase account (free tier works)
- OpenAI API key
- At least one email finding provider key (Prospeo, TryKitt, or BetterContact)
- Railway account (for workers) — ~$20/mo
- Vercel account (for dashboard) — free tier works

## License

MIT
