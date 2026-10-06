"""Tests for assertion implementations."""

from __future__ import annotations

import pytest

from llm_regress.assertions import (
    AssertionRegistry,
    ContainsAssertion,
    CostBudgetAssertion,
    ExactMatchAssertion,
    JsonSchemaAssertion,
    LatencyBudgetAssertion,
    RegexAssertion,
)
from llm_regress.config import AssertionConfig
from llm_regress.providers import ProviderResponse


def make_response(content: str, latency_ms: float = 50.0, cost: float = 0.001) -> ProviderResponse:
    """Create a test response."""
    return ProviderResponse(
        content=content,
        model="test-model",
        latency_ms=latency_ms,
        input_tokens=10,
        output_tokens=5,
        cost_dollars=cost,
    )


class TestExactMatchAssertion:
    """Tests for ExactMatchAssertion."""

    def test_exact_match_pass(self) -> None:
        """Test exact match passes."""
        assertion = ExactMatchAssertion()
        config = AssertionConfig(type="exact", value="Hello, World!")
        response = make_response("Hello, World!")

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_exact_match_fail(self) -> None:
        """Test exact match fails on mismatch."""
        assertion = ExactMatchAssertion()
        config = AssertionConfig(type="exact", value="Hello, World!")
        response = make_response("Hello, World")

        result = assertion.evaluate(response, config)
        assert result.passed is False

    def test_exact_match_strips_whitespace(self) -> None:
        """Test that exact match strips surrounding whitespace."""
        assertion = ExactMatchAssertion()
        config = AssertionConfig(type="exact", value="Hello")
        response = make_response("  Hello  ")

        result = assertion.evaluate(response, config)
        assert result.passed is True


class TestContainsAssertion:
    """Tests for ContainsAssertion."""

    def test_contains_pass(self) -> None:
        """Test contains passes."""
        assertion = ContainsAssertion()
        config = AssertionConfig(type="contains", value="world")
        response = make_response("Hello, World!")

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_contains_case_insensitive(self) -> None:
        """Test contains is case insensitive."""
        assertion = ContainsAssertion()
        config = AssertionConfig(type="contains", value="WORLD")
        response = make_response("Hello, world!")

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_contains_fail(self) -> None:
        """Test contains fails when not found."""
        assertion = ContainsAssertion()
        config = AssertionConfig(type="contains", value="foo")
        response = make_response("Hello, World!")

        result = assertion.evaluate(response, config)
        assert result.passed is False


class TestRegexAssertion:
    """Tests for RegexAssertion."""

    def test_regex_pass(self) -> None:
        """Test regex match passes."""
        assertion = RegexAssertion()
        config = AssertionConfig(type="regex", value=r"\d+")
        response = make_response("The answer is 42.")

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_regex_fail(self) -> None:
        """Test regex match fails."""
        assertion = RegexAssertion()
        config = AssertionConfig(type="regex", value=r"\d+")
        response = make_response("No numbers here!")

        result = assertion.evaluate(response, config)
        assert result.passed is False

    def test_regex_complex_pattern(self) -> None:
        """Test complex regex pattern."""
        assertion = RegexAssertion()
        config = AssertionConfig(type="regex", value=r"(?i)hello.*world")
        response = make_response("Hello there, World!")

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_regex_invalid_pattern(self) -> None:
        """Test invalid regex pattern returns failure."""
        assertion = RegexAssertion()
        config = AssertionConfig(type="regex", value=r"[invalid")
        response = make_response("Hello")

        result = assertion.evaluate(response, config)
        assert result.passed is False
        assert "Invalid regex" in result.message


