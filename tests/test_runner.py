"""Tests for the test runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_regress.config import AssertionConfig, TestCase, TestSuite, load_suite
from llm_regress.runner import ResponseCache, RunResult, SuiteResult, TestResult, TestRunner


class TestResponseCache:
    """Tests for ResponseCache."""

    def test_memory_cache(self) -> None:
        """Test in-memory caching."""
        from llm_regress.providers import ProviderResponse

        cache = ResponseCache()

        response = ProviderResponse(
            content="Hello",
            model="test",
            latency_ms=100.0,
        )

        cache.set("prompt", "provider", "model", response)

        cached = cache.get("prompt", "provider", "model")
        assert cached is not None
        assert cached.content == "Hello"
        assert cached.cached is True

    def test_cache_miss(self) -> None:
        """Test cache miss returns None."""
        cache = ResponseCache()
        result = cache.get("unknown", "provider", "model")
        assert result is None

    def test_file_cache(self, tmp_path: Path) -> None:
        """Test file-based caching."""
        from llm_regress.providers import ProviderResponse

        cache = ResponseCache(cache_dir=tmp_path)

        response = ProviderResponse(
            content="Persistent",
            model="test",
            latency_ms=50.0,
        )

        cache.set("prompt", "provider", "model", response)

        new_cache = ResponseCache(cache_dir=tmp_path)
        cached = new_cache.get("prompt", "provider", "model")
        assert cached is not None
        assert cached.content == "Persistent"

    def test_clear_cache(self, tmp_path: Path) -> None:
        """Test clearing cache."""
        from llm_regress.providers import ProviderResponse

        cache = ResponseCache(cache_dir=tmp_path)

        response = ProviderResponse(content="Test", model="test", latency_ms=50.0)
        cache.set("prompt", "provider", "model", response)

        cache.clear()

        assert cache.get("prompt", "provider", "model") is None
        assert len(list(tmp_path.glob("*.json"))) == 0


class TestTestRunner:
    """Tests for TestRunner."""

    @pytest.fixture
    def simple_suite(self) -> TestSuite:
        """Create a simple test suite."""
        return TestSuite(
            name="Simple Suite",
            provider="mock",
            tests=[
                TestCase(
                    name="Capital Test",
                    prompt="What is the capital of France?",
                    assertions=[AssertionConfig(type="contains", value="Paris")],
                ),
                TestCase(
                    name="Math Test",
                    prompt="What is 2 + 2?",
                    assertions=[AssertionConfig(type="contains", value="4")],
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_run_simple_suite(self, simple_suite: TestSuite) -> None:
        """Test running a simple suite."""
        runner = TestRunner()
        result = await runner.run_suite(simple_suite)

        assert result.suite_name == "Simple Suite"
        assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_run_multiple_suites(self, simple_suite: TestSuite) -> None:
        """Test running multiple suites."""
        runner = TestRunner()
        result = await runner.run([simple_suite, simple_suite])

        assert len(result.suites) == 2
        assert result.total_tests == 4

    def test_run_sync(self, simple_suite: TestSuite) -> None:
        """Test synchronous run method."""
        runner = TestRunner()
        result = runner.run_sync([simple_suite])

        assert result.total_tests == 2

    @pytest.mark.asyncio
    async def test_with_caching(self, simple_suite: TestSuite, tmp_path: Path) -> None:
        """Test that caching works."""
        runner = TestRunner(cache_dir=tmp_path)

        await runner.run([simple_suite])
        result2 = await runner.run([simple_suite])

        cached_count = sum(1 for s in result2.suites for t in s.tests if t.cached)
        assert cached_count == 2

    @pytest.mark.asyncio
    async def test_fail_fast(self) -> None:
        """Test fail-fast behavior."""
        suite = TestSuite(
            name="Fail Fast Suite",
            provider="mock",
            parallel=False,
            tests=[
                TestCase(
                    name="Pass Test",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="Mock")],
                ),
                TestCase(
                    name="Fail Test",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="exact", value="IMPOSSIBLE")],
                ),
                TestCase(
                    name="Never Run",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="hello")],
                ),
            ],
        )

        runner = TestRunner(fail_fast=True)
        result = await runner.run_suite(suite)

        assert len(result.tests) == 2

    @pytest.mark.asyncio
    async def test_template_rendering(self) -> None:
        """Test Jinja2 template rendering in prompts."""
        suite = TestSuite(
            name="Template Suite",
            provider="mock",
            defaults={"topic": "Python"},
            tests=[
                TestCase(
                    name="Template Test",
                    prompt="Tell me about {{ topic }} and {{ subtopic }}",
                    inputs={"subtopic": "basics"},
                    assertions=[AssertionConfig(type="contains", value="response")],
                ),
            ],
        )

        runner = TestRunner()
        result = await runner.run_suite(suite)

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_metadata_in_results(self) -> None:
        """Test that metadata is included in results."""
        suite = TestSuite(
            name="Suite",
            provider="mock",
            tests=[
                TestCase(
                    name="Test",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="Mock")],
                ),
            ],
        )

        runner = TestRunner()
        result = await runner.run(
            [suite],
            metadata={"version": "1.0", "env": "test"},
        )

        assert result.metadata["version"] == "1.0"
        assert result.metadata["env"] == "test"


class TestTestResult:
    """Tests for TestResult."""

    def test_to_dict(self) -> None:
        """Test converting result to dict."""
        from llm_regress.assertions import AssertionResult
        from llm_regress.providers import ProviderResponse

        result = TestResult(
            test_name="Test",
            suite_name="Suite",
            passed=True,
            response=ProviderResponse(
                content="Hello",
                model="test",
                latency_ms=50.0,
            ),
            assertions=[
                AssertionResult(
                    passed=True,
                    assertion_type="contains",
                    message="Contains 'hello'",
                )
            ],
            duration_ms=100.0,
        )

        data = result.to_dict()
        assert data["test_name"] == "Test"
        assert data["passed"] is True
        assert data["response"]["content"] == "Hello"
        assert len(data["assertions"]) == 1

    def test_failed_assertions_property(self) -> None:
        """Test failed_assertions property."""
        from llm_regress.assertions import AssertionResult

        result = TestResult(
            test_name="Test",
            suite_name="Suite",
            passed=False,
            response=None,
            assertions=[
                AssertionResult(passed=True, assertion_type="a", message="ok"),
                AssertionResult(passed=False, assertion_type="b", message="fail"),
                AssertionResult(passed=False, assertion_type="c", message="fail"),
            ],
        )

        assert len(result.failed_assertions) == 2


class TestSuiteResult:
    """Tests for SuiteResult."""

    def test_counts(self) -> None:
        """Test count properties."""
        result = SuiteResult(
            suite_name="Suite",
            passed=False,
            tests=[
                TestResult(
                    test_name="t1",
                    suite_name="Suite",
                    passed=True,
                    response=None,
                    assertions=[],
                ),
                TestResult(
                    test_name="t2",
                    suite_name="Suite",
                    passed=False,
                    response=None,
                    assertions=[],
                ),
                TestResult(
                    test_name="t3",
                    suite_name="Suite",
                    passed=True,
                    response=None,
                    assertions=[],
                ),
            ],
        )

        assert result.passed_count == 2
        assert result.failed_count == 1
        assert result.total_count == 3


class TestRunResult:
    """Tests for RunResult."""

    def test_aggregate_counts(self) -> None:
        """Test aggregate count properties."""
        result = RunResult(
            run_id="test-run",
            passed=False,
            suites=[
                SuiteResult(
                    suite_name="Suite1",
                    passed=True,
                    tests=[
                        TestResult("t1", "Suite1", True, None, []),
                        TestResult("t2", "Suite1", True, None, []),
                    ],
                ),
                SuiteResult(
                    suite_name="Suite2",
                    passed=False,
                    tests=[
                        TestResult("t3", "Suite2", False, None, []),
                    ],
                ),
            ],
        )

        assert result.total_tests == 3
        assert result.passed_tests == 2
        assert result.failed_tests == 1


class TestIntegrationWithYAML:
    """Integration tests loading from YAML files."""

    @pytest.mark.asyncio
    async def test_run_from_yaml_file(self, complex_yaml_file: Path) -> None:
        """Test running tests loaded from YAML."""
        suite = load_suite(complex_yaml_file)
        runner = TestRunner()
        result = await runner.run_suite(suite)

        assert result.suite_name == "Complex Test Suite"
        assert result.total_count == 5
        assert result.passed_count >= 3
