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

## Architecture

```
leadflow/
├── ai/                   # OpenAI client + prompt templates
├── db/                   # Supabase client, queries, migrations
├── enrichments/          # 9 built-in enrichment steps + custom AI
├── integrations/         # Prospeo, TryKitt, BetterContact, Reoon,
│                         # BounceBan, Smartlead, Deepline, CSV
├── pipeline/             # Batch processor, step registry, runner
├── scrapers/             # Website content scraper
├── utils/                # Logger, retry, rate limiter, cost tracker
├── cli.py                # CLI entry point (argparse)
└── config.py             # .env + YAML config loader
```

### Key Design Decisions

- **Supabase as the database** — free tier, instant REST API, real-time dashboard for monitoring
- **GATE steps** — ICP qualification happens *before* email finding to save credits on bad leads
- **Waterfall providers** — try cheaper/faster providers first, fall back to expensive ones
- **YAML-driven custom steps** — non-technical users can add AI enrichment without writing Python
- **Async pipeline with concurrency control** — process 20 leads simultaneously by default
- **Per-lead cost tracking** — every API call is logged with token counts and costs

## Cost Tracking

Every API call is logged with:
- Token usage (input + output)
- Cost in USD
- Duration in ms
- Success/failure status

View costs per campaign:

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
```

## Requirements

- Python 3.12+
- Supabase account (free tier works)
- OpenAI API key
- At least one email finding provider key (Prospeo, TryKitt, or BetterContact)

## License

MIT
