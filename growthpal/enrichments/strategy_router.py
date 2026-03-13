"""Strategy routing — evaluate signal conditions and assign leads to strategies.

Sits between signal_detection and email_generation in the pipeline.
Routes leads to signal-based strategies (first match wins by priority)
or fallback strategies (random equal split / optimization 80/20).

Config format in campaign YAML under `strategy_routing`:

strategy_routing:
  mode: "testing"  # "testing" | "optimization"
  optimization_winner: null
  optimization_split: 0.80
  strategies:
    - id: "hiring-angle"
      type: "signal"
      priority: 1
      conditions:
        - field: "hiring_signal.roles"
          operator: "not_empty"
      smartlead_campaign_id: 12345
      email_prompt: |
        Write a cold email leading with hiring...
    - id: "case-study"
      type: "fallback"
      smartlead_campaign_id: 12350
      email_prompt: |
        Write leading with a relevant case study...
"""

from __future__ import annotations

import json
import random
from typing import Any

from growthpal.config import CampaignConfig
from growthpal.enrichments.base import EnrichmentStep
from growthpal.pipeline.registry import register
from growthpal.utils.logger import get_logger

log = get_logger(__name__)


def resolve_field(lead: dict, field_path: str) -> Any:
    """Resolve a dot-notation field path from a lead dict.

    Handles JSONB string fields by parsing them automatically.
    e.g. resolve_field(lead, "hiring_signal.roles") ->
         lead["hiring_signal"]["roles"]
    """
    parts = field_path.split(".")
    current: Any = lead

    for part in parts:
        if current is None:
            return None

        # Auto-parse JSON strings
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (json.JSONDecodeError, TypeError):
                return None

        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            # Support numeric index for lists
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None

    # Final auto-parse for JSONB strings
    if isinstance(current, str):
        try:
            parsed = json.loads(current)
            if isinstance(parsed, (dict, list)):
                current = parsed
        except (json.JSONDecodeError, TypeError):
            pass

    return current


