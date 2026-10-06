"""Assertion implementations for validating LLM outputs."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from llm_regress.config import AssertionConfig
    from llm_regress.providers import Provider, ProviderResponse


@dataclass
class AssertionResult:
    """Result of running an assertion."""

    passed: bool
    assertion_type: str
    message: str
    expected: Any = None
    actual: Any = None
    details: dict[str, Any] | None = None


class Assertion(ABC):
    """Abstract base class for assertions."""

    name: ClassVar[str] = "base"

    @abstractmethod
    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Evaluate the assertion against a response.

        Args:
            response: The provider response to evaluate.
            config: The assertion configuration.

        Returns:
            AssertionResult with pass/fail status and details.
        """
        ...


class ExactMatchAssertion(Assertion):
    """Assert that the output exactly matches the expected value."""

    name: ClassVar[str] = "exact"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check for exact match."""
        expected = str(config.value)
        actual = response.content.strip()
        passed = actual == expected

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message="Exact match" if passed else "Output does not match expected value",
            expected=expected,
            actual=actual,
        )


class ContainsAssertion(Assertion):
    """Assert that the output contains a substring."""

    name: ClassVar[str] = "contains"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check if output contains the expected substring."""
        expected = str(config.value)
        actual = response.content
        passed = expected.lower() in actual.lower()

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=f"Contains '{expected}'" if passed else f"Output does not contain '{expected}'",
            expected=expected,
            actual=actual[:200] + "..." if len(actual) > 200 else actual,
        )


class RegexAssertion(Assertion):
    """Assert that the output matches a regex pattern."""

    name: ClassVar[str] = "regex"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check if output matches the regex pattern."""
        pattern = str(config.value)
        actual = response.content

        try:
            match = re.search(pattern, actual, re.IGNORECASE | re.MULTILINE)
            passed = match is not None
        except re.error as e:
            return AssertionResult(
                passed=False,
                assertion_type=self.name,
                message=f"Invalid regex pattern: {e}",
                expected=pattern,
                actual=actual[:200],
            )

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message="Matches pattern" if passed else f"Output does not match pattern '{pattern}'",
            expected=pattern,
            actual=actual[:200] + "..." if len(actual) > 200 else actual,
            details={"match": match.group() if match else None},
        )


class JsonSchemaAssertion(Assertion):
    """Assert that the output is valid JSON matching a schema."""

    name: ClassVar[str] = "json_schema"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check if output is valid JSON matching the schema."""
        import jsonschema

        schema = config.schema_ or {}
        actual = response.content.strip()

        if actual.startswith("```json"):
            actual = actual[7:]
        if actual.startswith("```"):
            actual = actual[3:]
        if actual.endswith("```"):
            actual = actual[:-3]
        actual = actual.strip()

        try:
            parsed = json.loads(actual)
        except json.JSONDecodeError as e:
            return AssertionResult(
                passed=False,
                assertion_type=self.name,
                message=f"Invalid JSON: {e}",
                expected="Valid JSON",
                actual=actual[:200],
            )

        try:
            jsonschema.validate(parsed, schema)
            return AssertionResult(
                passed=True,
                assertion_type=self.name,
                message="JSON matches schema",
                expected=schema,
                actual=parsed,
            )
        except jsonschema.ValidationError as e:
            return AssertionResult(
                passed=False,
                assertion_type=self.name,
                message=f"Schema validation failed: {e.message}",
                expected=schema,
                actual=parsed,
                details={"path": list(e.path), "validator": e.validator},
            )


