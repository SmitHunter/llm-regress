"""Command-line interface for llm-regress."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from llm_regress.compare import compare_runs, load_run_result, save_run_result
from llm_regress.config import ProviderConfig, load_suite, load_suites_from_directory
from llm_regress.reporters import HtmlReporter, JsonReporter, TerminalReporter
from llm_regress.runner import TestRunner

console = Console()


@click.group()
@click.version_option(package_name="llm-regress")
def main() -> None:
    """llm-regress: Regression testing for LLM prompts and models.

    Run test suites defined in YAML to validate LLM outputs against
    assertions like exact match, regex, JSON schema, and more.
    """
    pass


@main.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for results (JSON or HTML based on extension)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["terminal", "json", "html"]),
    default="terminal",
    help="Output format (default: terminal)",
)
@click.option(
    "--save-run",
    type=click.Path(),
    help="Save run results to JSON file for later comparison",
)
@click.option(
    "--cache-dir",
    type=click.Path(),
    help="Directory for caching LLM responses (or set LLM_REGRESS_CACHE_DIR)",
)
@click.option(
    "--provider",
    help="Override the provider name from the suite (e.g. mock, openai, anthropic)",
)
@click.option(
    "--max-concurrency",
    "-j",
    type=int,
    default=5,
    help="Maximum concurrent test executions (default: 5)",
)
@click.option(
    "--fail-fast",
    "-x",
    is_flag=True,
    help="Stop on first test failure",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose output including response content",
)
@click.option(
    "--tag",
    "-t",
    multiple=True,
    help="Only run tests/suites with these tags",
)
@click.option(
    "--metadata",
    "-m",
    multiple=True,
    help="Add metadata as key=value pairs",
)
def run(
    paths: tuple[str, ...],
    output: str | None,
    format: str,
    save_run: str | None,
    cache_dir: str | None,
    provider: str | None,
    max_concurrency: int,
    fail_fast: bool,
    verbose: bool,
    tag: tuple[str, ...],
    metadata: tuple[str, ...],
) -> None:
    """Run test suites from YAML files.

    PATHS can be YAML files or directories containing YAML files.
    If no paths given, searches current directory for *.yaml files.

    Examples:

        llm-regress run tests/

        llm-regress run suite.yaml --output results.json

        llmr run tests/ -o report.html --cache-dir .llm-regress-cache

        llmr run tests/ --save-run baseline.json --provider mock
    """
    if max_concurrency < 1:
        console.print("[red]--max-concurrency must be at least 1[/red]")
        sys.exit(2)

    if not paths:
        paths = (".",)

    suites = []
    for path_str in paths:
        path = Path(path_str)
        try:
            if path.is_file():
                suites.append(load_suite(path))
            elif path.is_dir():
                suites.extend(load_suites_from_directory(path))
            else:
                console.print(f"[red]Path not found: {path}[/red]")
                sys.exit(1)
        except Exception as exc:
            console.print(f"[red]Failed to load {path}: {exc}[/red]")
            sys.exit(1)

    if not suites:
        console.print(
            "[red]No test suites found.[/red] "
            "Pass a YAML file or a directory containing *.yaml / *.yml suites."
        )
        sys.exit(1)

    if provider:
        for suite in suites:
            current = suite.get_provider_config()
            suite.provider = ProviderConfig(
                name=provider,
                model=current.model,
                api_key=current.api_key,
                base_url=current.base_url,
                options=current.options,
            )

    if tag:
        tags_set = set(tag)
        filtered_suites = []
        for suite in suites:
            if tags_set & set(suite.tags):
                filtered_suites.append(suite)
            else:
                filtered_tests = [t for t in suite.tests if tags_set & set(t.tags)]
                if filtered_tests:
                    suite.tests = filtered_tests
                    filtered_suites.append(suite)
        suites = filtered_suites

    meta_dict: dict[str, Any] = {}
    for m in metadata:
        if "=" in m:
            key, value = m.split("=", 1)
            meta_dict[key] = value

    if cache_dir is None:
        cache_dir = os.environ.get("LLM_REGRESS_CACHE_DIR")

    runner = TestRunner(
        cache_dir=cache_dir,
        max_concurrency=max_concurrency,
        fail_fast=fail_fast,
    )

    result = runner.run_sync(suites, metadata=meta_dict)

    if format == "html" and not output:
        console.print("[red]--format html requires --output PATH[/red]")
        sys.exit(2)

    if format == "terminal":
        reporter = TerminalReporter(console=console, verbose=verbose)
        reporter.report_run(result)
    elif format == "json" and not output:
        click.echo(JsonReporter().report_run(result))

    if output:
        output_path = Path(output)
        if output_path.suffix == ".html" or format == "html":
            html_reporter = HtmlReporter(output_path)
            html_reporter.report_run(result)
            console.print(f"[dim]HTML report saved to {output_path}[/dim]")
        else:
            json_reporter = JsonReporter(output_path)
            json_reporter.report_run(result)
            console.print(f"[dim]JSON results saved to {output_path}[/dim]")

    if save_run:
        save_run_result(result, save_run)
        console.print(f"[dim]Run saved to {save_run}[/dim]")

    sys.exit(0 if result.passed else 1)


@main.command()
@click.argument("baseline", type=click.Path(exists=True))
@click.argument("current", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for comparison results (JSON)",
)
@click.option(
    "--fail-on-regression/--no-fail-on-regression",
    default=True,
    help="Exit with code 1 if regressions are detected (default: fail)",
)
def compare(
    baseline: str,
    current: str,
    output: str | None,
    fail_on_regression: bool,
) -> None:
    """Compare two test runs to detect regressions.

    BASELINE is the reference run (e.g., from main branch).
    CURRENT is the new run to compare against baseline.

    Examples:

        llm-regress compare baseline.json current.json

        llmr compare main-run.json feature-run.json -o comparison.json
    """
    baseline_result = load_run_result(baseline)
    current_result = load_run_result(current)

    comparison = compare_runs(baseline_result, current_result)

    reporter = TerminalReporter(console=console)
    reporter.report_comparison(comparison)

    if output:
        json_reporter = JsonReporter(output)
        json_reporter.report_comparison(comparison)
        console.print(f"[dim]Comparison saved to {output}[/dim]")

    if fail_on_regression and comparison.has_regressions:
        sys.exit(1)
    sys.exit(0)


@main.command()
@click.argument("path", type=click.Path(exists=True))
def validate(path: str) -> None:
    """Validate test suite YAML files.

    Checks that YAML files are valid and conform to the expected schema.

    Examples:

        llm-regress validate tests/

        llmr validate suite.yaml
    """
    path_obj = Path(path)
    if path_obj.is_file():
        files = [path_obj]
    else:
        files = sorted(set(path_obj.rglob("*.yaml")) | set(path_obj.rglob("*.yml")))

    errors = []
    valid_count = 0

    for file_path in files:
        try:
            load_suite(file_path)
            console.print(f"[green]✓[/green] {file_path}")
            valid_count += 1
        except Exception as e:
            console.print(f"[red]✗[/red] {file_path}: {e}")
            errors.append((file_path, str(e)))

    console.print()
    if errors:
        console.print(f"[red]{len(errors)} file(s) invalid[/red]")
        sys.exit(1)
    else:
        console.print(f"[green]{valid_count} file(s) valid[/green]")
        sys.exit(0)


@main.command()
def init() -> None:
    """Initialize a new llm-regress project.

    Creates example test files and configuration.
    """
    example_suite = """name: Example Test Suite
