# Writing Custom Assertions

LLM Regress's assertion system is fully extensible. You can create custom assertions to validate LLM outputs against domain-specific criteria.

## Basic Structure

Custom assertions inherit from the `Assertion` base class and implement the `evaluate` method:

```python
from llm_regress.assertions import Assertion, AssertionResult, AssertionRegistry
from llm_regress.config import AssertionConfig
from llm_regress.providers import ProviderResponse


class SentimentAssertion(Assertion):
    """Assert that the response has a specific sentiment."""
    
    name = "sentiment"
    
    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        """Evaluate sentiment of the response."""
        expected_sentiment = config.value  # "positive", "negative", "neutral"
        content = response.content.lower()
        
        # Simple keyword-based sentiment (use a real library in production)
        positive_words = ["great", "good", "excellent", "happy", "love"]
        negative_words = ["bad", "terrible", "hate", "awful", "poor"]
        
        pos_count = sum(1 for w in positive_words if w in content)
        neg_count = sum(1 for w in negative_words if w in content)
        
        if pos_count > neg_count:
            detected = "positive"
        elif neg_count > pos_count:
            detected = "negative"
        else:
            detected = "neutral"
        
        passed = detected == expected_sentiment
        
        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=f"Detected '{detected}' sentiment" if passed else f"Expected '{expected_sentiment}', got '{detected}'",
            expected=expected_sentiment,
            actual=detected,
            details={"positive_count": pos_count, "negative_count": neg_count},
        )


# Register the assertion
AssertionRegistry.register("sentiment", SentimentAssertion)
```

## Using Custom Assertions

Once registered, use your assertion in YAML test suites:

```yaml
name: Sentiment Tests
provider: mock

tests:
  - name: Positive response
    prompt: Write a happy message
    assertions:
      - type: sentiment
        value: positive
```

## AssertionResult Fields

The `AssertionResult` dataclass has these fields:

| Field | Type | Description |
|-------|------|-------------|
| `passed` | `bool` | Whether the assertion passed |
| `assertion_type` | `str` | Name of the assertion type |
| `message` | `str` | Human-readable result message |
| `expected` | `Any` | Expected value (optional) |
| `actual` | `Any` | Actual value from response (optional) |
| `details` | `dict` | Additional details for debugging (optional) |

## Accessing Response Data

The `ProviderResponse` object provides:

```python
response.content       # str: The LLM's text output
response.model         # str: Model name used
response.latency_ms    # float: Response time in milliseconds
response.input_tokens  # int: Input token count
response.output_tokens # int: Output token count
response.cost_dollars  # float: Estimated cost
response.raw_response  # dict: Provider-specific raw response
response.cached        # bool: Whether this was a cached response
```

## Assertion Configuration

The `AssertionConfig` object provides:

```python
config.type           # str: Assertion type name
config.value          # Any: Primary value for the assertion
config.threshold      # float | None: Numeric threshold
config.schema_        # dict | None: JSON schema (use schema_ due to Pydantic)
config.rubric         # str | None: LLM judge rubric
config.budget_ms      # float | None: Latency budget
config.budget_dollars # float | None: Cost budget
```

## Example: Word Count Assertion

```python
class WordCountAssertion(Assertion):
    """Assert response has expected word count."""
    
    name = "word_count"
    
    def evaluate(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        words = response.content.split()
        actual_count = len(words)
        
        # config.value could be "min:50" or "max:100" or "50-100"
        requirement = str(config.value)
        
        if requirement.startswith("min:"):
            min_count = int(requirement[4:])
            passed = actual_count >= min_count
            message = f"{actual_count} words {'≥' if passed else '<'} {min_count}"
        elif requirement.startswith("max:"):
            max_count = int(requirement[4:])
            passed = actual_count <= max_count
            message = f"{actual_count} words {'≤' if passed else '>'} {max_count}"
        elif "-" in requirement:
            min_count, max_count = map(int, requirement.split("-"))
            passed = min_count <= actual_count <= max_count
            message = f"{actual_count} words in range [{min_count}, {max_count}]"
        else:
            expected = int(requirement)
            passed = actual_count == expected
            message = f"{actual_count} words {'==' if passed else '!='} {expected}"
        
        return AssertionResult(
            passed=passed,
            assertion_type=self.name,
            message=message,
            expected=requirement,
            actual=actual_count,
        )

AssertionRegistry.register("word_count", WordCountAssertion)
```

Usage:

```yaml
tests:
  - name: Concise response
    prompt: Briefly explain recursion
    assertions:
      - type: word_count
        value: "max:50"
  
  - name: Detailed explanation
    prompt: Write a comprehensive guide to Python
    assertions:
      - type: word_count
        value: "100-500"
```

## Async Assertions

For assertions that need async operations (like calling external APIs), implement `evaluate_async`:

```python
class ExternalValidatorAssertion(Assertion):
    name = "external_validator"
    
    async def evaluate_async(
        self,
        response: ProviderResponse,
        config: AssertionConfig,
    ) -> AssertionResult:
        # Async external API call
        import httpx
        async with httpx.AsyncClient() as client:
            result = await client.post(
                "https://api.validator.example/check",
                json={"content": response.content},
            )
            is_valid = result.json()["valid"]
        
        return AssertionResult(
            passed=is_valid,
            assertion_type=self.name,
            message="External validation " + ("passed" if is_valid else "failed"),
        )
    
    def evaluate(self, response, config):
        """Sync wrapper for async evaluation."""
        import asyncio
        return asyncio.run(self.evaluate_async(response, config))
```

## Tips

1. **Keep assertions focused**: Each assertion should check one thing
2. **Provide clear messages**: Help users understand why assertions fail
3. **Include details**: Add debugging info in the `details` dict
4. **Handle edge cases**: Check for empty responses, None values
5. **Consider performance**: Avoid heavy computation in assertions
