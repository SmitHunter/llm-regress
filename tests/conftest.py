"""Pytest configuration and fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from llm_regress.providers import MockProvider


@pytest.fixture
def tmp_yaml_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary YAML test file."""
    yaml_content = """
name: Test Suite
description: A test suite for testing
provider: mock

tests:
  - name: Simple test
    prompt: What is 2 + 2?
    assertions:
      - type: contains
        value: "4"
"""
    yaml_file = tmp_path / "test_suite.yaml"
    yaml_file.write_text(yaml_content)
    yield yaml_file


@pytest.fixture
def complex_yaml_file(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a complex YAML test file with multiple assertions."""
    yaml_content = """
name: Complex Test Suite
description: Tests with various assertion types
provider:
  name: mock
  model: mock-v1
  options:
    latency_ms: 10

defaults:
  language: Python

tests:
  - name: Capital test
    prompt: What is the capital of France?
    assertions:
      - type: contains
        value: Paris

  - name: JSON test
    prompt: Return JSON with status success
    assertions:
      - type: json_schema
        schema:
          type: object
          required: [status]
          properties:
            status:
              type: string

  - name: Regex test
    prompt: Say hello in any language
    assertions:
      - type: regex
        value: "(?i)hello|hola|bonjour"

  - name: Latency test
    prompt: Quick response please
    assertions:
      - type: latency_budget
        budget_ms: 1000

  - name: Multiple assertions
    prompt: What is the capital of {{ country }}?
    inputs:
      country: Australia
    assertions:
      - type: contains
        value: Canberra
      - type: latency_budget
        budget_ms: 500
    tags:
      - geography
      - capitals
"""
    yaml_file = tmp_path / "complex_suite.yaml"
    yaml_file.write_text(yaml_content)
    yield yaml_file


@pytest.fixture
def mock_provider() -> MockProvider:
    """Create a mock provider instance."""
    from llm_regress.providers import MockProvider as MP

    return MP(
        responses={
            "What is the capital of France?": "Paris",
            "What is 2 + 2?": "4",
        },
        default_response="Mock response",
        latency_ms=10,
    )