description: Sample tests demonstrating llm-regress features
provider: mock

tests:
  - name: Capital of France
    prompt: What is the capital of France?
    assertions:
      - type: contains
        value: Paris

  - name: JSON Response
    prompt: Return a JSON object with a "status" field set to "success"
    assertions:
      - type: json_schema
        schema:
          type: object
          required: [status]
          properties:
            status:
              type: string
              enum: [success, error]

  - name: Code Generation
    prompt: Write a Python function that returns 42
    assertions:
      - type: contains
        value: "def"
      - type: contains
        value: "42"
      - type: latency_budget
        budget_ms: 1000
"""

    tests_dir = Path("tests/prompts")
    tests_dir.mkdir(parents=True, exist_ok=True)

    suite_path = tests_dir / "example.yaml"
    if suite_path.exists():
        console.print(f"[yellow]File already exists: {suite_path}[/yellow]")
    else:
        suite_path.write_text(example_suite)
        console.print(f"[green]Created: {suite_path}[/green]")

    console.print()
    console.print("Run your tests with:")
    console.print("  [bold]llm-regress run tests/prompts/[/bold]")


@main.command(name="list")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
def list_tests(paths: tuple[str, ...]) -> None:
    """List all test suites and test cases.

    Examples:

        llm-regress list tests/

        llmr list examples/
    """
    if not paths:
        paths = (".",)

    suites = []
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            suites.append(load_suite(path))
        elif path.is_dir():
            suites.extend(load_suites_from_directory(path))

    if not suites:
        console.print("[yellow]No test suites found[/yellow]")
        return

    for suite in suites:
        console.print(f"\n[bold]{suite.name}[/bold]")
        if suite.description:
            console.print(f"  [dim]{suite.description}[/dim]")
        console.print(f"  Provider: {suite.get_provider_config().name}")
        console.print(f"  Tests: {len(suite.tests)}")

        for test in suite.tests:
            tags = f" [{', '.join(test.tags)}]" if test.tags else ""
            console.print(f"    • {test.name}{tags}")


if __name__ == "__main__":
    main()
