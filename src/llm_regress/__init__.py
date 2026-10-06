"""
llm-regress: Regression testing framework for LLM prompts and models.

A pip-installable Python library and CLI for regression-testing LLM prompts
and models, designed to run in CI pipelines.
"""

from llm_regress.assertions import (
    Assertion,
    ContainsAssertion,
    CostBudgetAssertion,
    ExactMatchAssertion,
    JsonSchemaAssertion,
    LatencyBudgetAssertion,
    LlmJudgeAssertion,
    RegexAssertion,
    SemanticSimilarityAssertion,
)
from llm_regress.config import TestCase, TestSuite, load_suite, load_suites_from_directory
from llm_regress.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    AnthropicProvider,
    MockProvider,
    OpenAIProvider,
    Provider,
    ProviderRegistry,
)
from llm_regress.runner import RunResult, SuiteResult, TestRunner

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DEFAULT_ANTHROPIC_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "AnthropicProvider",
    "Assertion",
    "ContainsAssertion",
    "CostBudgetAssertion",
    "ExactMatchAssertion",
    "JsonSchemaAssertion",
    "LatencyBudgetAssertion",
    "LlmJudgeAssertion",
    "MockProvider",
    "OpenAIProvider",
    "Provider",
    "ProviderRegistry",
    "RegexAssertion",
    "RunResult",
    "SemanticSimilarityAssertion",
    "SuiteResult",
    "TestCase",
    "TestRunner",
    "TestSuite",
    "load_suite",
    "load_suites_from_directory",
]
