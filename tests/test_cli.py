"""Tests for the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from llm_regress.cli import main


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def test_suite_file(tmp_path: Path) -> Path:
    """Create a test suite file."""
    content = """
name: CLI Test Suite
provider: mock

tests:
  - name: Simple Test
    prompt: What is the capital of France?
    assertions:
      - type: contains
        value: Paris
"""
    file_path = tmp_path / "suite.yaml"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def failing_suite_file(tmp_path: Path) -> Path:
    """Create a failing test suite file."""
    content = """
name: Failing Suite
provider: mock

tests:
  - name: Impossible Test
    prompt: Hello
    assertions:
      - type: exact
        value: THIS_WILL_NEVER_MATCH_EXACTLY
"""
    file_path = tmp_path / "failing.yaml"
    file_path.write_text(content)
    return file_path


class TestRunCommand:
    """Tests for the run command."""

    def test_run_simple_suite(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test running a simple suite."""
        result = runner.invoke(main, ["run", str(test_suite_file)])
        assert result.exit_code == 0
        assert "CLI Test Suite" in result.output
        assert "PASSED" in result.output

    def test_run_failing_suite(self, runner: CliRunner, failing_suite_file: Path) -> None:
        """Test running a failing suite returns exit code 1."""
        result = runner.invoke(main, ["run", str(failing_suite_file)])
        assert result.exit_code == 1
        assert "FAILED" in result.output

    def test_run_with_json_output(
        self, runner: CliRunner, test_suite_file: Path, tmp_path: Path
    ) -> None:
        """Test running with JSON output."""
        output_file = tmp_path / "results.json"
        result = runner.invoke(main, ["run", str(test_suite_file), "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

        data = json.loads(output_file.read_text())
        assert data["passed"] is True
        assert "suites" in data

    def test_run_with_html_output(
        self, runner: CliRunner, test_suite_file: Path, tmp_path: Path
    ) -> None:
        """Test running with HTML output."""
        output_file = tmp_path / "report.html"
        result = runner.invoke(main, ["run", str(test_suite_file), "-o", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        assert "<html" in output_file.read_text()

    def test_run_with_save_run(
        self, runner: CliRunner, test_suite_file: Path, tmp_path: Path
    ) -> None:
        """Test saving run results."""
        save_file = tmp_path / "run.json"
        result = runner.invoke(main, ["run", str(test_suite_file), "--save-run", str(save_file)])
        assert result.exit_code == 0
        assert save_file.exists()

    def test_run_directory(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test running from a directory."""
        result = runner.invoke(main, ["run", str(test_suite_file.parent)])
        assert result.exit_code == 0

    def test_run_verbose(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test verbose output."""
        result = runner.invoke(main, ["run", str(test_suite_file), "-v"])
        assert result.exit_code == 0
        assert "Response:" in result.output

    def test_run_empty_directory_exits_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """A directory with no suites should fail so CI cannot pass silently."""
        result = runner.invoke(main, ["run", str(tmp_path)])
        assert result.exit_code == 1
        assert "No test suites found" in result.output

    def test_run_json_stdout(self, runner: CliRunner, test_suite_file: Path) -> None:
        """--format json without --output should print JSON to stdout."""
        result = runner.invoke(main, ["run", str(test_suite_file), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True
        assert data["total_tests"] == 1

    def test_run_provider_override(self, runner: CliRunner, tmp_path: Path) -> None:
        """--provider should override the suite provider name."""
        suite = tmp_path / "suite.yaml"
        suite.write_text("""
name: Override Suite
provider: openai
tests:
  - name: Capital
    prompt: What is the capital of France?
    assertions:
      - type: contains
        value: Paris
""")
        result = runner.invoke(main, ["run", str(suite), "--provider", "mock"])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_run_invalid_concurrency(self, runner: CliRunner, test_suite_file: Path) -> None:
        """--max-concurrency must be at least 1."""
        result = runner.invoke(main, ["run", str(test_suite_file), "-j", "0"])
        assert result.exit_code == 2
        assert "at least 1" in result.output

    def test_run_with_metadata(
        self, runner: CliRunner, test_suite_file: Path, tmp_path: Path
    ) -> None:
        """Test running with metadata."""
        output_file = tmp_path / "results.json"
        result = runner.invoke(
            main,
            [
                "run",
                str(test_suite_file),
                "-o",
                str(output_file),
                "-m",
                "version=1.0",
                "-m",
                "env=test",
            ],
        )
        assert result.exit_code == 0

        data = json.loads(output_file.read_text())
        assert data["metadata"]["version"] == "1.0"
        assert data["metadata"]["env"] == "test"


class TestCompareCommand:
    """Tests for the compare command."""

    @pytest.fixture
    def baseline_file(self, tmp_path: Path) -> Path:
        """Create a baseline run file."""
        data = {
            "run_id": "baseline",
            "passed": True,
            "suites": [
                {
                    "suite_name": "Suite",
                    "passed": True,
                    "tests": [
                        {
                            "test_name": "test1",
                            "suite_name": "Suite",
                            "passed": True,
                            "response": {"content": "Paris", "model": "test", "latency_ms": 100},
                            "assertions": [{"type": "contains", "passed": True, "message": "ok"}],
                        }
                    ],
                }
            ],
            "metadata": {},
        }
        file_path = tmp_path / "baseline.json"
        file_path.write_text(json.dumps(data))
        return file_path

    @pytest.fixture
    def current_file(self, tmp_path: Path) -> Path:
        """Create a current run file with a regression."""
        data = {
            "run_id": "current",
            "passed": False,
            "suites": [
                {
                    "suite_name": "Suite",
                    "passed": False,
                    "tests": [
                        {
                            "test_name": "test1",
                            "suite_name": "Suite",
                            "passed": False,
                            "response": {"content": "Wrong", "model": "test", "latency_ms": 100},
                            "assertions": [
                                {"type": "contains", "passed": False, "message": "fail"}
                            ],
                        }
                    ],
                }
            ],
            "metadata": {},
        }
        file_path = tmp_path / "current.json"
        file_path.write_text(json.dumps(data))
        return file_path

    def test_compare_with_regression(
        self, runner: CliRunner, baseline_file: Path, current_file: Path
    ) -> None:
        """Test comparing runs with regression."""
        result = runner.invoke(main, ["compare", str(baseline_file), str(current_file)])
        assert result.exit_code == 1
        assert "REGRESSIONS DETECTED" in result.output

    def test_compare_no_regression(self, runner: CliRunner, baseline_file: Path) -> None:
        """Test comparing identical runs."""
        result = runner.invoke(main, ["compare", str(baseline_file), str(baseline_file)])
        assert result.exit_code == 0
        assert "NO REGRESSIONS" in result.output

    def test_compare_no_fail_on_regression(
        self, runner: CliRunner, baseline_file: Path, current_file: Path
    ) -> None:
        """--no-fail-on-regression reports regressions but exits 0."""
        result = runner.invoke(
            main,
            ["compare", str(baseline_file), str(current_file), "--no-fail-on-regression"],
        )
        assert result.exit_code == 0
        assert "REGRESSIONS DETECTED" in result.output

    def test_compare_with_output(
        self,
        runner: CliRunner,
        baseline_file: Path,
        current_file: Path,
        tmp_path: Path,
    ) -> None:
        """Test comparing with JSON output."""
        output_file = tmp_path / "comparison.json"
        runner.invoke(
            main,
            ["compare", str(baseline_file), str(current_file), "-o", str(output_file)],
        )

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["has_regressions"] is True


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_file(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test validating a valid file."""
        result = runner.invoke(main, ["validate", str(test_suite_file)])
        assert result.exit_code == 0
        assert "✓" in result.output

    def test_validate_invalid_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test validating an invalid file."""
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("not: valid: yaml: structure")

        result = runner.invoke(main, ["validate", str(invalid_file)])
        assert result.exit_code == 1
        assert "✗" in result.output

    def test_validate_directory(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test validating a directory."""
        result = runner.invoke(main, ["validate", str(test_suite_file.parent)])
        assert result.exit_code == 0


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_files(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that init creates example files."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "tests/prompts/example.yaml").exists()


class TestListCommand:
    """Tests for the list command."""

    def test_list_suites(self, runner: CliRunner, test_suite_file: Path) -> None:
        """Test listing suites."""
        result = runner.invoke(main, ["list", str(test_suite_file)])
        assert result.exit_code == 0
        assert "CLI Test Suite" in result.output
        assert "Simple Test" in result.output
