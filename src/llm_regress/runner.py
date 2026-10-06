"""Test runner with concurrent execution and caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import xxhash

from llm_regress.assertions import Assertion, AssertionRegistry, AssertionResult
from llm_regress.config import TestCase, TestSuite
from llm_regress.providers import Provider, ProviderRegistry, ProviderResponse


@dataclass
class TestResult:
    """Result of a single test case execution."""

    __test__ = False

    test_name: str
    suite_name: str
    passed: bool
    response: ProviderResponse | None
    assertions: list[AssertionResult]
    error: str | None = None
    duration_ms: float = 0.0
    cached: bool = False

    @property
    def failed_assertions(self) -> list[AssertionResult]:
        """Get list of failed assertions."""
        return [a for a in self.assertions if not a.passed]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_name": self.test_name,
            "suite_name": self.suite_name,
            "passed": self.passed,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "cached": self.cached,
            "response": {
                "content": self.response.content if self.response else None,
                "model": self.response.model if self.response else None,
                "latency_ms": self.response.latency_ms if self.response else None,
                "input_tokens": self.response.input_tokens if self.response else 0,
                "output_tokens": self.response.output_tokens if self.response else 0,
                "cost_dollars": self.response.cost_dollars if self.response else 0,
            },
            "assertions": [
                {
                    "type": a.assertion_type,
                    "passed": a.passed,
                    "message": a.message,
                    "expected": str(a.expected)[:200] if a.expected else None,
                    "actual": str(a.actual)[:200] if a.actual else None,
                }
                for a in self.assertions
            ],
        }


@dataclass
class SuiteResult:
    """Result of a test suite execution."""

    suite_name: str
    passed: bool
    tests: list[TestResult]
    duration_ms: float = 0.0
    started_at: str = ""
    finished_at: str = ""

    @property
    def passed_count(self) -> int:
        """Count of passed tests."""
        return sum(1 for t in self.tests if t.passed)

    @property
    def failed_count(self) -> int:
        """Count of failed tests."""
        return sum(1 for t in self.tests if not t.passed)

    @property
    def total_count(self) -> int:
        """Total number of tests."""
        return len(self.tests)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "total_count": self.total_count,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tests": [t.to_dict() for t in self.tests],
        }


@dataclass
class RunResult:
    """Result of a complete test run across all suites."""

    run_id: str
    passed: bool
    suites: list[SuiteResult]
    duration_ms: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tests(self) -> int:
        """Total tests across all suites."""
        return sum(s.total_count for s in self.suites)

    @property
    def passed_tests(self) -> int:
        """Passed tests across all suites."""
        return sum(s.passed_count for s in self.suites)

    @property
    def failed_tests(self) -> int:
        """Failed tests across all suites."""
        return sum(s.failed_count for s in self.suites)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "run_id": self.run_id,
            "passed": self.passed,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": self.metadata,
            "suites": [s.to_dict() for s in self.suites],
        }


class ResponseCache:
    """Cache for LLM responses to avoid redundant API calls."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize the cache.

        Args:
            cache_dir: Directory to store cache files. None disables persistence.
        """
        self.cache_dir = cache_dir
        self._memory_cache: dict[str, ProviderResponse] = {}

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, prompt: str, provider: str, model: str, extra: str = "") -> str:
        """Create a cache key from request parameters."""
        data = f"{provider}:{model}:{prompt}:{extra}"
        return xxhash.xxh64(data.encode()).hexdigest()

    def get(
        self, prompt: str, provider: str, model: str, extra: str = ""
    ) -> ProviderResponse | None:
        """Get a cached response if available."""
        key = self._make_key(prompt, provider, model, extra)

        if key in self._memory_cache:
            response = self._memory_cache[key]
            response.cached = True
            return response

        if self.cache_dir:
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    response = ProviderResponse(**data)
                    response.cached = True
                    self._memory_cache[key] = response
                    return response
                except (json.JSONDecodeError, TypeError):
                    pass

        return None

    def set(
        self,
        prompt: str,
        provider: str,
        model: str,
        response: ProviderResponse,
        extra: str = "",
    ) -> None:
        """Cache a response."""
        key = self._make_key(prompt, provider, model, extra)
        self._memory_cache[key] = response

        if self.cache_dir:
            cache_file = self.cache_dir / f"{key}.json"
            data = {
                "content": response.content,
                "model": response.model,
                "latency_ms": response.latency_ms,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "cost_dollars": response.cost_dollars,
                "raw_response": response.raw_response,
            }
            cache_file.write_text(json.dumps(data, indent=2))

    def clear(self) -> None:
        """Clear the cache."""
        self._memory_cache.clear()
        if self.cache_dir:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()


class TestRunner:
    """Runs test suites with concurrent execution and caching."""

    __test__ = False

    def __init__(
        self,
        cache_dir: Path | str | None = None,
        max_concurrency: int = 5,
        fail_fast: bool = False,
    ) -> None:
        """Initialize the test runner.

        Args:
            cache_dir: Directory for response caching. None disables caching.
            max_concurrency: Maximum concurrent test executions.
            fail_fast: Stop on first failure if True.
        """
        cache_path = Path(cache_dir) if cache_dir else None
        self.cache = ResponseCache(cache_path) if cache_path else None
        self.max_concurrency = max_concurrency
        self.fail_fast = fail_fast
        self._providers: dict[str, Provider] = {}

    def _get_provider(self, suite: TestSuite) -> Provider:
        """Get or create provider for a suite."""
        config = suite.get_provider_config()
        key = f"{config.name}:{config.model}:{config.base_url}"

        if key not in self._providers:
            self._providers[key] = ProviderRegistry.get(config)

        return self._providers[key]

    def _render_prompt(self, template: str, inputs: dict[str, Any]) -> str:
        """Render a prompt template with inputs using a sandboxed Jinja2 environment."""
        from jinja2.sandbox import SandboxedEnvironment

        result: str = SandboxedEnvironment().from_string(template).render(**inputs)
        return result

    async def _run_test(
        self,
        test: TestCase,
        suite: TestSuite,
        provider: Provider,
        semaphore: asyncio.Semaphore,
    ) -> TestResult:
        """Run a single test case."""
        async with semaphore:
            start_time = time.perf_counter()
            assertions_results: list[AssertionResult] = []
            response: ProviderResponse | None = None
            error: str | None = None
            cached = False

            try:
                merged_inputs = {**suite.defaults, **test.inputs}
                prompt = self._render_prompt(test.prompt, merged_inputs)

                config = suite.get_provider_config()
                model = config.model or "default"
                options = dict(config.options)
                cache_extra = json.dumps(options, sort_keys=True, default=str)

                if self.cache:
                    cached_response = self.cache.get(prompt, config.name, model, cache_extra)
                    if cached_response:
                        response = cached_response
                        cached = True

                if response is None:
                    complete = provider.complete(prompt, model=config.model, **options)
                    if test.timeout_ms is not None:
                        try:
                            response = await asyncio.wait_for(
                                complete, timeout=test.timeout_ms / 1000.0
                            )
                        except TimeoutError as exc:
                            raise TimeoutError(
                                f"Test '{test.name}' exceeded timeout of {test.timeout_ms:.0f}ms"
                            ) from exc
                    else:
                        response = await complete
                    if self.cache:
                        self.cache.set(prompt, config.name, model, response, cache_extra)

                for assertion_config in test.assertions:
                    assertion: Assertion
                    if assertion_config.type == "llm_judge":
                        from llm_regress.assertions import LlmJudgeAssertion

                        assertion = LlmJudgeAssertion(judge_provider=provider)
                    else:
                        assertion = AssertionRegistry.get(assertion_config.type)
                    result = assertion.evaluate(response, assertion_config)
                    assertions_results.append(result)

            except Exception as e:
                error = str(e)

            duration_ms = (time.perf_counter() - start_time) * 1000
            passed = error is None and all(a.passed for a in assertions_results)

            return TestResult(
                test_name=test.name,
                suite_name=suite.name,
                passed=passed,
                response=response,
                assertions=assertions_results,
                error=error,
                duration_ms=duration_ms,
                cached=cached,
            )

    async def run_suite(self, suite: TestSuite) -> SuiteResult:
        """Run all tests in a suite.

        Args:
            suite: Test suite to run.

        Returns:
            SuiteResult with all test results.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        provider = self._get_provider(suite)
        concurrency = suite.max_concurrency if suite.parallel else 1
        semaphore = asyncio.Semaphore(min(concurrency, self.max_concurrency))

        results: list[TestResult] = []

        if suite.parallel and not self.fail_fast:
            tasks = [self._run_test(test, suite, provider, semaphore) for test in suite.tests]
            results = await asyncio.gather(*tasks)
        else:
            for test in suite.tests:
                result = await self._run_test(test, suite, provider, semaphore)
                results.append(result)
                if self.fail_fast and not result.passed:
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000
        finished_at = datetime.now(timezone.utc).isoformat()

        return SuiteResult(
            suite_name=suite.name,
            passed=all(r.passed for r in results),
            tests=results,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def run(
        self,
        suites: list[TestSuite],
        metadata: dict[str, Any] | None = None,
    ) -> RunResult:
        """Run all test suites.

        Args:
            suites: List of test suites to run.
            metadata: Optional metadata to include in results.

        Returns:
            RunResult with all suite results.
        """
        run_id = hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:12]

        started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.perf_counter()

        suite_results: list[SuiteResult] = []

        for suite in suites:
            result = await self.run_suite(suite)
            suite_results.append(result)

            if self.fail_fast and not result.passed:
                break

        duration_ms = (time.perf_counter() - start_time) * 1000
        finished_at = datetime.now(timezone.utc).isoformat()

        return RunResult(
            run_id=run_id,
            passed=all(s.passed for s in suite_results),
            suites=suite_results,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            metadata=metadata or {},
        )

    def run_sync(
        self,
        suites: list[TestSuite],
        metadata: dict[str, Any] | None = None,
    ) -> RunResult:
        """Synchronous wrapper for run().

        Args:
            suites: List of test suites to run.
            metadata: Optional metadata to include in results.

        Returns:
            RunResult with all suite results.
        """
        return asyncio.run(self.run(suites, metadata))
