"""Configuration and test suite loading from YAML files."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

_ENV_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_SOLE_ENV_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def expand_env_vars(value: Any) -> Any:
    """Expand ``${VAR}`` and ``${VAR:-default}`` placeholders.

    A string that is only ``${VAR}`` becomes ``None`` when the variable is
    unset, so optional fields such as ``api_key`` fall back to the provider's
    own environment lookup instead of sending a literal ``${...}`` string.
    """
    if isinstance(value, str):
        sole = _SOLE_ENV_PLACEHOLDER.fullmatch(value)
        if sole:
            return os.environ.get(sole.group(1))

        def _replace(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2)
            found = os.environ.get(name)
            if found is not None:
                return found
            if default is not None:
                return default
            return match.group(0)

        return _ENV_PLACEHOLDER.sub(_replace, value)
    if isinstance(value, dict):
        return {key: expand_env_vars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


class AssertionConfig(BaseModel):
    """Configuration for a single assertion."""

    type: str
    value: Any = None
    threshold: float | None = None
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    rubric: str | None = None
    judge_model: str | None = None
    budget_ms: float | None = None
    budget_dollars: float | None = None

    model_config = {"populate_by_name": True}


class TestCase(BaseModel):
    """A single test case with prompt, inputs, and assertions."""

    __test__ = False

    name: str
    description: str | None = None
    prompt: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    assertions: list[AssertionConfig]
    tags: list[str] = Field(default_factory=list)
    timeout_ms: float | None = None

    @field_validator("assertions", mode="before")
    @classmethod
    def parse_assertions(cls, v: Any) -> list[AssertionConfig]:
        """Parse assertion configs from various formats."""
        if not isinstance(v, list):
            v = [v]
        result = []
        for item in v:
            if isinstance(item, str):
                if item.startswith("contains:"):
                    result.append(AssertionConfig(type="contains", value=item[9:].strip()))
                elif item.startswith("regex:"):
                    result.append(AssertionConfig(type="regex", value=item[6:].strip()))
                elif item.startswith("exact:"):
                    result.append(AssertionConfig(type="exact", value=item[6:].strip()))
                else:
                    result.append(AssertionConfig(type="contains", value=item))
            elif isinstance(item, dict):
                result.append(AssertionConfig(**item))
            else:
                result.append(item)
        return result


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    name: str
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class TestSuite(BaseModel):
    """A test suite containing multiple test cases."""

    __test__ = False

    name: str
    description: str | None = None
    provider: ProviderConfig | str = "mock"
    defaults: dict[str, Any] = Field(default_factory=dict)
    tests: list[TestCase]
    tags: list[str] = Field(default_factory=list)
    parallel: bool = True
    max_concurrency: int = 5

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider(cls, v: Any) -> ProviderConfig | str:
        """Parse provider config from string or dict."""
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return ProviderConfig(**v)
        if isinstance(v, ProviderConfig):
            return v
        raise ValueError(f"Invalid provider config type: {type(v)}")

    def get_provider_config(self) -> ProviderConfig:
        """Get the provider config, converting from string if needed."""
        if isinstance(self.provider, str):
            return ProviderConfig(name=self.provider)
        return self.provider


def load_suite(path: Path | str) -> TestSuite:
    """Load a test suite from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed TestSuite object.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file is not valid YAML.
        pydantic.ValidationError: If the YAML doesn't match the schema.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Test suite not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"{path} is empty")
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping with at least 'name' and 'tests'")

    return TestSuite(**expand_env_vars(data))


def _suite_files(directory: Path, pattern: str, recursive: bool) -> list[Path]:
    """Collect YAML suite files, including both .yaml and .yml by default."""
    globber = directory.rglob if recursive else directory.glob
    files = list(globber(pattern))
    if pattern == "*.yaml":
        files.extend(globber("*.yml"))
    return sorted(set(files))


def load_suites_from_directory(
    directory: Path | str,
    pattern: str = "*.yaml",
    recursive: bool = True,
) -> list[TestSuite]:
    """Load all test suites from a directory.

    Args:
        directory: Directory to search for YAML files.
        pattern: Glob pattern for matching files.
        recursive: Whether to search subdirectories.

    Returns:
        List of parsed TestSuite objects.
    """
    directory = Path(directory)
    files = _suite_files(directory, pattern, recursive)

    suites = []
    for file_path in files:
        try:
            suite = load_suite(file_path)
            suites.append(suite)
        except Exception as e:
            raise RuntimeError(f"Failed to load suite from {file_path}: {e}") from e

    return suites
