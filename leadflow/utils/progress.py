"""Live progress dashboard for pipeline runs using Rich."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn, TimeElapsedColumn
from rich.columns import Columns

from leadflow.utils.logger import console


@dataclass
class PipelineProgress:
    """Tracks real-time pipeline progress for the live dashboard."""

    total_leads: int = 0
    processed: int = 0
    qualified: int = 0
    disqualified: int = 0
    errors: int = 0
    emails_found: int = 0
    emails_verified: int = 0

    # Per-step tracking
    step_counts: dict[str, int] = field(default_factory=dict)
    step_active: dict[str, int] = field(default_factory=dict)

    # Cost
    total_cost: float = 0.0
    step_costs: dict[str, float] = field(default_factory=dict)

    # Timing
    start_time: float = field(default_factory=time.monotonic)
    current_lead_email: str = ""
    current_step: str = ""
    batch_num: int = 0
    total_batches: int = 0

    # Provider stats
    provider_hits: dict[str, int] = field(default_factory=dict)
    provider_misses: dict[str, int] = field(default_factory=dict)

    def record_step(self, step_name: str, cost: float = 0.0) -> None:
        self.step_counts[step_name] = self.step_counts.get(step_name, 0) + 1
        self.step_costs[step_name] = self.step_costs.get(step_name, 0) + cost
        self.total_cost += cost

    def record_provider(self, provider: str, found: bool) -> None:
        if found:
            self.provider_hits[provider] = self.provider_hits.get(provider, 0) + 1
        else:
            self.provider_misses[provider] = self.provider_misses.get(provider, 0) + 1

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def leads_per_minute(self) -> float:
        elapsed_min = self.elapsed / 60
        return self.processed / elapsed_min if elapsed_min > 0 else 0

    @property
    def est_remaining_min(self) -> float:
        if self.leads_per_minute <= 0:
            return 0
        remaining = self.total_leads - self.processed
        return remaining / self.leads_per_minute

    @property
    def pass_rate(self) -> float:
        total = self.qualified + self.disqualified
        return (self.qualified / total * 100) if total > 0 else 0

    def build_display(self) -> Layout:
        """Build the full dashboard layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Header
        elapsed_str = _format_duration(self.elapsed)
        remaining_str = _format_duration(self.est_remaining_min * 60) if self.est_remaining_min > 0 else "calculating..."
        header_text = Text.assemble(
            ("  LEADFLOW PIPELINE  ", "bold white on blue"),
            ("  ", ""),
            (f"Batch {self.batch_num}/{self.total_batches}  ", "dim"),
            (f"Elapsed: {elapsed_str}  ", "cyan"),
            (f"ETA: {remaining_str}  ", "yellow"),
        )
        layout["header"].update(Panel(header_text, style="blue"))

        # Body — split into left (progress) and right (details)
        layout["body"].split_row(
            Layout(name="progress", ratio=3),
            Layout(name="details", ratio=2),
        )

        # Progress table
        progress_table = Table(show_header=True, expand=True, title="Pipeline Progress")
        progress_table.add_column("Metric", style="cyan", width=18)
        progress_table.add_column("Count", justify="right", width=8)
        progress_table.add_column("", width=20)

        pct_done = (self.processed / self.total_leads * 100) if self.total_leads > 0 else 0
        bar = _progress_bar(pct_done)

        progress_table.add_row("Total Leads", str(self.total_leads), "")
        progress_table.add_row("Processed", f"[bold]{self.processed}[/bold]", bar)
        progress_table.add_row("Qualified", f"[green]{self.qualified}[/green]", f"[green]{self.pass_rate:.0f}% pass rate[/green]")
        progress_table.add_row("Disqualified", f"[yellow]{self.disqualified}[/yellow]", "")
        progress_table.add_row("Errors", f"[red]{self.errors}[/red]", "")
        progress_table.add_row("", "", "")
        progress_table.add_row("Emails Found", str(self.emails_found), "")
        progress_table.add_row("Emails Verified", str(self.emails_verified), "")
        progress_table.add_row("", "", "")
        progress_table.add_row("Speed", f"{self.leads_per_minute:.1f}/min", "")
        progress_table.add_row("Total Cost", f"[green]${self.total_cost:.4f}[/green]", "")

        cost_per_lead = self.total_cost / self.processed if self.processed > 0 else 0
        progress_table.add_row("Cost/Lead", f"[green]${cost_per_lead:.4f}[/green]", "")

        layout["progress"].update(progress_table)

        # Details — step breakdown + provider stats
        details_table = Table(show_header=True, expand=True, title="Step Breakdown")
        details_table.add_column("Step", style="cyan", width=20)
        details_table.add_column("Done", justify="right", width=6)
        details_table.add_column("Cost", justify="right", width=10)

        for step_name in sorted(self.step_counts.keys()):
            count = self.step_counts[step_name]
            cost = self.step_costs.get(step_name, 0)
            active = self.step_active.get(step_name, 0)
            name_display = step_name
            if active > 0:
                name_display = f"[bold]{step_name}[/bold] ({active} active)"
            details_table.add_row(name_display, str(count), f"${cost:.4f}")

        # Provider stats
        if self.provider_hits or self.provider_misses:
            details_table.add_section()
            details_table.add_row("[bold]Provider[/bold]", "[bold]Hits[/bold]", "[bold]Miss[/bold]")
            all_providers = set(list(self.provider_hits.keys()) + list(self.provider_misses.keys()))
            for provider in sorted(all_providers):
                hits = self.provider_hits.get(provider, 0)
                misses = self.provider_misses.get(provider, 0)
                total = hits + misses
                rate = f"{hits/total*100:.0f}%" if total > 0 else "—"
                details_table.add_row(provider, f"[green]{hits}[/green] ({rate})", str(misses))

        layout["details"].update(details_table)

        # Footer — current activity
        footer_text = Text.assemble(
            ("  Current: ", "dim"),
            (self.current_step or "idle", "bold cyan"),
            ("  |  ", "dim"),
            (self.current_lead_email or "", "dim"),
        )
        layout["footer"].update(Panel(footer_text, style="dim"))

        return layout


class LiveDashboard:
    """Context manager for the live-updating terminal dashboard."""

    def __init__(self, progress: PipelineProgress):
        self.progress = progress
        self._live: Live | None = None

    def __enter__(self) -> "LiveDashboard":
        self._live = Live(
            self.progress.build_display(),
            console=console,
            refresh_per_second=2,
            screen=False,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args) -> None:
        if self._live:
            self._live.__exit__(*args)

    def update(self) -> None:
        if self._live:
            self._live.update(self.progress.build_display())


def _progress_bar(pct: float, width: int = 15) -> str:
    """Simple text-based progress bar."""
    filled = int(width * pct / 100)
    empty = width - filled
    return f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim] {pct:.0f}%"


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    return f"{h}h {m}m"
