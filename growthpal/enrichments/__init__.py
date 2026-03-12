"""Auto-register all enrichment steps on import."""

from growthpal.enrichments import (  # noqa: F401
    company_research,
    email_finding,
    email_generation,
    email_verification,
    icp_qualification,
    job_title_cleaning,
    job_title_icp,
    name_cleaning,
    signal_detection,
)
