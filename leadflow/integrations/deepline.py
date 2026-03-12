"""Deepline integration — waterfall enrichment across 15+ data providers.

Deepline (https://code.deepline.com/) provides:
- Waterfall enrichment across Apollo, Crustdata, Hunter, PDL, LeadMagic, etc.
- BYOK (Bring Your Own Keys) tier is FREE — you pay providers directly
- Auto-routing to best-performing providers for your target market
- Smartlead integration built-in

Usage:
    Install Deepline CLI: curl -s "https://code.deepline.com/api/v2/cli/install" | bash
    Authenticate: deepline auth login

This module wraps the Deepline CLI for use as a pipeline enrichment step.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from leadflow.config import CampaignConfig
from leadflow.enrichments.base import EnrichmentStep
from leadflow.utils.logger import get_logger

log = get_logger(__name__)


def is_deepline_installed() -> bool:
    """Check if Deepline CLI is available."""
    return shutil.which("deepline") is not None


async def _run_deepline(args: list[str], timeout: float = 30.0) -> dict:
    """Run a Deepline CLI command and return parsed JSON output."""
    cmd = ["deepline"] + args + ["--json"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise TimeoutError(f"Deepline command timed out: {' '.join(cmd)}")

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() if stderr else "Unknown error"
        raise RuntimeError(f"Deepline error (exit {proc.returncode}): {error_msg}")

    output = stdout.decode().strip()
    if not output:
        return {}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        # Sometimes output has extra lines before JSON
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("{") or line.startswith("["):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        log.warning(f"Could not parse Deepline output: {output[:200]}")
        return {"raw_output": output}


async def enrich_email(email: str) -> dict:
    """Enrich a single email address via Deepline waterfall."""
    return await _run_deepline(["enrich", email])


async def enrich_person(
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    company: str | None = None,
    linkedin: str | None = None,
) -> dict:
    """Enrich a person with available identifiers."""
    args = ["enrich"]

    if email:
        args.extend(["--email", email])
    if first_name:
        args.extend(["--first-name", first_name])
    if last_name:
        args.extend(["--last-name", last_name])
    if company:
        args.extend(["--company", company])
    if linkedin:
        args.extend(["--linkedin", linkedin])

    if len(args) == 1:
        raise ValueError("At least one identifier required for enrichment")

    return await _run_deepline(args, timeout=45.0)


async def enrich_company(domain: str) -> dict:
    """Enrich company data by domain."""
    return await _run_deepline(["enrich", "--domain", domain], timeout=30.0)


class DeeplineEnrichmentStep(EnrichmentStep):
    """Pipeline step that enriches leads via Deepline waterfall.

    Pulls contact data (verified emails, phones, social profiles) and
    company data (employee count, revenue, tech stack) from 15+ providers.
    """

    name = "deepline_enrich"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        if not is_deepline_installed():
            log.warning("Deepline CLI not installed. Skipping enrichment.")
            return {}

        email = lead.get("email") or lead.get("raw_email")
        first_name = lead.get("raw_first_name") or lead.get("first_name")
        last_name = lead.get("raw_last_name") or lead.get("last_name")
        company = lead.get("raw_company") or lead.get("company_name")
        linkedin = lead.get("raw_linkedin") or lead.get("linkedin_url")

        try:
            data = await enrich_person(
                email=email,
                first_name=first_name,
                last_name=last_name,
                company=company,
                linkedin=linkedin,
            )
        except Exception as e:
            log.warning(f"[deepline] Enrichment failed for {email}: {e}")
            return {}

        # Map Deepline response to our lead fields
        result: dict[str, Any] = {}

        if data.get("email") and not email:
            result["email"] = data["email"]
        if data.get("phone"):
            result["phone"] = data["phone"]
        if data.get("linkedin_url"):
            result["linkedin_url"] = data["linkedin_url"]
        if data.get("title") or data.get("job_title"):
            result["job_title"] = data.get("title") or data.get("job_title")
        if data.get("location") or data.get("city"):
            result["location"] = data.get("location") or data.get("city")

        # Company data
        if data.get("company_name"):
            result["company_name"] = data["company_name"]
        if data.get("company_domain") or data.get("website"):
            result["website"] = data.get("company_domain") or data.get("website")
        if data.get("industry"):
            result["industry"] = data["industry"]
        if data.get("employee_count"):
            result["company_employee_count"] = str(data["employee_count"])

        # Store full Deepline response in raw_extra for reference
        existing_extra = lead.get("raw_extra") or {}
        if isinstance(existing_extra, str):
            try:
                existing_extra = json.loads(existing_extra)
            except json.JSONDecodeError:
                existing_extra = {}

        existing_extra["deepline"] = data
        result["raw_extra"] = json.dumps(existing_extra)

        log.info(f"[deepline] Enriched {email}: {len(result) - 1} fields updated")
        return result
