"""The results of one dam's analysis (steps 4 to 7), held apart from the widgets that show them.

A `DamRun` belongs to the dam it was made for, so a result can not be read for another dam. Later steps and the export
take their inputs from it and not from the steps before them.
"""

from typing import Any, Dict, Optional, Tuple

from src.services.bedload import BedloadResult
from src.services.integration import IntegrationResult
from src.services.project import Dam
from src.services.reservoir import CurveResult
from src.services.suspended import SuspendedResult

SUSPENDED, BEDLOAD, CURVE, INTEGRATION = "suspended", "bedload", "curve", "integration"
STAGES = (SUSPENDED, BEDLOAD, CURVE, INTEGRATION)
_NAMES = {
    SUSPENDED: "suspended sediment",
    BEDLOAD: "bedload",
    CURVE: "reservoir curve",
    INTEGRATION: "integration and projection",
}


class DamRun:
    def __init__(self, dam: Dam):
        self.dam = dam
        self._results: Dict[str, Any] = {}

    def get(self, stage: str) -> Optional[Any]:
        if stage not in STAGES:
            raise KeyError(stage)
        return self._results.get(stage)

    def set(self, stage: str, result: Optional[Any]) -> None:
        """Keep the result of a stage; None removes it."""
        if stage not in STAGES:
            raise KeyError(stage)
        if result is None:
            self._results.pop(stage, None)
        else:
            self._results[stage] = result

    @property
    def suspended(self) -> Optional[SuspendedResult]:
        return self.get(SUSPENDED)

    @property
    def bedload(self) -> Optional[BedloadResult]:
        return self.get(BEDLOAD)

    @property
    def curve(self) -> Optional[CurveResult]:
        return self.get(CURVE)

    @property
    def integration(self) -> Optional[IntegrationResult]:
        return self.get(INTEGRATION)

    def require(self, *stages: str) -> None:
        """Raises ValueError naming every stage in `stages` that has no result yet."""
        missing = [_NAMES[stage] for stage in stages if self.get(stage) is None]
        if missing:
            raise ValueError(f"Compute the {', '.join(missing)} of {self.dam.name} first.")

    def results(self) -> Tuple[SuspendedResult, BedloadResult, CurveResult, IntegrationResult]:
        """The four results, for the report. Raises ValueError if one is missing."""
        self.require(*STAGES)
        return self.suspended, self.bedload, self.curve, self.integration
