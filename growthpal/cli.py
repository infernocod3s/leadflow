"""CLI commands for GrowthPal — argparse-based interface."""

import argparse
import asyncio
import sys
from pathlib import Path

from rich.table import Table

from growthpal.config import CampaignConfig, get_config
from growthpal.utils.logger import console, get_logger, setup_logging

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="growthpal",
        description="GrowthPal — CLI lead enrichment pipeline",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── import ───────────────────────────────────────────────────────────
    p_import = sub.add_parser("import", help="Import leads from CSV")
    p_import.add_argument("--file", "-f", required=True, help="Path to CSV file")
    p_import.add_argument("--campaign", "-c", required=True, help="Campaign slug")
    p_import.add_argument("--client", default=None, help="Client name (defaults to campaign slug prefix)")
    p_import.add_argument("--config", default=None, help="Path to campaign YAML config")

    # ── run ───────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Run enrichment pipeline")
    p_run.add_argument("--campaign", "-c", required=True, help="Campaign slug")
    p_run.add_argument("--steps", nargs="+", default=["all"], help="Steps to run (default: all)")
    p_run.add_argument("--concurrency", type=int, default=None, help="Max concurrent leads")
    p_run.add_argument("--batch-size", type=int, default=100, help="Batch size")
    p_run.add_argument("--dry-run", action="store_true", help="Preview without processing")
    p_run.add_argument("--config", default=None, help="Path to campaign YAML config")

    # ── push ──────────────────────────────────────────────────────────────
    p_push = sub.add_parser("push", help="Push enriched leads to Smartlead")
    p_push.add_argument("--campaign", "-c", required=True, help="Campaign slug")
    p_push.add_argument("--smartlead-id", type=int, default=None, help="Smartlead campaign ID")
    p_push.add_argument("--limit", type=int, default=500, help="Max leads to push")

    # ── export ────────────────────────────────────────────────────────────
    p_export = sub.add_parser("export", help="Export enriched leads to CSV")
    p_export.add_argument("--campaign", "-c", required=True, help="Campaign slug")
    p_export.add_argument("--output", "-o", required=True, help="Output CSV path")

    # ── stats ─────────────────────────────────────────────────────────────
    p_stats = sub.add_parser("stats", help="Show campaign stats")
    p_stats.add_argument("--campaign", "-c", required=True, help="Campaign slug")

    # ── campaigns ─────────────────────────────────────────────────────────
    sub.add_parser("campaigns", help="List all campaigns")

    # ── steps ─────────────────────────────────────────────────────────────
    sub.add_parser("steps", help="List available enrichment steps")

    # ── migrate ─────────────────────────────────────────────────────────
    p_migrate = sub.add_parser("migrate", help="Run database migrations")
    p_migrate.add_argument(
        "--db-url", required=True,
        help="PostgreSQL connection URL (e.g. postgresql://postgres:PASS@db.xxx.supabase.co:5432/postgres)",
    )

    # ── inspect ───────────────────────────────────────────────────────────
    p_inspect = sub.add_parser("inspect", help="Inspect a single lead")
    p_inspect.add_argument("--email", "-e", required=True, help="Lead email address")
    p_inspect.add_argument("--campaign", "-c", default=None, help="Campaign slug (optional)")

    args = parser.parse_args()

    if args.verbose:
        setup_logging("DEBUG")
    else:
        setup_logging(get_config().log_level)

    # Validate config
    cfg = get_config()
    errors = cfg.validate()
    if errors and args.command not in ("steps", "migrate"):
        for err in errors:
            console.print(f"[red]Config error:[/red] {err}")
        console.print("\nCopy .env.example to .env and fill in your keys.")
        sys.exit(1)

    # Dispatch
    commands = {
        "import": lambda: cmd_import(args),
        "run": lambda: asyncio.run(cmd_run(args)),
        "push": lambda: asyncio.run(cmd_push(args)),
        "export": lambda: cmd_export(args),
        "stats": lambda: cmd_stats(args),
        "campaigns": lambda: cmd_campaigns(),
        "steps": lambda: cmd_steps(),
        "inspect": lambda: cmd_inspect(args),
        "migrate": lambda: cmd_migrate(args),
    }
    try:
        commands[args.command]()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if args.verbose:
            console.print_exception()
        sys.exit(1)


# ── Command implementations ──────────────────────────────────────────────────


