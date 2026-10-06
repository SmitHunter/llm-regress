# Writing Custom Providers

LLM Regress supports pluggable LLM providers. You can add support for any LLM API by implementing the `Provider` interface.

## Basic Structure

Custom providers inherit from the `Provider` base class:

```python
from llm_regress.providers import Provider, ProviderResponse, ProviderRegistry
from llm_regress.config import ProviderConfig


class MyCustomProvider(Provider):
    """Custom LLM provider implementation."""
    
    name = "my_custom"
    
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "default-model",
        base_url: str = "https://api.example.com",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._client = None
    
    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs,
    ) -> ProviderResponse:
        """Generate a completion."""
        import time
        import httpx
        
        model = model or self.model
        start = time.perf_counter()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "prompt": prompt,
                    **kwargs,
                },
            )
            data = response.json()
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        return ProviderResponse(
            content=data["choices"][0]["text"],
            model=model,
            latency_ms=latency_ms,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
            raw_response=data,
        )
    
    @classmethod
    def from_config(cls, config: ProviderConfig) -> "MyCustomProvider":
        """Create provider from configuration."""
        return cls(
            api_key=config.api_key,
            model=config.model or "default-model",
            base_url=config.base_url or "https://api.example.com",
        )


# Register the provider
ProviderRegistry.register("my_custom", MyCustomProvider)
```

## Using Custom Providers

Once registered, reference your provider in YAML test suites:

```yaml
name: Custom Provider Tests
provider:
  name: my_custom
  model: my-model-v1
  api_key: ${MY_CUSTOM_API_KEY}
  base_url: https://my-api.example.com
  options:
    temperature: 0.7

tests:
  - name: Basic test
    prompt: Hello, world!
    assertions:
      - type: contains
        value: hello
```

## ProviderResponse Fields

The `ProviderResponse` dataclass requires these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | `str` | Yes | The generated text |
| `model` | `str` | Yes | Model name used |
| `latency_ms` | `float` | Yes | Response time in milliseconds |
| `input_tokens` | `int` | No | Input token count (default: 0) |
| `output_tokens` | `int` | No | Output token count (default: 0) |
| `cost_dollars` | `float` | No | Estimated cost (default: auto-calculated) |
| `raw_response` | `dict` | No | Raw API response for debugging |
| `cached` | `bool` | No | Whether response is from cache |

## Example: Ollama Provider

```python
import os
import time
from typing import Any

from llm_regress.providers import Provider, ProviderResponse, ProviderRegistry
from llm_regress.config import ProviderConfig


class OllamaProvider(Provider):
    """Provider for Ollama local LLM server."""
    
    name = "ollama"
    
    def __init__(
        self,
        model: str = "llama2",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self.model = model
        self.base_url = base_url
    
    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        import httpx
        
        model = model or self.model
        start = time.perf_counter()
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    **kwargs,
                },
            )
            data = response.json()
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        return ProviderResponse(
            content=data["response"],
            model=model,
            latency_ms=latency_ms,
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            cost_dollars=0.0,  # Local, no cost
            raw_response=data,
        )
    
    @classmethod
    def from_config(cls, config: ProviderConfig) -> "OllamaProvider":
        return cls(
            model=config.model or "llama2",
            base_url=config.base_url or "http://localhost:11434",
        )


ProviderRegistry.register("ollama", OllamaProvider)
```

## Example: Azure OpenAI Provider

```python
class AzureOpenAIProvider(Provider):
    """Provider for Azure OpenAI Service."""
    
    name = "azure_openai"
    
    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        deployment: str = "gpt-35-turbo",
        api_version: str = "2024-02-01",
    ) -> None:
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.deployment = deployment
        self.api_version = api_version
    
    async def complete(
        self,
        prompt: str,
        model: str | None = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        import httpx
        
        deployment = model or self.deployment
        start = time.perf_counter()
        
        url = (
            f"{self.endpoint}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={"api-key": self.api_key},
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    **kwargs,
                },
            )
            data = response.json()
        
        latency_ms = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        
        return ProviderResponse(
            content=data["choices"][0]["message"]["content"],
            model=deployment,
            latency_ms=latency_ms,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw_response=data,
        )
    
    @classmethod
    def from_config(cls, config: ProviderConfig) -> "AzureOpenAIProvider":
        return cls(
            api_key=config.api_key,
            endpoint=config.base_url,
            deployment=config.model or "gpt-35-turbo",
            api_version=config.options.get("api_version", "2024-02-01"),
        )


ProviderRegistry.register("azure_openai", AzureOpenAIProvider)
```

## Configuration via Environment Variables

Providers should support configuration via environment variables:

```python
def __init__(self, api_key: str | None = None) -> None:
    self.api_key = api_key or os.environ.get("MY_PROVIDER_API_KEY")
    if not self.api_key:
        raise ValueError(
            "API key required. Set MY_PROVIDER_API_KEY environment variable "
            "or pass api_key in provider config."
        )
```

## Error Handling

Implement proper error handling and retries:

```python
from tenacity import retry, stop_after_attempt, wait_exponential


class RobustProvider(Provider):
    name = "robust"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _make_request(self, prompt: str, model: str) -> dict:
        """Make API request with retry logic."""
        async with httpx.AsyncClient() as client:
            response = await client.post(...)
            response.raise_for_status()
            return response.json()
    
    async def complete(self, prompt: str, model: str | None = None, **kwargs):
        try:
            data = await self._make_request(prompt, model or self.model)
            return ProviderResponse(...)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"API error: {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError("Request timed out") from e
```

## Testing Your Provider

Create tests for your custom provider:

```python
import pytest
from my_providers import MyCustomProvider

@pytest.mark.asyncio
async def test_custom_provider_completion():
    provider = MyCustomProvider(api_key="test-key")
    response = await provider.complete("Hello")
    
    assert response.content
    assert response.model
    assert response.latency_ms >= 0

def test_custom_provider_from_config():
    from llm_regress.config import ProviderConfig
    
    config = ProviderConfig(
        name="my_custom",
        model="test-model",
        api_key="test-key",
    )
    provider = MyCustomProvider.from_config(config)
    
    assert provider.model == "test-model"
```

## Tips

1. **Lazy initialization**: Don't create HTTP clients in `__init__`; create them in `complete()`
2. **Handle rate limits**: Implement retry logic with exponential backoff
3. **Support streaming**: Consider adding streaming support for long responses
4. **Cost estimation**: Calculate costs based on token counts and model pricing
5. **Timeout handling**: Set appropriate timeouts for API calls
6. **Environment variables**: Support configuration via env vars for secrets