class SemanticSimilarityAssertion(Assertion):
    """Assert that the output is semantically similar to expected text."""

    name: ClassVar[str] = "semantic_similarity"
    _model: Any = None

    def _get_model(self) -> Any:
        """Lazy-load the sentence transformer model."""
        if SemanticSimilarityAssertion._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "Semantic similarity requires sentence-transformers. "
                    "Install with: pip install llm-regress[semantic]"
                ) from e

            SemanticSimilarityAssertion._model = SentenceTransformer("all-MiniLM-L6-v2")
        return SemanticSimilarityAssertion._model

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check semantic similarity using embeddings."""
        expected = str(config.value)
        actual = response.content
        threshold = config.threshold or 0.7

        try:
            model = self._get_model()
            embeddings = model.encode([expected, actual])
            from numpy import dot
            from numpy.linalg import norm

            similarity = float(
                dot(embeddings[0], embeddings[1]) / (norm(embeddings[0]) * norm(embeddings[1]))
            )
        except Exception as e:
            return AssertionResult(
                passed=False,
                assertion_type=self.name,
                message=f"Failed to compute similarity: {e}",
                expected=expected[:100],
                actual=actual[:100],
            )

        passed = similarity >= threshold

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=f"Similarity {similarity:.3f} {'≥' if passed else '<'} {threshold}",
            expected=expected[:100],
            actual=actual[:100],
            details={"similarity": similarity, "threshold": threshold},
        )


class LlmJudgeAssertion(Assertion):
    """Assert using an LLM to judge the output against a rubric."""

    name: ClassVar[str] = "llm_judge"

    def __init__(self, judge_provider: Provider | None = None) -> None:
        """Initialize with optional judge provider."""
        self.judge_provider = judge_provider

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Use LLM to judge output against rubric.

        Note: This is a synchronous wrapper. For async evaluation,
        use evaluate_async directly.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.evaluate_async(response, config),
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(self.evaluate_async(response, config))

    async def evaluate_async(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Async evaluation using LLM judge."""
        from llm_regress.providers import MockProvider

        rubric = config.rubric or "Evaluate if the response is helpful and accurate."
        actual = response.content

        judge_prompt = f"""You are evaluating an LLM output against a rubric.

RUBRIC:
{rubric}

OUTPUT TO EVALUATE:
{actual}

Respond with exactly "PASS" if the output meets the rubric, or "FAIL: <reason>" if it does not.
Do not include any other text."""

        provider = self.judge_provider or MockProvider()

        judge_response = await provider.complete(judge_prompt, model=config.judge_model)
        verdict = judge_response.content.strip().upper()

        passed = verdict.startswith("PASS")

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=judge_response.content.strip(),
            expected=rubric[:100],
            actual=actual[:100],
            details={
                "rubric": rubric,
                "verdict": verdict,
                "judge_model": judge_response.model,
            },
        )


class LatencyBudgetAssertion(Assertion):
    """Assert that response latency is within budget."""

    name: ClassVar[str] = "latency_budget"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check if latency is within budget."""
        budget_ms = config.budget_ms or 1000.0
        actual_ms = response.latency_ms
        passed = actual_ms <= budget_ms

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=f"Latency {actual_ms:.0f}ms {'≤' if passed else '>'} {budget_ms:.0f}ms budget",
            expected=f"≤{budget_ms}ms",
            actual=f"{actual_ms:.0f}ms",
            details={"budget_ms": budget_ms, "actual_ms": actual_ms},
        )


class CostBudgetAssertion(Assertion):
    """Assert that response cost is within budget."""

    name: ClassVar[str] = "cost_budget"

    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Check if cost is within budget."""
        budget = config.budget_dollars or 0.01
        actual = response.cost_dollars
        passed = actual <= budget

        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=f"Cost ${actual:.6f} {'≤' if passed else '>'} ${budget:.6f} budget",
            expected=f"≤${budget:.6f}",
            actual=f"${actual:.6f}",
            details={"budget_dollars": budget, "actual_dollars": actual},
        )


class AssertionRegistry:
    """Registry for assertion types."""

    _assertions: ClassVar[dict[str, type[Assertion]]] = {
        "exact": ExactMatchAssertion,
        "contains": ContainsAssertion,
        "regex": RegexAssertion,
        "json_schema": JsonSchemaAssertion,
        "semantic_similarity": SemanticSimilarityAssertion,
        "llm_judge": LlmJudgeAssertion,
        "latency_budget": LatencyBudgetAssertion,
        "cost_budget": CostBudgetAssertion,
    }
    _instances: ClassVar[dict[str, Assertion]] = {}

    @classmethod
    def register(cls, name: str, assertion_class: type[Assertion]) -> None:
        """Register a custom assertion type."""
        cls._assertions[name] = assertion_class

    @classmethod
    def get(cls, assertion_type: str) -> Assertion:
        """Get an assertion instance by type."""
        if assertion_type not in cls._assertions:
            available = ", ".join(sorted(cls._assertions.keys()))
            raise ValueError(f"Unknown assertion type '{assertion_type}'. Available: {available}")

        if assertion_type not in cls._instances:
            cls._instances[assertion_type] = cls._assertions[assertion_type]()

        return cls._instances[assertion_type]

    @classmethod
    def list_assertions(cls) -> list[str]:
        """List all registered assertion types."""
        return sorted(cls._assertions.keys())