def cmd_import(args: argparse.Namespace) -> None:
    from growthpal.db import queries as db
    from growthpal.integrations.csv_handler import import_csv

    client_name = args.client or args.campaign.split("-")[0]

    # Load campaign config if provided
    config_dict = None
    if args.config:
        cc = CampaignConfig.from_yaml(args.config)
        config_dict = {
            "icp_description": cc.icp_description,
            "target_titles": cc.target_titles,
            "target_industries": cc.target_industries,
        }

    campaign = db.get_or_create_campaign(client_name, args.campaign, config_dict)
    count = import_csv(args.file, campaign["id"])
    console.print(f"[green]Imported {count} leads[/green] into campaign [cyan]{args.campaign}[/cyan]")


async def cmd_run(args: argparse.Namespace) -> None:
    # Import enrichments to trigger registration
    import growthpal.enrichments  # noqa: F401
    from growthpal.pipeline.runner import run_pipeline

    campaign_config = None
    if args.config:
        campaign_config = CampaignConfig.from_yaml(args.config)

    concurrency = args.concurrency or get_config().default_concurrency

    result = await run_pipeline(
        campaign_slug=args.campaign,
        step_names=args.steps,
        concurrency=concurrency,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        campaign_config=campaign_config,
    )

    console.print(f"\n[green]Pipeline complete:[/green]")
    console.print(f"  Total:         {result['total']}")
    console.print(f"  Processed:     {result['processed']}")
    console.print(f"  Qualified:     {result['qualified']}")
    console.print(f"  Disqualified:  {result['disqualified']}")
    console.print(f"  Errors:        {result['errors']}")
    console.print(f"  Total cost:    ${result['cost']:.4f}")


async def cmd_push(args: argparse.Namespace) -> None:
    from growthpal.db import queries as db
    from growthpal.integrations.smartlead import push_leads_to_smartlead

    campaign = db.get_campaign(args.campaign)
    if not campaign:
        console.print(f"[red]Campaign not found:[/red] {args.campaign}")
        return

    smartlead_id = args.smartlead_id or campaign.get("smartlead_campaign_id")
    if not smartlead_id:
        console.print("[red]No Smartlead campaign ID.[/red] Use --smartlead-id or set in campaign config.")
        return

    count = await push_leads_to_smartlead(args.campaign, smartlead_id, args.limit)
    console.print(f"[green]Pushed {count} leads[/green] to Smartlead campaign {smartlead_id}")


def cmd_export(args: argparse.Namespace) -> None:
    from growthpal.db import queries as db
    from growthpal.integrations.csv_handler import export_csv

    campaign = db.get_campaign(args.campaign)
    if not campaign:
        console.print(f"[red]Campaign not found:[/red] {args.campaign}")
        return

    count = export_csv(campaign["id"], args.output)
    console.print(f"[green]Exported {count} leads[/green] to {args.output}")