def _is_truthy(value: Any) -> bool:
    """Check if a value is truthy (not None, not empty string/list/dict, not 0)."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip() not in ("[]", "{}", "null")
    if isinstance(value, (list, dict)):
        return bool(value)
    return bool(value)


def evaluate_condition(lead: dict, condition: dict) -> bool:
    """Evaluate a single condition against a lead."""
    field_path = condition.get("field", "")
    operator = condition.get("operator", "not_empty")
    cond_value = condition.get("value")

    value = resolve_field(lead, field_path)

    if operator == "not_empty":
        return _is_truthy(value)

    if operator == "empty":
        return not _is_truthy(value)

    if operator == "eq":
        return value == cond_value

    if operator == "neq":
        return value != cond_value

    if operator == "contains":
        if isinstance(value, str):
            return str(cond_value).lower() in value.lower()
        if isinstance(value, list):
            return cond_value in value
        return False

    if operator == "contains_any":
        if not isinstance(cond_value, list):
            cond_value = [cond_value]
        if isinstance(value, str):
            return any(str(v).lower() in value.lower() for v in cond_value)
        if isinstance(value, list):
            value_lower = [str(v).lower() if isinstance(v, str) else v for v in value]
            return any(
                (str(v).lower() if isinstance(v, str) else v) in value_lower
                for v in cond_value
            )
        return False

    if operator in ("gt", "gte", "lt", "lte"):
        try:
            num_value = float(value) if value is not None else None
            num_cond = float(cond_value)
        except (ValueError, TypeError):
            return False
        if num_value is None:
            return False
        if operator == "gt":
            return num_value > num_cond
        if operator == "gte":
            return num_value >= num_cond
        if operator == "lt":
            return num_value < num_cond
        if operator == "lte":
            return num_value <= num_cond

    if operator == "in":
        if isinstance(cond_value, list):
            return value in cond_value
        return False

    log.warning(f"Unknown condition operator: {operator}")
    return False


def evaluate_conditions(lead: dict, conditions: list[dict]) -> bool:
    """Evaluate ALL conditions (AND logic). Returns True if all match."""
    if not conditions:
        return False
    return all(evaluate_condition(lead, c) for c in conditions)


def extract_matched_values(lead: dict, conditions: list[dict]) -> dict[str, Any]:
    """Extract the matched field values for use in template rendering.

    Returns a dict like {"matched_hiring_roles": [...], "matched_funding_stage": "Series A"}
    """
    matched = {}
    for condition in conditions:
        field_path = condition.get("field", "")
        value = resolve_field(lead, field_path)
        # Create a template-friendly key: hiring_signal.roles -> matched_hiring_signal_roles
        key = "matched_" + field_path.replace(".", "_")
        matched[key] = value
    return matched


def select_fallback(
    fallbacks: list[dict],
    mode: str,
    config: dict,
) -> dict | None:
    """Select a fallback strategy based on mode.

    - testing: random equal distribution
    - optimization: 80/20 (or configured split) winner vs rest
    """
    if not fallbacks:
        return None

    if mode == "optimization":
        winner_id = config.get("optimization_winner")
        split = config.get("optimization_split", 0.80)

        if winner_id:
            winner = next((f for f in fallbacks if f["id"] == winner_id), None)
            others = [f for f in fallbacks if f["id"] != winner_id]

            if winner and random.random() < split:
                return winner
            elif others:
                return random.choice(others)
            elif winner:
                return winner

    # Default: testing mode — equal random distribution
    return random.choice(fallbacks)


def get_strategy_config(campaign_config: CampaignConfig) -> dict:
    """Extract strategy_routing config from CampaignConfig."""
    return getattr(campaign_config, "strategy_routing", None) or {}


def get_strategy_by_id(campaign_config: CampaignConfig, strategy_id: str) -> dict | None:
    """Look up a strategy by ID from campaign config."""
    sr = get_strategy_config(campaign_config)
    for strategy in sr.get("strategies", []):
        if strategy.get("id") == strategy_id:
            return strategy
    return None


@register
class StrategyRoutingStep(EnrichmentStep):
    """Evaluate strategy conditions and assign each lead to a strategy.

    Signal strategies are checked in priority order (first match wins).
    Unmatched leads go to fallback strategies (random or optimization split).
    No-op if strategy_routing is not configured.
    """

    name = "strategy_routing"

    async def process(self, lead: dict, campaign_config: CampaignConfig) -> dict[str, Any]:
        sr = get_strategy_config(campaign_config)
        if not sr or not sr.get("strategies"):
            # No strategy config — no-op, backward compatible
            return {
                "_model": None,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        strategies = sr["strategies"]
        mode = sr.get("mode", "testing")

        # Separate signal vs fallback strategies
        signal_strategies = sorted(
            [s for s in strategies if s.get("type") == "signal"],
            key=lambda s: s.get("priority", 999),
        )
        fallback_strategies = [s for s in strategies if s.get("type") == "fallback"]

        # Try signal strategies in priority order (first match wins)
        for strategy in signal_strategies:
            conditions = strategy.get("conditions", [])
            if evaluate_conditions(lead, conditions):
                matched = extract_matched_values(lead, conditions)
                log.info(
                    f"[strategy_routing] Lead {lead.get('email', '?')} → "
                    f"signal strategy '{strategy['id']}'"
                )
                return {
                    "strategy_id": strategy["id"],
                    "strategy_name": strategy.get("name", strategy["id"]),
                    "_strategy_matched_values": matched,  # Popped by email gen, not persisted
                    "_model": None,
                    "_input_tokens": 0,
                    "_output_tokens": 0,
                    "_cost": 0.0,
                }

        # No signal matched — use fallback
        fallback = select_fallback(fallback_strategies, mode, sr)
        if fallback:
            log.info(
                f"[strategy_routing] Lead {lead.get('email', '?')} → "
                f"fallback strategy '{fallback['id']}' (mode={mode})"
            )
            return {
                "strategy_id": fallback["id"],
                "strategy_name": fallback.get("name", fallback["id"]),
                "_model": None,
                "_input_tokens": 0,
                "_output_tokens": 0,
                "_cost": 0.0,
            }

        # No strategies matched at all (shouldn't happen if config has fallbacks)
        log.warning(
            f"[strategy_routing] No strategy matched for lead {lead.get('email', '?')}"
        )
        return {
            "_model": None,
            "_input_tokens": 0,
            "_output_tokens": 0,
            "_cost": 0.0,
        }
