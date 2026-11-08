"""
Run artifacts: one folder per run, holding the execution trace and the cost record.

Layout::

    runs/
      latest.txt                name of the most recent run folder
      run-20261108-153022/
        trace.json              step-by-step record (ExecutionTrace)
        cost.json               TestForge's own LLM spend for the run (CostReport)
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from testforge.scenarios.models import ExecutionTrace, ScenarioResult

TRACE_FILE = "trace.json"
COST_FILE = "cost.json"
LATEST_POINTER = "latest.txt"


class RunNotFoundError(Exception):
    """Raised when a run reference does not match a recorded run."""

    pass


class LLMCall(BaseModel):
    """One LLM call made by TestForge itself, such as a judge call."""

    purpose: str = Field(min_length=1, description="What the call was for, e.g. 'judge'")
    model: str = Field(min_length=1, description="Model that handled the call")
    tokens_in: int = Field(ge=0, description="Input tokens")
    tokens_out: int = Field(ge=0, description="Output tokens")
    cost_usd: float = Field(ge=0, description="Cost of the call in USD")
    duration_sec: float = Field(ge=0, description="How long the call took")


class CostReport(BaseModel):
    """
    TestForge's own LLM spend during one run.

    The bot's own LLM calls are not measured: Telegram does not report them.
    """

    scenario_id: str = Field(description="Scenario the run belongs to")
    calls: list[LLMCall] = Field(default_factory=list, description="Every call, in order")
    total_cost_usd: float = Field(ge=0, description="Sum of the call costs")
    budget_usd: float | None = Field(
        default=None,
        gt=0,
        description="Budget for these calls, from the scenario's validation block",
    )
    budget_used: float | None = Field(
        default=None,
        ge=0,
        description="total_cost_usd / budget_usd (1.0 means the budget is used up)",
    )

    @classmethod
    def from_calls(
        cls,
        scenario_id: str,
        calls: list[LLMCall],
        budget_usd: float | None = None,
    ) -> "CostReport":
        total = sum((call.cost_usd for call in calls), 0.0)
        used = total / budget_usd if budget_usd else None
        return cls(
            scenario_id=scenario_id,
            calls=calls,
            total_cost_usd=total,
            budget_usd=budget_usd,
            budget_used=used,
        )


class RunStore:
    """Keeps one folder per run under `root` and remembers the latest one."""

    def __init__(self, root: str | Path = "runs"):
        self.root = Path(root)

    def create_run(self, now: datetime | None = None) -> Path:
        """Create runs/run-YYYYMMDD-HHMMSS/, with a numeric suffix if that name is taken."""
        stamp = (now or datetime.now()).strftime("run-%Y%m%d-%H%M%S")
        run_dir = self.root / stamp
        suffix = 1
        while run_dir.exists():
            run_dir = self.root / f"{stamp}-{suffix}"
            suffix += 1
        run_dir.mkdir(parents=True)
        return run_dir

    def save_trace(self, run_dir: Path, trace: ExecutionTrace) -> Path:
        path = run_dir / TRACE_FILE
        path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_trace(self, run_dir: Path) -> ExecutionTrace:
        text = (run_dir / TRACE_FILE).read_text(encoding="utf-8")
        return ExecutionTrace.model_validate_json(text)

    def load_cost(self, run_dir: Path) -> CostReport:
        text = (run_dir / COST_FILE).read_text(encoding="utf-8")
        return CostReport.model_validate_json(text)

    def save_cost(self, run_dir: Path, report: CostReport) -> Path:
        path = run_dir / COST_FILE
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return path

    def save_run(
        self,
        result: ScenarioResult,
        calls: list[LLMCall] | None = None,
        budget_usd: float | None = None,
        now: datetime | None = None,
    ) -> Path:
        """
        Save one finished run and mark it as the latest.

        Args:
            result: Result of ScenarioExecutor.run(); must carry a trace
            calls: TestForge's own LLM calls made for this run (judge calls)
            budget_usd: Budget for those calls, from the scenario's validation block
            now: Start time for the folder name (defaults to the current time)

        Returns:
            Path of the run folder

        Raises:
            ValueError: If the result has no trace
        """
        if result.trace is None:
            raise ValueError("result has no execution trace to save")

        run_dir = self.create_run(now)
        self.save_trace(run_dir, result.trace)
        report = CostReport.from_calls(result.scenario_id, calls or [], budget_usd)
        self.save_cost(run_dir, report)
        (self.root / LATEST_POINTER).write_text(run_dir.name, encoding="utf-8")
        return run_dir

    def resolve(self, ref: str = "latest") -> Path:
        """
        Find a run folder by name, or the latest run with ref='latest'.

        Raises:
            RunNotFoundError: If there is no such run
        """
        name = ref
        if ref == "latest":
            pointer = self.root / LATEST_POINTER
            if not pointer.exists():
                raise RunNotFoundError(f"no runs recorded in {self.root}")
            name = pointer.read_text(encoding="utf-8").strip()

        run_dir = self.root / name
        # Only direct children of the runs folder count as runs
        if run_dir.parent != self.root or not run_dir.is_dir():
            raise RunNotFoundError(f"run not found: {name}")
        return run_dir
