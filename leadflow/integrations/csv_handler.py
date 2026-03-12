"""CSV import and export for leads."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from leadflow.constants import PipelineStatus
from leadflow.db import queries as db
from leadflow.utils.logger import get_logger

log = get_logger(__name__)

# Map common CSV column names to our raw_ fields
COLUMN_MAPPING = {
    "email": "raw_email",
    "e-mail": "raw_email",
    "email_address": "raw_email",
    "first_name": "raw_first_name",
    "firstname": "raw_first_name",
    "first name": "raw_first_name",
    "last_name": "raw_last_name",
    "lastname": "raw_last_name",
    "last name": "raw_last_name",
    "company": "raw_company",
    "company_name": "raw_company",
    "organization": "raw_company",
    "title": "raw_title",
    "job_title": "raw_title",
    "jobtitle": "raw_title",
    "position": "raw_title",
    "website": "raw_website",
    "company_website": "raw_website",
    "url": "raw_website",
    "domain": "raw_website",
    "linkedin": "raw_linkedin",
    "linkedin_url": "raw_linkedin",
    "linkedin_profile": "raw_linkedin",
    "phone": "raw_phone",
    "phone_number": "raw_phone",
    "location": "raw_location",
    "city": "raw_location",
    "industry": "raw_industry",
}

# Fields we export
EXPORT_FIELDS = [
    "email", "first_name", "last_name", "company_name", "job_title",
    "website", "linkedin_url", "phone", "location", "industry",
    "company_summary", "company_employee_count", "company_funding",
    "icp_qualified", "icp_reason", "title_relevant",
    "email_subject", "email_body",
    "pipeline_status",
]


def import_csv(
    file_path: str | Path,
    campaign_id: str,
    batch_size: int = 500,
) -> int:
    """Import leads from a CSV file into the database.

    Returns:
        Number of leads imported.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    total = 0
    batch: list[dict] = []

    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        for row in reader:
            lead = _map_row(row, campaign_id)
            if not lead.get("raw_email"):
                continue  # Skip rows without email

            batch.append(lead)

            if len(batch) >= batch_size:
                db.insert_leads(batch)
                total += len(batch)
                log.info(f"Imported {total} leads...")
                batch = []

        # Insert remaining
        if batch:
            db.insert_leads(batch)
            total += len(batch)

    log.info(f"Import complete: {total} leads from {file_path.name}")
    return total


def _map_row(row: dict, campaign_id: str) -> dict:
    """Map a CSV row to our lead schema."""
    lead: dict[str, Any] = {
        "campaign_id": campaign_id,
        "pipeline_status": PipelineStatus.IMPORTED.value,
    }

    extra: dict[str, str] = {}

    for col_name, value in row.items():
        if not value or not value.strip():
            continue

        normalized = col_name.strip().lower().replace(" ", "_")
        mapped = COLUMN_MAPPING.get(normalized)

        if mapped:
            lead[mapped] = value.strip()
        else:
            extra[col_name] = value.strip()

    if extra:
        lead["raw_extra"] = extra

    # Copy raw email to email field for lookups
    if "raw_email" in lead:
        lead["email"] = lead["raw_email"]

    return lead


def export_csv(
    campaign_id: str,
    output_path: str | Path,
    statuses: list[PipelineStatus] | None = None,
) -> int:
    """Export enriched leads to CSV.

    Returns:
        Number of leads exported.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    statuses = statuses or [
        PipelineStatus.ENRICHED,
        PipelineStatus.QUALIFIED,
        PipelineStatus.EMAIL_GENERATED,
        PipelineStatus.PUSHED,
    ]

    leads = db.get_leads_by_status(campaign_id, statuses, limit=999999)

    if not leads:
        log.info("No leads to export.")
        return 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({k: lead.get(k, "") for k in EXPORT_FIELDS})

    log.info(f"Exported {len(leads)} leads to {output_path}")
    return len(leads)