class TestJsonSchemaAssertion:
    """Tests for JsonSchemaAssertion."""

    def test_json_schema_pass(self) -> None:
        """Test JSON schema validation passes."""
        assertion = JsonSchemaAssertion()
        config = AssertionConfig(
            type="json_schema",
            schema={
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {"type": "string"},
                },
            },
        )
        response = make_response('{"status": "success"}')

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_json_schema_fail_invalid_json(self) -> None:
        """Test JSON schema fails on invalid JSON."""
        assertion = JsonSchemaAssertion()
        config = AssertionConfig(type="json_schema", schema={"type": "object"})
        response = make_response("not json")

        result = assertion.evaluate(response, config)
        assert result.passed is False
        assert "Invalid JSON" in result.message

    def test_json_schema_fail_schema_mismatch(self) -> None:
        """Test JSON schema fails on schema mismatch."""
        assertion = JsonSchemaAssertion()
        config = AssertionConfig(
            type="json_schema",
            schema={
                "type": "object",
                "required": ["status"],
            },
        )
        response = make_response('{"name": "test"}')

        result = assertion.evaluate(response, config)
        assert result.passed is False
        assert "Schema validation failed" in result.message

    def test_json_schema_strips_markdown(self) -> None:
        """Test JSON schema strips markdown code blocks."""
        assertion = JsonSchemaAssertion()
        config = AssertionConfig(
            type="json_schema",
            schema={"type": "object"},
        )
        response = make_response('```json\n{"key": "value"}\n```')

        result = assertion.evaluate(response, config)
        assert result.passed is True


class TestLatencyBudgetAssertion:
    """Tests for LatencyBudgetAssertion."""

    def test_latency_under_budget(self) -> None:
        """Test latency under budget passes."""
        assertion = LatencyBudgetAssertion()
        config = AssertionConfig(type="latency_budget", budget_ms=100.0)
        response = make_response("Hello", latency_ms=50.0)

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_latency_over_budget(self) -> None:
        """Test latency over budget fails."""
        assertion = LatencyBudgetAssertion()
        config = AssertionConfig(type="latency_budget", budget_ms=100.0)
        response = make_response("Hello", latency_ms=150.0)

        result = assertion.evaluate(response, config)
        assert result.passed is False

    def test_latency_exactly_at_budget(self) -> None:
        """Test latency exactly at budget passes."""
        assertion = LatencyBudgetAssertion()
        config = AssertionConfig(type="latency_budget", budget_ms=100.0)
        response = make_response("Hello", latency_ms=100.0)

        result = assertion.evaluate(response, config)
        assert result.passed is True


class TestCostBudgetAssertion:
    """Tests for CostBudgetAssertion."""

    def test_cost_under_budget(self) -> None:
        """Test cost under budget passes."""
        assertion = CostBudgetAssertion()
        config = AssertionConfig(type="cost_budget", budget_dollars=0.01)
        response = make_response("Hello", cost=0.005)

        result = assertion.evaluate(response, config)
        assert result.passed is True

    def test_cost_over_budget(self) -> None:
        """Test cost over budget fails."""
        assertion = CostBudgetAssertion()
        config = AssertionConfig(type="cost_budget", budget_dollars=0.01)
        response = make_response("Hello", cost=0.02)

        result = assertion.evaluate(response, config)
        assert result.passed is False


class TestAssertionRegistry:
    """Tests for AssertionRegistry."""

    def test_list_assertions(self) -> None:
        """Test listing available assertions."""
        assertions = AssertionRegistry.list_assertions()
        assert "exact" in assertions
        assert "contains" in assertions
        assert "regex" in assertions
        assert "json_schema" in assertions
        assert "latency_budget" in assertions
        assert "cost_budget" in assertions

    def test_get_assertion(self) -> None:
        """Test getting assertion by type."""
        assertion = AssertionRegistry.get("contains")
        assert isinstance(assertion, ContainsAssertion)

    def test_unknown_assertion_raises(self) -> None:
        """Test unknown assertion raises ValueError."""
        with pytest.raises(ValueError, match="Unknown assertion type"):
            AssertionRegistry.get("unknown_type")

    def test_assertions_are_cached(self) -> None:
        """Test that assertion instances are cached."""
        assertion1 = AssertionRegistry.get("contains")
        assertion2 = AssertionRegistry.get("contains")
        assert assertion1 is assertion2
