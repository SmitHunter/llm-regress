"""Compare test runs to detect regressions between versions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llm_regress.runner import RunResult, SuiteResult, TestResult


@dataclass
class TestComparison:
    """Comparison of a single test between two runs."""

    test_name: str
    suite_name: str
    baseline_passed: bool | None
    current_passed: bool | None
    status: str  # "improved", "regressed", "unchanged", "new", "removed"
    baseline_latency_ms: float | None = None
    current_latency_ms: float | None = None
    latency_change_pct: float | None = None
    baseline_cost: float | None = None
    current_cost: float | None = None
    cost_change_pct: float | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_regression(self) -> bool:
        """Check if this represents a regression."""
        return self.status == "regressed"

    @property
    def is_improvement(self) -> bool:
        """Check if this represents an improvement."""
        return self.status == "improved"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_name": self.test_name,
            "suite_name": self.suite_name,
            "status": self.status,
            "baseline_passed": self.baseline_passed,
            "current_passed": self.current_passed,
            "latency_change_pct": self.latency_change_pct,
            "cost_change_pct": self.cost_change_pct,
            "details": self.details,
        }


@dataclass
class SuiteComparison:
    """Comparison of a test suite between two runs."""

    suite_name: str
    tests: list[TestComparison]
    baseline_passed: int
    baseline_failed: int
    current_passed: int
    current_failed: int
    regressions: int
    improvements: int
    new_tests: int
    removed_tests: int

    @property
    def has_regressions(self) -> bool:
        """Check if suite has any regressions."""
        return self.regressions > 0

    @property
    def net_change(self) -> int:
        """Net change in passing tests (positive = improvement)."""
        return self.improvements - self.regressions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "suite_name": self.suite_name,
            "baseline": {"passed": self.baseline_passed, "failed": self.baseline_failed},
            "current": {"passed": self.current_passed, "failed": self.current_failed},
            "regressions": self.regressions,
            "improvements": self.improvements,
            "new_tests": self.new_tests,
            "removed_tests": self.removed_tests,
            "net_change": self.net_change,
            "tests": [t.to_dict() for t in self.tests],
        }


@dataclass
class RunComparison:
    """Full comparison between two test runs."""

    baseline_run_id: str
    current_run_id: str
    suites: list[SuiteComparison]
    total_regressions: int
    total_improvements: int
    has_regressions: bool
    baseline_metadata: dict[str, Any] = field(default_factory=dict)
    current_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        """Get CI exit code (0 = no regressions, 1 = has regressions)."""
        return 1 if self.has_regressions else 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "baseline_run_id": self.baseline_run_id,
            "current_run_id": self.current_run_id,
            "has_regressions": self.has_regressions,
            "total_regressions": self.total_regressions,
            "total_improvements": self.total_improvements,
            "baseline_metadata": self.baseline_metadata,
            "current_metadata": self.current_metadata,
            "suites": [s.to_dict() for s in self.suites],
        }


def _compare_tests(
    baseline: TestResult | None,
    current: TestResult | None,
    suite_name: str,
) -> TestComparison:
    """Compare two test results."""
    if baseline is None and current is not None:
        return TestComparison(
            test_name=current.test_name,
            suite_name=suite_name,
            baseline_passed=None,
            current_passed=current.passed,
            status="new",
            current_latency_ms=current.response.latency_ms if current.response else None,
            current_cost=current.response.cost_dollars if current.response else None,
        )

    if baseline is not None and current is None:
        return TestComparison(
            test_name=baseline.test_name,
            suite_name=suite_name,
            baseline_passed=baseline.passed,
            current_passed=None,
            status="removed",
            baseline_latency_ms=baseline.response.latency_ms if baseline.response else None,
            baseline_cost=baseline.response.cost_dollars if baseline.response else None,
        )

    assert baseline is not None and current is not None

    if baseline.passed and not current.passed:
        status = "regressed"
    elif not baseline.passed and current.passed:
        status = "improved"
    else:
        status = "unchanged"

    baseline_latency = baseline.response.latency_ms if baseline.response else None
    current_latency = current.response.latency_ms if current.response else None
    latency_change = None
    if baseline_latency and current_latency and baseline_latency > 0:
        latency_change = ((current_latency - baseline_latency) / baseline_latency) * 100

    baseline_cost = baseline.response.cost_dollars if baseline.response else None
    current_cost = current.response.cost_dollars if current.response else None
    cost_change = None
    if baseline_cost and current_cost and baseline_cost > 0:
        cost_change = ((current_cost - baseline_cost) / baseline_cost) * 100

    details: dict[str, Any] = {}
    if status == "regressed" and current.failed_assertions:
        details["failed_assertions"] = [
            {"type": a.assertion_type, "message": a.message} for a in current.failed_assertions
        ]

    return TestComparison(
        test_name=baseline.test_name,
        suite_name=suite_name,
        baseline_passed=baseline.passed,
        current_passed=current.passed,
        status=status,
        baseline_latency_ms=baseline_latency,
        current_latency_ms=current_latency,
        latency_change_pct=latency_change,
        baseline_cost=baseline_cost,
        current_cost=current_cost,
        cost_change_pct=cost_change,
        details=details,
    )


def _compare_suites(
    baseline: SuiteResult | None,
    current: SuiteResult | None,
) -> SuiteComparison | None:
    """Compare two suite results."""
    if baseline is None and current is None:
        return None

    if baseline is not None:
        suite_name = baseline.suite_name
    elif current is not None:
        suite_name = current.suite_name
    else:
        suite_name = ""

    baseline_tests = {t.test_name: t for t in baseline.tests} if baseline else {}
    current_tests = {t.test_name: t for t in current.tests} if current else {}

    all_test_names = set(baseline_tests.keys()) | set(current_tests.keys())

    comparisons: list[TestComparison] = []
    regressions = 0
    improvements = 0
    new_tests = 0
    removed_tests = 0

    for test_name in sorted(all_test_names):
        b_test = baseline_tests.get(test_name)
        c_test = current_tests.get(test_name)
        comparison = _compare_tests(b_test, c_test, suite_name)
        comparisons.append(comparison)

        if comparison.status == "regressed":
            regressions += 1
        elif comparison.status == "improved":
            improvements += 1
        elif comparison.status == "new":
            new_tests += 1
        elif comparison.status == "removed":
            removed_tests += 1

    return SuiteComparison(
        suite_name=suite_name,
        tests=comparisons,
        baseline_passed=baseline.passed_count if baseline else 0,
        baseline_failed=baseline.failed_count if baseline else 0,
        current_passed=current.passed_count if current else 0,
        current_failed=current.failed_count if current else 0,
        regressions=regressions,
        improvements=improvements,
        new_tests=new_tests,
        removed_tests=removed_tests,
    )


def compare_runs(baseline: RunResult, current: RunResult) -> RunComparison:
    """Compare two test runs to identify regressions.

    Args:
        baseline: The baseline run to compare against.
        current: The current run to compare.

    Returns:
        RunComparison with detailed comparison results.
    """
    baseline_suites = {s.suite_name: s for s in baseline.suites}
    current_suites = {s.suite_name: s for s in current.suites}

    all_suite_names = set(baseline_suites.keys()) | set(current_suites.keys())

    suite_comparisons: list[SuiteComparison] = []
    total_regressions = 0
    total_improvements = 0

    for suite_name in sorted(all_suite_names):
        b_suite = baseline_suites.get(suite_name)
        c_suite = current_suites.get(suite_name)
        comparison = _compare_suites(b_suite, c_suite)
        if comparison:
            suite_comparisons.append(comparison)
            total_regressions += comparison.regressions
            total_improvements += comparison.improvements

    return RunComparison(
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        suites=suite_comparisons,
        total_regressions=total_regressions,
        total_improvements=total_improvements,
        has_regressions=total_regressions > 0,
        baseline_metadata=baseline.metadata,
        current_metadata=current.metadata,
    )


def load_run_result(path: Path | str) -> RunResult:
    """Load a RunResult from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Loaded RunResult object.
    """
    from llm_regress.assertions import AssertionResult
    from llm_regress.providers import ProviderResponse

    path = Path(path)
    data = json.loads(path.read_text())

    suites = []
    for suite_data in data.get("suites", []):
        tests = []
        for test_data in suite_data.get("tests", []):
            response_data = test_data.get("response", {})
            response = (
                ProviderResponse(
                    content=response_data.get("content", ""),
                    model=response_data.get("model", ""),
                    latency_ms=response_data.get("latency_ms", 0),
                    input_tokens=response_data.get("input_tokens", 0),
                    output_tokens=response_data.get("output_tokens", 0),
                    cost_dollars=response_data.get("cost_dollars", 0),
                )
                if response_data.get("content")
                else None
            )

            assertions = [
                AssertionResult(
                    passed=a.get("passed", False),
                    assertion_type=a.get("type", ""),
                    message=a.get("message", ""),
                    expected=a.get("expected"),
                    actual=a.get("actual"),
                )
                for a in test_data.get("assertions", [])
            ]

            tests.append(
                TestResult(
                    test_name=test_data.get("test_name", ""),
                    suite_name=test_data.get("suite_name", ""),
                    passed=test_data.get("passed", False),
                    response=response,
                    assertions=assertions,
                    error=test_data.get("error"),
                    duration_ms=test_data.get("duration_ms", 0),
                    cached=test_data.get("cached", False),
                )
            )

        suites.append(
            SuiteResult(
                suite_name=suite_data.get("suite_name", ""),
                passed=suite_data.get("passed", False),
                tests=tests,
                duration_ms=suite_data.get("duration_ms", 0),
                started_at=suite_data.get("started_at", ""),
                finished_at=suite_data.get("finished_at", ""),
            )
        )

    return RunResult(
        run_id=data.get("run_id", ""),
        passed=data.get("passed", False),
        suites=suites,
        duration_ms=data.get("duration_ms", 0),
        started_at=data.get("started_at", ""),
        finished_at=data.get("finished_at", ""),
        metadata=data.get("metadata", {}),
    )


def save_run_result(result: RunResult, path: Path | str) -> None:
    """Save a RunResult to a JSON file.

    Args:
        result: The RunResult to save.
        path: Path to save to.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2))
