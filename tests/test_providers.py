"""Tests for LLM providers."""

from __future__ import annotations

import pytest

from llm_regress.config import ProviderConfig
from llm_regress.providers import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    AnthropicProvider,
    MockProvider,
    OpenAIProvider,
    ProviderRegistry,
    ProviderResponse,
)


class TestProviderResponse:
    """Tests for ProviderResponse."""

    def test_basic_response(self) -> None:
        """Test creating a basic response."""
        response = ProviderResponse(
            content="Hello, world!",
            model=DEFAULT_OPENAI_MODEL,
            latency_ms=100.0,
            input_tokens=10,
            output_tokens=5,
        )
        assert response.content == "Hello, world!"
        assert response.model == DEFAULT_OPENAI_MODEL
        assert response.latency_ms == 100.0

    def test_cost_estimation_gpt6_luna(self) -> None:
        """Test cost estimation for gpt-6-luna ($0.10 / $0.50 per 1M tokens)."""
        response = ProviderResponse(
            content="Hello",
            model="gpt-6-luna",
            latency_ms=100.0,
            input_tokens=1000,
            output_tokens=500,
        )
        assert response.cost_dollars == pytest.approx((1000 * 0.10 + 500 * 0.50) / 1_000_000)

    def test_cost_estimation_claude_haiku(self) -> None:
        """Test cost estimation for Claude Haiku 4.5 ($1 / $5 per 1M tokens)."""
        response = ProviderResponse(
            content="Hello",
            model=DEFAULT_ANTHROPIC_MODEL,
            latency_ms=100.0,
            input_tokens=1000,
            output_tokens=500,
        )
        assert response.cost_dollars == pytest.approx((1000 * 1.00 + 500 * 5.00) / 1_000_000)

    def test_cached_flag(self) -> None:
        """Test cached flag."""
        response = ProviderResponse(
            content="Hello",
            model="test",
            latency_ms=50.0,
            cached=True,
        )
        assert response.cached is True


class TestMockProvider:
    """Tests for MockProvider."""

    @pytest.mark.asyncio
    async def test_basic_completion(self) -> None:
        """Test basic completion."""
        provider = MockProvider()
        response = await provider.complete("Hello, world!")
        assert response.content is not None
        assert response.model == "mock-model-v1"
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_configured_responses(self) -> None:
        """Test with configured responses."""
        provider = MockProvider(
            responses={
                "What is the capital of France?": "Paris",
            }
        )
        response = await provider.complete("What is the capital of France?")
        assert response.content == "Paris"

    @pytest.mark.asyncio
    async def test_default_response(self) -> None:
        """Test with default response."""
        provider = MockProvider(default_response="Default answer")
        response = await provider.complete("Any question?")
        assert response.content == "Default answer"

    @pytest.mark.asyncio
    async def test_deterministic_response_capital(self) -> None:
        """Test deterministic response for capital questions."""
        provider = MockProvider()
        response = await provider.complete("What is the capital of France?")
        assert "Paris" in response.content

    @pytest.mark.asyncio
    async def test_deterministic_response_json(self) -> None:
        """Test deterministic response for JSON requests."""
        provider = MockProvider()
        response = await provider.complete("Return a JSON object with status")
        assert "{" in response.content
        assert "}" in response.content

    @pytest.mark.asyncio
    async def test_deterministic_response_code(self) -> None:
        """Test deterministic response for code requests."""
        provider = MockProvider()
        response = await provider.complete("Write a Python function")
        assert "def" in response.content

    @pytest.mark.asyncio
    async def test_judge_prompt_nonempty_output_passes(self) -> None:
        """Judge-style prompts should PASS when the evaluated output is non-empty."""
        provider = MockProvider()
        prompt = (
            "You are evaluating an LLM output against a rubric.\n\n"
            "RUBRIC:\nBe helpful.\n\n"
            "OUTPUT TO EVALUATE:\nThis is a useful answer.\n\n"
            'Respond with exactly "PASS" if the output meets the rubric, or '
            '"FAIL: <reason>" if it does not.\n'
        )
        response = await provider.complete(prompt)
        assert response.content.startswith("PASS")

    @pytest.mark.asyncio
    async def test_judge_prompt_empty_output_fails(self) -> None:
        """Judge-style prompts should FAIL when the evaluated output is empty."""
        provider = MockProvider()
        prompt = (
            "RUBRIC:\nBe helpful.\n\nOUTPUT TO EVALUATE:\n\nRespond with exactly PASS or FAIL.\n"
        )
        response = await provider.complete(prompt)
        assert response.content.startswith("FAIL")

    @pytest.mark.asyncio
    async def test_custom_latency(self) -> None:
        """Test custom latency setting."""
        provider = MockProvider(latency_ms=100.0)
        response = await provider.complete("Hello")
        assert response.latency_ms >= 100.0

    @pytest.mark.asyncio
    async def test_call_count(self) -> None:
        """Test call counting."""
        provider = MockProvider()
        assert provider._call_count == 0

        await provider.complete("First call")
        assert provider._call_count == 1

        await provider.complete("Second call")
        assert provider._call_count == 2

    def test_from_config(self) -> None:
        """Test creating from config."""
        config = ProviderConfig(
            name="mock",
            model="custom-mock",
            options={"latency_ms": 200.0, "default_response": "Configured"},
        )
        provider = MockProvider.from_config(config)
        assert provider.model == "custom-mock"
        assert provider.latency_ms == 200.0
        assert provider.default_response == "Configured"


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_list_providers(self) -> None:
        """Test listing available providers."""
        providers = ProviderRegistry.list_providers()
        assert "mock" in providers
        assert "openai" in providers
        assert "anthropic" in providers

    def test_get_mock_provider(self) -> None:
        """Test getting mock provider from registry."""
        config = ProviderConfig(name="mock")
        provider = ProviderRegistry.get(config)
        assert isinstance(provider, MockProvider)

    def test_unknown_provider_raises(self) -> None:
        """Test that unknown provider raises ValueError."""
        config = ProviderConfig(name="unknown_provider")
        with pytest.raises(ValueError, match="Unknown provider"):
            ProviderRegistry.get(config)

    def test_register_custom_provider(self) -> None:
        """Test registering a custom provider."""

        class CustomProvider(MockProvider):
            name = "custom"

        ProviderRegistry.register("custom", CustomProvider)
        assert "custom" in ProviderRegistry.list_providers()

        config = ProviderConfig(name="custom")
        provider = ProviderRegistry.get(config)
        assert isinstance(provider, CustomProvider)


class TestProviderDefaults:
    """Tests for current default model IDs."""

    def test_openai_default_model(self) -> None:
        """OpenAI defaults to the current inexpensive GA model."""
        provider = OpenAIProvider.from_config(ProviderConfig(name="openai"))
        assert provider.model == DEFAULT_OPENAI_MODEL
        assert provider.model == "gpt-6-luna"

    def test_anthropic_default_model(self) -> None:
        """Anthropic defaults to the current inexpensive GA model."""
        provider = AnthropicProvider.from_config(ProviderConfig(name="anthropic"))
        assert provider.model == DEFAULT_ANTHROPIC_MODEL
        assert provider.model == "claude-haiku-4-5"
