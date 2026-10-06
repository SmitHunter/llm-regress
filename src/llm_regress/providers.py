"""LLM provider implementations with pluggable architecture."""

from __future__ import annotations

import hashlib
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from llm_regress.config import ProviderConfig

# Current inexpensive, generally available defaults (retrieved 2026-10-06).
# OpenAI: https://developers.openai.com/api/docs/models/gpt-6-luna
# Anthropic: https://platform.claude.com/docs/en/models/overview.md
#   Claude API ID is the pinned snapshot claude-haiku-4-5-20251001;
#   claude-haiku-4-5 is the documented alias for that snapshot.
DEFAULT_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"


@dataclass
class ProviderResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_dollars: float = 0.0
    raw_response: dict[str, Any] = field(default_factory=dict)
    cached: bool = False

    def __post_init__(self) -> None:
        """Estimate cost if not provided."""
        if self.cost_dollars == 0.0 and (self.input_tokens > 0 or self.output_tokens > 0):
            self.cost_dollars = self._estimate_cost()

    def _estimate_cost(self) -> float:
        """Estimate cost from published short-context list prices.

        Rates are USD per million tokens. Approximate only: billed cost can
        differ by tier, caching, batch, and long-context pricing.

        Sources (retrieved 2026-10-06):
        - OpenAI: https://developers.openai.com/api/docs/pricing
        - Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
        """
        model_lower = self.model.lower()
        # (match, input_usd_per_mtok, output_usd_per_mtok)
        rates: list[tuple[str, float, float]] = [
            ("gpt-6-luna", 0.10, 0.50),
            ("gpt-6.1-sol", 2.00, 10.00),
            ("gpt-6-astra", 10.00, 50.00),
            ("claude-haiku", 1.00, 5.00),
            ("claude-sonnet", 2.00, 10.00),
            ("claude-opus", 4.00, 20.00),
            ("claude-fable", 10.00, 50.00),
        ]
        input_per_mtok = 1.00
        output_per_mtok = 5.00
        for needle, in_rate, out_rate in rates:
            if needle in model_lower:
                input_per_mtok = in_rate
                output_per_mtok = out_rate
                break
        return (
            self.input_tokens * input_per_mtok + self.output_tokens * output_per_mtok
        ) / 1_000_000


