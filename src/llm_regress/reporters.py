"""Output reporters for test results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from llm_regress.compare import RunComparison
    from llm_regress.runner import RunResult, SuiteResult, TestResult


class TerminalReporter:
    """Rich terminal output for test results."""

    def __init__(self, console: Console | None = None, verbose: bool = False) -> None:
        """Initialize the reporter.

        Args:
            console: Rich console instance. Creates new if None.
            verbose: Show detailed output including response content.
        """
        self.console = console or Console()
        self.verbose = verbose

    def _status_icon(self, passed: bool) -> str:
        """Get status icon."""
        return "✓" if passed else "✗"

    def _status_style(self, passed: bool) -> str:
        """Get status style."""
        return "green" if passed else "red"

    def report_test(self, test: TestResult) -> None:
        """Report a single test result."""
        icon = self._status_icon(test.passed)
        style = self._status_style(test.passed)

        status_text = Text()
        status_text.append(f"  {icon} ", style=style)
        status_text.append(test.test_name)

        if test.cached:
            status_text.append(" (cached)", style="dim")

        status_text.append(f" [{test.duration_ms:.0f}ms]", style="dim")

        self.console.print(status_text)

        if not test.passed:
            if test.error:
                self.console.print(f"      Error: {test.error}", style="red dim")
            for assertion in test.failed_assertions:
                self.console.print(
                    f"      {assertion.assertion_type}: {assertion.message}",
                    style="red dim",
                )

        if self.verbose and test.response:
            content = test.response.content[:200]
            if len(test.response.content) > 200:
                content += "..."
            self.console.print(f"      Response: {content}", style="dim")

    def report_suite(self, suite: SuiteResult) -> None:
        """Report a test suite result."""
        icon = self._status_icon(suite.passed)
        style = self._status_style(suite.passed)

        header = Text()
        header.append(f"{icon} ", style=style)
        header.append(suite.suite_name, style="bold")
        header.append(
            f" ({suite.passed_count}/{suite.total_count} passed, {suite.duration_ms:.0f}ms)",
            style="dim",
        )

        self.console.print()
        self.console.print(header)

        for test in suite.tests:
            self.report_test(test)

    def report_run(self, result: RunResult) -> None:
        """Report a complete test run."""
        self.console.print()
        self.console.rule("[bold]LLM Regress Test Results[/bold]")

        for suite in result.suites:
            self.report_suite(suite)

        self.console.print()

        summary_table = Table(show_header=False, box=None, padding=(0, 2))
        summary_table.add_column("Metric", style="bold")
        summary_table.add_column("Value")

        summary_table.add_row("Total Tests", str(result.total_tests))
        summary_table.add_row(
            "Passed",
            Text(str(result.passed_tests), style="green"),
        )
        summary_table.add_row(
            "Failed",
            Text(str(result.failed_tests), style="red" if result.failed_tests else "dim"),
        )
        summary_table.add_row("Duration", f"{result.duration_ms:.0f}ms")
        summary_table.add_row("Run ID", result.run_id)

        status = "PASSED" if result.passed else "FAILED"
        status_style = "green bold" if result.passed else "red bold"

        panel = Panel(
            summary_table,
            title=f"[{status_style}]{status}[/{status_style}]",
            border_style=self._status_style(result.passed),
        )
        self.console.print(panel)

    def report_comparison(self, comparison: RunComparison) -> None:
        """Report a run comparison."""
        self.console.print()
        self.console.rule("[bold]Run Comparison[/bold]")
        self.console.print()

        self.console.print(f"Baseline: {comparison.baseline_run_id}")
        self.console.print(f"Current:  {comparison.current_run_id}")
        self.console.print()

        for suite in comparison.suites:
            changed = [test for test in suite.tests if test.status != "unchanged"]
            if not changed:
                continue

            self.console.print(f"[bold]{suite.suite_name}[/bold]")

            for test in changed:
                icon_map = {
                    "regressed": ("↓", "red"),
                    "improved": ("↑", "green"),
                    "new": ("+", "blue"),
                    "removed": ("-", "yellow"),
                }
                icon, style = icon_map.get(test.status, ("•", "dim"))

                line = Text()
                line.append(f"  {icon} ", style=style)
                line.append(test.test_name)
                line.append(f" [{test.status}]", style=style)

                if test.latency_change_pct is not None and abs(test.latency_change_pct) >= 1:
                    change = test.latency_change_pct
                    lat_style = "red" if change > 20 else "green" if change < -20 else "dim"
                    line.append(f" latency: {change:+.0f}%", style=lat_style)

                self.console.print(line)

            self.console.print()

        summary = Table(show_header=False, box=None)
        summary.add_column("Metric")
        summary.add_column("Value")

        summary.add_row(
            "Regressions",
            Text(
                str(comparison.total_regressions),
                style="red bold" if comparison.total_regressions else "dim",
            ),
        )
        summary.add_row(
            "Improvements",
            Text(
                str(comparison.total_improvements),
                style="green" if comparison.total_improvements else "dim",
            ),
        )

        status = "REGRESSIONS DETECTED" if comparison.has_regressions else "NO REGRESSIONS"
        status_style = "red bold" if comparison.has_regressions else "green bold"

        panel = Panel(
            summary,
            title=f"[{status_style}]{status}[/{status_style}]",
            border_style="red" if comparison.has_regressions else "green",
        )
        self.console.print(panel)


class JsonReporter:
    """JSON output for test results."""

    def __init__(self, output_path: Path | str | None = None) -> None:
        """Initialize the reporter.

        Args:
            output_path: Path to write JSON output. None for stdout.
        """
        self.output_path = Path(output_path) if output_path else None

    def report_run(self, result: RunResult) -> str:
        """Report a test run as JSON.

        Returns:
            JSON string of the results.
        """
        output = json.dumps(result.to_dict(), indent=2)

        if self.output_path:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(output)

        return output

    def report_comparison(self, comparison: RunComparison) -> str:
        """Report a comparison as JSON.

        Returns:
            JSON string of the comparison.
        """
        output = json.dumps(comparison.to_dict(), indent=2)

        if self.output_path:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_text(output)

        return output


class HtmlReporter:
    """HTML output for test results."""

    def __init__(self, output_path: Path | str) -> None:
        """Initialize the reporter.

        Args:
            output_path: Path to write HTML output.
        """
        self.output_path = Path(output_path)

    def _generate_html(self, result: RunResult) -> str:
        """Generate HTML report."""
        status_class = "passed" if result.passed else "failed"
        status_text = "PASSED" if result.passed else "FAILED"

        tests_html = []
        for suite in result.suites:
            suite_html = f"""
            <div class="suite">
                <h2 class="{"passed" if suite.passed else "failed"}">
                    {"✓" if suite.passed else "✗"} {suite.suite_name}
                    <span class="stats">({suite.passed_count}/{suite.total_count} passed)</span>
                </h2>
                <div class="tests">
            """
            for test in suite.tests:
                test_class = "passed" if test.passed else "failed"
                assertions_html = ""
                for a in test.assertions:
                    a_class = "passed" if a.passed else "failed"
                    assertions_html += f"""
                    <div class="assertion {a_class}">
                        <span class="type">{a.assertion_type}</span>: {a.message}
                    </div>
                    """

                suite_html += f"""
                <div class="test {test_class}">
                    <div class="test-header">
                        {"✓" if test.passed else "✗"} {test.test_name}
                        <span class="duration">{test.duration_ms:.0f}ms</span>
                    </div>
                    <div class="assertions">{assertions_html}</div>
                </div>
                """

            suite_html += "</div></div>"
            tests_html.append(suite_html)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Regress Test Report</title>
    <style>
        :root {{
            --green: #22c55e;
            --red: #ef4444;
            --bg: #0f172a;
            --surface: #1e293b;
            --text: #f1f5f9;
            --muted: #94a3b8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ font-size: 2rem; margin-bottom: 1rem; }}
        .summary {{
            background: var(--surface);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
        }}
        .stat {{ text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: bold; }}
        .stat-label {{ color: var(--muted); font-size: 0.875rem; }}
        .status {{ padding: 0.5rem 1rem; border-radius: 4px; display: inline-block; }}
        .status.passed {{ background: var(--green); color: white; }}
        .status.failed {{ background: var(--red); color: white; }}
        .suite {{ background: var(--surface); border-radius: 8px; margin-bottom: 1rem; overflow: hidden; }}
        .suite h2 {{ padding: 1rem; border-bottom: 1px solid var(--bg); font-size: 1.1rem; }}
        .suite h2.passed {{ border-left: 4px solid var(--green); }}
        .suite h2.failed {{ border-left: 4px solid var(--red); }}
        .stats {{ color: var(--muted); font-weight: normal; font-size: 0.9rem; }}
        .tests {{ padding: 0.5rem; }}
        .test {{ padding: 0.75rem 1rem; border-radius: 4px; margin: 0.25rem 0; }}
        .test.passed {{ background: rgba(34, 197, 94, 0.1); }}
        .test.failed {{ background: rgba(239, 68, 68, 0.1); }}
        .test-header {{ display: flex; justify-content: space-between; align-items: center; }}
        .duration {{ color: var(--muted); font-size: 0.875rem; }}
        .assertions {{ margin-top: 0.5rem; padding-left: 1.5rem; }}
        .assertion {{ font-size: 0.875rem; color: var(--muted); padding: 0.25rem 0; }}
        .assertion.passed {{ color: var(--green); }}
        .assertion.failed {{ color: var(--red); }}
        .type {{ font-weight: 500; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>LLM Regress Test Report</h1>

        <div class="summary">
            <div class="stat">
                <div class="stat-value status {status_class}">{status_text}</div>
                <div class="stat-label">Overall Status</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.total_tests}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: var(--green)">{result.passed_tests}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat">
                <div class="stat-value" style="color: var(--red)">{result.failed_tests}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat">
                <div class="stat-value">{result.duration_ms:.0f}ms</div>
                <div class="stat-label">Duration</div>
            </div>
        </div>

        {"".join(tests_html)}

        <p style="color: var(--muted); text-align: center; margin-top: 2rem; font-size: 0.875rem;">
            Run ID: {result.run_id} | Generated by LLM Regress
        </p>
    </div>
</body>
</html>"""

    def report_run(self, result: RunResult) -> None:
        """Generate and save HTML report.

        Args:
            result: Test run result to report.
        """
        html = self._generate_html(result)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(html)
