"""Track API costs per lead and enrichment step."""

from dataclasses import dataclass, field

from leadflow.constants import MODEL_COSTS, Model
from leadflow.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class StepCost:
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost(self) -> float:
        rates = MODEL_COSTS.get(self.model, MODEL_COSTS[Model.GPT4O])
        return (self.input_tokens * rates["input"] + self.output_tokens * rates["output"]) / 1_000_000


@dataclass
class CostTracker:
    """Accumulate costs across a pipeline run."""

    steps: dict[str, list[StepCost]] = field(default_factory=dict)

    def record(self, step_name: str, model: str, input_tokens: int, output_tokens: int) -> float:
        cost_entry = StepCost(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        self.steps.setdefault(step_name, []).append(cost_entry)
        return cost_entry.cost

    @property
    def total_cost(self) -> float:
        return sum(c.cost for costs in self.steps.values() for c in costs)

    @property
    def total_tokens(self) -> dict[str, int]:
        inp = sum(c.input_tokens for costs in self.steps.values() for c in costs)
        out = sum(c.output_tokens for costs in self.steps.values() for c in costs)
        return {"input": inp, "output": out}

    def summary(self) -> dict[str, dict]:
        result = {}
        for step, costs in self.steps.items():
            result[step] = {
                "calls": len(costs),
                "input_tokens": sum(c.input_tokens for c in costs),
                "output_tokens": sum(c.output_tokens for c in costs),
                "cost": sum(c.cost for c in costs),
            }
        result["_total"] = {
            "calls": sum(len(c) for c in self.steps.values()),
            **self.total_tokens,
            "cost": self.total_cost,
        }
        return result

    def print_summary(self) -> None:
        from rich.table import Table
        from leadflow.utils.logger import console

        table = Table(title="Cost Summary")
        table.add_column("Step", style="cyan")
        table.add_column("Calls", justify="right")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        table.add_column("Cost ($)", justify="right", style="green")

        for step, data in self.summary().items():
            if step == "_total":
                continue
            table.add_row(
                step,
                str(data["calls"]),
                f"{data['input_tokens']:,}",
                f"{data['output_tokens']:,}",
                f"${data['cost']:.4f}",
            )

        total = self.summary()["_total"]
        table.add_section()
        table.add_row(
            "TOTAL",
            str(total["calls"]),
            f"{total['input']:,}",
            f"{total['output']:,}",
            f"${total['cost']:.4f}",
            style="bold",
        )
        console.print(table)
