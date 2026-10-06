"""Tests for run comparison functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_regress.assertions import AssertionResult
from llm_regress.compare import (
    compare_runs,
    load_run_result,
    save_run_result,
)
from llm_regress.providers import ProviderResponse
from llm_regress.runner import RunResult, SuiteResult, TestResult


def make_test_result(
    name: str,
    suite: str,
    passed: bool,
    latency_ms: float = 100.0,
    cost: float = 0.001,
) -> TestResult:
    """Create a test result for testing."""
    return TestResult(
        test_name=name,
        suite_name=suite,
        passed=passed,
        response=ProviderResponse(
            content="Test response",
            model="test-model",
            latency_ms=latency_ms,
            cost_dollars=cost,
        ),
        assertions=[
            AssertionResult(
                passed=passed,
                assertion_type="contains",
                message="Test assertion",
            )
        ],
        duration_ms=latency_ms,
    )


def make_suite_result(
    name: str,
    tests: list[TestResult],
) -> SuiteResult:
    """Create a suite result for testing."""
    return SuiteResult(
        suite_name=name,
        passed=all(t.passed for t in tests),
        tests=tests,
        duration_ms=sum(t.duration_ms for t in tests),
    )


def make_run_result(
    run_id: str,
    suites: list[SuiteResult],
    metadata: dict | None = None,
) -> RunResult:
    """Create a run result for testing."""
    return RunResult(
        run_id=run_id,
        passed=all(s.passed for s in suites),
        suites=suites,
        metadata=metadata or {},
    )


class TestCompareRuns:
    """Tests for compare_runs function."""

    def test_no_changes(self) -> None:
        """Test comparison with identical runs."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        assert comparison.has_regressions is False
        assert comparison.total_regressions == 0
        assert comparison.total_improvements == 0

    def test_regression_detected(self) -> None:
        """Test that regressions are detected."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", False),
                    ],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        assert comparison.has_regressions is True
        assert comparison.total_regressions == 1
        assert comparison.exit_code == 1

    def test_improvement_detected(self) -> None:
        """Test that improvements are detected."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", False),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        assert comparison.has_regressions is False
        assert comparison.total_improvements == 1
        assert comparison.exit_code == 0

    def test_new_tests(self) -> None:
        """Test detection of new tests."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True)],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        suite_comp = comparison.suites[0]
        new_tests = [t for t in suite_comp.tests if t.status == "new"]
        assert len(new_tests) == 1
        assert new_tests[0].test_name == "test2"

    def test_removed_tests(self) -> None:
        """Test detection of removed tests."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", True),
                    ],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True)],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        suite_comp = comparison.suites[0]
        removed_tests = [t for t in suite_comp.tests if t.status == "removed"]
        assert len(removed_tests) == 1
        assert removed_tests[0].test_name == "test2"

    def test_latency_change(self) -> None:
        """Test latency change calculation."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True, latency_ms=100.0)],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True, latency_ms=150.0)],
                )
            ],
        )

        comparison = compare_runs(baseline, current)

        test_comp = comparison.suites[0].tests[0]
        assert test_comp.latency_change_pct is not None
        assert test_comp.latency_change_pct == pytest.approx(50.0)

    def test_multiple_suites(self) -> None:
        """Test comparison with multiple suites."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite1",
                    [make_test_result("test1", "Suite1", True)],
                ),
                make_suite_result(
                    "Suite2",
                    [make_test_result("test2", "Suite2", True)],
                ),
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite1",
                    [make_test_result("test1", "Suite1", False)],
                ),
                make_suite_result(
                    "Suite2",
                    [make_test_result("test2", "Suite2", True)],
                ),
            ],
        )

        comparison = compare_runs(baseline, current)

        assert len(comparison.suites) == 2
        assert comparison.total_regressions == 1


class TestSaveAndLoadRunResult:
    """Tests for save/load functionality."""

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading run results."""
        original = make_run_result(
            "test-run-123",
            [
                make_suite_result(
                    "Suite",
                    [
                        make_test_result("test1", "Suite", True),
                        make_test_result("test2", "Suite", False),
                    ],
                )
            ],
            metadata={"version": "1.0"},
        )

        file_path = tmp_path / "run.json"
        save_run_result(original, file_path)

        loaded = load_run_result(file_path)

        assert loaded.run_id == original.run_id
        assert loaded.passed == original.passed
        assert len(loaded.suites) == len(original.suites)
        assert loaded.suites[0].suite_name == original.suites[0].suite_name
        assert len(loaded.suites[0].tests) == 2
        assert loaded.metadata["version"] == "1.0"

    def test_load_creates_valid_objects(self, tmp_path: Path) -> None:
        """Test that loaded objects have correct types."""
        original = make_run_result(
            "test",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True)],
                )
            ],
        )

        file_path = tmp_path / "run.json"
        save_run_result(original, file_path)

        loaded = load_run_result(file_path)

        assert isinstance(loaded, RunResult)
        assert isinstance(loaded.suites[0], SuiteResult)
        assert isinstance(loaded.suites[0].tests[0], TestResult)


class TestRunComparison:
    """Tests for RunComparison dataclass."""

    def test_to_dict(self) -> None:
        """Test converting comparison to dict."""
        baseline = make_run_result(
            "baseline",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", True)],
                )
            ],
        )
        current = make_run_result(
            "current",
            [
                make_suite_result(
                    "Suite",
                    [make_test_result("test1", "Suite", False)],
                )
            ],
        )

        comparison = compare_runs(baseline, current)
        data = comparison.to_dict()

        assert data["baseline_run_id"] == "baseline"
        assert data["current_run_id"] == "current"
        assert data["has_regressions"] is True
        assert "suites" in data
