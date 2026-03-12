"""Enrichment step registry — maps step names to classes."""

from __future__ import annotations

from leadflow.enrichments.base import EnrichmentStep

_registry: dict[str, type[EnrichmentStep]] = {}

# Ordered list of all steps in pipeline order
# ICP check BEFORE email finding to save credits on disqualified leads
PIPELINE_ORDER: list[str] = [
    "company_research",       # 1. Scrape website + AI summary
    "icp_qualification",      # 2. GATE: company matches ICP?
    "email_finding",          # 3. Waterfall: Prospeo → TryKitt → BetterContact
    "email_verification",     # 4. GATE: Reoon → BounceBan (skip for BetterContact)
    "job_title_cleaning",     # 5. Normalize job titles
    "name_cleaning",          # 6. Clean names + company
    "job_title_icp",          # 7. GATE: role relevance check
    "signal_detection",       # 8. Tech/funding/hiring signals
    "email_generation",       # 9. Generate cold email copy
]


def register(step_class: type[EnrichmentStep]) -> type[EnrichmentStep]:
    """Decorator to register an enrichment step."""
    _registry[step_class.name] = step_class
    return step_class


def get_step(name: str) -> EnrichmentStep:
    if name not in _registry:
        raise ValueError(f"Unknown enrichment step: {name}. Available: {list(_registry.keys())}")
    return _registry[name]()


def get_all_steps() -> list[EnrichmentStep]:
    return [get_step(name) for name in PIPELINE_ORDER if name in _registry]


def get_steps(names: list[str]) -> list[EnrichmentStep]:
    if "all" in names:
        return get_all_steps()
    return [get_step(name) for name in names]


def build_pipeline(
    step_names: list[str],
    campaign_config: "CampaignConfig | None" = None,
) -> list[EnrichmentStep]:
    """Build the full pipeline with built-in, custom AI, and Deepline steps.

    This is the main entry point for constructing a pipeline. It:
    1. Gets the requested built-in steps
    2. Injects Deepline enrichment if enabled
    3. Injects custom AI steps from campaign config
    """
    from leadflow.config import CampaignConfig

    steps = get_steps(step_names)

    if campaign_config is None:
        return steps

    # Inject Deepline step if enabled
    if campaign_config.use_deepline:
        from leadflow.integrations.deepline import DeeplineEnrichmentStep, is_deepline_installed

        if is_deepline_installed():
            deepline_step = DeeplineEnrichmentStep()
            insert_at = campaign_config.deepline_before_step
            steps = _insert_before(steps, insert_at, deepline_step)
        else:
            from leadflow.utils.logger import get_logger
            get_logger(__name__).warning(
                "Deepline enabled but CLI not installed. "
                "Install: curl -s 'https://code.deepline.com/api/v2/cli/install' | bash"
            )

    # Inject custom AI steps if defined
    if campaign_config.custom_ai_steps:
        from leadflow.enrichments.custom_ai import load_custom_steps

        custom_steps = load_custom_steps(campaign_config)
        if custom_steps:
            insert_after = campaign_config.custom_ai_after_step
            steps = _insert_after(steps, insert_after, custom_steps)

    return steps


def _insert_before(
    steps: list[EnrichmentStep], before_name: str, new_step: EnrichmentStep
) -> list[EnrichmentStep]:
    """Insert a step before a named step, or at the start if not found."""
    for i, s in enumerate(steps):
        if s.name == before_name:
            steps.insert(i, new_step)
            return steps
    steps.insert(0, new_step)
    return steps


def _insert_after(
    steps: list[EnrichmentStep], after_name: str, new_steps: list[EnrichmentStep]
) -> list[EnrichmentStep]:
    """Insert steps after a named step, or at the end if not found."""
    for i, s in enumerate(steps):
        if s.name == after_name:
            for j, ns in enumerate(new_steps):
                steps.insert(i + 1 + j, ns)
            return steps
    steps.extend(new_steps)
    return steps


def list_step_names() -> list[str]:
    return list(_registry.keys())