def cmd_stats(args: argparse.Namespace) -> None:
    from growthpal.db import queries as db

    campaign = db.get_campaign(args.campaign)
    if not campaign:
        console.print(f"[red]Campaign not found:[/red] {args.campaign}")
        return

    campaign_id = campaign["id"]

    # Lead counts by status
    counts = db.get_campaign_lead_counts(campaign_id)
    total = sum(counts.values())

    table = Table(title=f"Campaign: {args.campaign}")
    table.add_column("Status", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")

    for status, count in sorted(counts.items()):
        pct = f"{count / total * 100:.1f}%" if total else "0%"
        table.add_row(status, str(count), pct)

    table.add_section()
    table.add_row("TOTAL", str(total), "100%", style="bold")
    console.print(table)

    # Cost summary
    total_cost = db.get_campaign_total_cost(campaign_id)
    if total_cost > 0:
        console.print(f"\nTotal cost: [green]${total_cost:.4f}[/green]")
        if total:
            console.print(f"Cost per lead: [green]${total_cost / total:.4f}[/green]")

    # Step breakdown
    step_costs = db.get_campaign_costs(campaign_id)
    if step_costs:
        st = Table(title="Step Breakdown")
        st.add_column("Step", style="cyan")
        st.add_column("Calls", justify="right")
        st.add_column("Success", justify="right", style="green")
        st.add_column("Failures", justify="right", style="red")
        for s in step_costs:
            st.add_row(s["step"], str(s["calls"]), str(s["success"]), str(s["failures"]))
        console.print(st)


def cmd_campaigns() -> None:
    from growthpal.db import queries as db

    campaigns = db.list_campaigns()
    if not campaigns:
        console.print("No campaigns found.")
        return

    table = Table(title="Campaigns")
    table.add_column("Slug", style="cyan")
    table.add_column("Client")
    table.add_column("Created")
    table.add_column("Smartlead ID")

    for c in campaigns:
        client_name = c.get("clients", {}).get("name", "—") if isinstance(c.get("clients"), dict) else "—"
        table.add_row(
            c["slug"],
            client_name,
            c["created_at"][:10] if c.get("created_at") else "—",
            str(c.get("smartlead_campaign_id") or "—"),
        )

    console.print(table)


def cmd_steps() -> None:
    # Import to register
    import growthpal.enrichments  # noqa: F401
    from growthpal.pipeline.registry import PIPELINE_ORDER, _registry

    table = Table(title="Built-in Enrichment Steps")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Step", style="cyan")
    table.add_column("Gate", justify="center")
    table.add_column("Class")

    for i, name in enumerate(PIPELINE_ORDER, 1):
        cls = _registry.get(name)
        if cls:
            instance = cls()
            table.add_row(
                str(i),
                name,
                "[red]GATE[/red]" if instance.is_gate else "",
                cls.__name__,
            )

    console.print(table)

    # Dynamic steps info
    console.print("\n[bold]Dynamic Steps[/bold] (configured per-campaign in YAML):")
    console.print("  [cyan]deepline_enrich[/cyan] — Waterfall enrichment via Deepline (15+ providers)")

    from growthpal.integrations.deepline import is_deepline_installed
    if is_deepline_installed():
        console.print("    Status: [green]Installed[/green]")
    else:
        console.print("    Status: [yellow]Not installed[/yellow] — curl -s 'https://code.deepline.com/api/v2/cli/install' | bash")

    console.print("  [cyan]custom:*[/cyan] — Custom AI enrichment steps (define in campaign YAML)")
    console.print("    Example: custom:find_investors, custom:pain_points, etc.")


def cmd_inspect(args: argparse.Namespace) -> None:
    from growthpal.db import queries as db

    campaign_id = None
    if args.campaign:
        campaign = db.get_campaign(args.campaign)
        if campaign:
            campaign_id = campaign["id"]

    lead = db.get_lead_by_email(args.email, campaign_id)
    if not lead:
        console.print(f"[red]Lead not found:[/red] {args.email}")
        return

    table = Table(title=f"Lead: {args.email}", show_lines=True)
    table.add_column("Field", style="cyan", width=25)
    table.add_column("Value", overflow="fold")

    # Show key fields first, then rest
    priority_fields = [
        "pipeline_status", "email", "first_name", "last_name",
        "company_name", "job_title", "website",
        "company_summary", "icp_qualified", "icp_reason",
        "title_relevant", "email_subject", "email_body",
        "error_message",
    ]

    shown = set()
    for field in priority_fields:
        val = lead.get(field)
        if val is not None and val != "" and val != {} and val != []:
            table.add_row(field, str(val))
            shown.add(field)

    # Show remaining non-empty fields
    skip = {"id", "campaign_id", "created_at", "updated_at"}
    for field, val in sorted(lead.items()):
        if field in shown or field in skip:
            continue
        if val is not None and val != "" and val != {} and val != [] and val != "{}":
            table.add_row(field, str(val))

    console.print(table)


def cmd_migrate(args: argparse.Namespace) -> None:
    import glob as globmod
    from pathlib import Path

    import psycopg2

    migrations_dir = Path(__file__).parent / "db" / "migrations"
    sql_files = sorted(globmod.glob(str(migrations_dir / "*.sql")))

    if not sql_files:
        console.print("[yellow]No migration files found.[/yellow]")
        return

    console.print(f"[cyan]Connecting to database...[/cyan]")
    try:
        conn = psycopg2.connect(args.db_url)
        conn.autocommit = True
        cur = conn.cursor()

        for sql_file in sql_files:
            name = Path(sql_file).name
            console.print(f"  Running [cyan]{name}[/cyan]...")
            with open(sql_file) as f:
                sql = f.read()
            cur.execute(sql)
            console.print(f"  [green]{name} applied.[/green]")

        cur.close()
        conn.close()
        console.print(f"\n[green]All migrations applied successfully.[/green]")
    except psycopg2.errors.DuplicateObject:
        console.print("[yellow]Migration already applied (tables exist).[/yellow]")
    except Exception as e:
        console.print(f"[red]Migration failed:[/red] {e}")
        sys.exit(1)