class Provider(ABC):
    """Abstract base class for LLM providers."""

    name: ClassVar[str] = "base"

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion for the given prompt.

        Args:
            prompt: The prompt to complete.
            model: Optional model override.
            **kwargs: Additional provider-specific options.

        Returns:
            ProviderResponse with the completion.
        """
        ...

    @classmethod
    def from_config(cls, config: ProviderConfig) -> Provider:
        """Create a provider instance from config."""
        raise NotImplementedError


class MockProvider(Provider):
    """Mock provider for testing without API calls.

    Supports deterministic responses based on prompt hashing,
    configurable responses, and simulated latency/costs.
    """

    name: ClassVar[str] = "mock"

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default_response: str | None = None,
        latency_ms: float = 50.0,
        model: str = "mock-model-v1",
    ) -> None:
        """Initialize the mock provider.

        Args:
            responses: Map of prompt hashes or exact prompts to responses.
            default_response: Default response when no match found.
            latency_ms: Simulated latency in milliseconds.
            model: Model name to report.
        """
        self.responses = responses or {}
        self.default_response = default_response
        self.latency_ms = latency_ms
        self.model = model
        self._call_count = 0

    def _get_response(self, prompt: str) -> str:
        """Get the response for a prompt."""
        if prompt in self.responses:
            return self.responses[prompt]

        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        if prompt_hash in self.responses:
            return self.responses[prompt_hash]

        if self.default_response is not None:
            return self.default_response

        return self._generate_deterministic_response(prompt)

    def _generate_deterministic_response(self, prompt: str) -> str:
        """Generate a deterministic response based on prompt content."""
        prompt_lower = prompt.lower()

        if "rubric:" in prompt_lower and "output to evaluate:" in prompt_lower:
            marker = "output to evaluate:"
            start = prompt_lower.rfind(marker)
            rest = prompt[start + len(marker) :]
            for sep in ("\n\nRespond", "\nRespond"):
                cut = rest.lower().find(sep.lower())
                if cut != -1:
                    rest = rest[:cut]
                    break
            if rest.strip():
                return "PASS"
            return "FAIL: empty output"

        if "json" in prompt_lower or "schema" in prompt_lower:
            return '{"status": "success", "result": 42, "items": ["a", "b", "c"]}'

        if "capital" in prompt_lower:
            if "france" in prompt_lower:
                return "Paris"
            if "australia" in prompt_lower:
                return "Canberra"
            if "japan" in prompt_lower:
                return "Tokyo"
            return "The capital is a major city in that country."

        if "explain" in prompt_lower or "what is" in prompt_lower:
            return (
                "This is a comprehensive explanation of the topic. "
                "It covers the key concepts, provides examples, and "
                "offers practical insights for understanding."
            )

        if "summarize" in prompt_lower or "summary" in prompt_lower:
            return (
                "Summary: The main points are clearly articulated, "
                "the argument is well-structured, and the conclusion "
                "follows logically from the premises."
            )

        if "code" in prompt_lower or "function" in prompt_lower:
            return "def solution():\n    return 42"

        if "yes" in prompt_lower and "no" in prompt_lower:
            return "Yes"

        if "list" in prompt_lower:
            return "1. First item\n2. Second item\n3. Third item"

        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        return f"Mock response for prompt (hash: {prompt_hash[:8]})"

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,  # noqa: ARG002
    ) -> ProviderResponse:
        """Generate a mock completion."""
        self._call_count += 1
        start = time.perf_counter()

        response_text = self._get_response(prompt)
        input_tokens = len(prompt.split())
        output_tokens = len(response_text.split())

        elapsed_ms = (time.perf_counter() - start) * 1000
        total_latency = max(elapsed_ms, self.latency_ms)

        return ProviderResponse(
            content=response_text,
            model=model or self.model,
            latency_ms=total_latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_dollars=0.0,
            raw_response={"mock": True, "call_number": self._call_count},
        )

    @classmethod
    def from_config(cls, config: ProviderConfig) -> MockProvider:
        """Create from config."""
        return cls(
            model=config.model or "mock-model-v1",
            latency_ms=config.options.get("latency_ms", 50.0),
            default_response=config.options.get("default_response"),
            responses=config.options.get("responses", {}),
        )


class OpenAIProvider(Provider):
    """OpenAI API provider."""

    name: ClassVar[str] = "openai"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        base_url: str | None = None,
    ) -> None:
        """Initialize the OpenAI provider."""
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as e:
                raise ImportError(
                    "OpenAI provider requires the 'openai' package. "
                    "Install with: pip install llm-regress[openai]"
                ) from e

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion using OpenAI."""
        client = self._get_client()
        model = model or self.model
        start = time.perf_counter()

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        latency_ms = (time.perf_counter() - start) * 1000

        content = response.choices[0].message.content or ""
        usage = response.usage

        return ProviderResponse(
            content=content,
            model=model,
            latency_ms=latency_ms,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            raw_response=response.model_dump(),
        )

    @classmethod
    def from_config(cls, config: ProviderConfig) -> OpenAIProvider:
        """Create from config."""
        return cls(
            api_key=config.api_key,
            model=config.model or DEFAULT_OPENAI_MODEL,
            base_url=config.base_url,
        )


class AnthropicProvider(Provider):
    """Anthropic Claude API provider."""

    name: ClassVar[str] = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        max_tokens: int = 1024,
    ) -> None:
        """Initialize the Anthropic provider."""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as e:
                raise ImportError(
                    "Anthropic provider requires the 'anthropic' package. "
                    "Install with: pip install llm-regress[anthropic]"
                ) from e

            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a completion using Anthropic."""
        client = self._get_client()
        model = model or self.model
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        start = time.perf_counter()

        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        latency_ms = (time.perf_counter() - start) * 1000

        content = response.content[0].text if response.content else ""

        return ProviderResponse(
            content=content,
            model=model,
            latency_ms=latency_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            raw_response={"id": response.id, "model": response.model},
        )

    @classmethod
    def from_config(cls, config: ProviderConfig) -> AnthropicProvider:
        """Create from config."""
        return cls(
            api_key=config.api_key,
            model=config.model or DEFAULT_ANTHROPIC_MODEL,
            max_tokens=config.options.get("max_tokens", 1024),
        )


class ProviderRegistry:
    """Registry for LLM providers with lazy initialization."""

    _providers: ClassVar[dict[str, type[Provider]]] = {
        "mock": MockProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class: type[Provider]) -> None:
        """Register a custom provider.

        Args:
            name: Name to register the provider under.
            provider_class: Provider class to register.
        """
        cls._providers[name] = provider_class

    @classmethod
    def get(cls, config: ProviderConfig) -> Provider:
        """Get a provider instance from config.

        Args:
            config: Provider configuration.

        Returns:
            Configured provider instance.

        Raises:
            ValueError: If the provider is not registered.
        """
        if config.name not in cls._providers:
            available = ", ".join(sorted(cls._providers.keys()))
            raise ValueError(f"Unknown provider '{config.name}'. Available providers: {available}")

        provider_class = cls._providers[config.name]
        return provider_class.from_config(config)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return sorted(cls._providers.keys())
