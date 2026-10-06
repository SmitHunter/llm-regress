"""Tests for configuration and YAML loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from llm_regress.config import (
    AssertionConfig,
    ProviderConfig,
    TestCase,
    TestSuite,
    expand_env_vars,
    load_suite,
    load_suites_from_directory,
)


class TestAssertionConfig:
    """Tests for AssertionConfig."""

    def test_basic_assertion(self) -> None:
        """Test creating a basic assertion config."""
        config = AssertionConfig(type="contains", value="test")
        assert config.type == "contains"
        assert config.value == "test"

    def test_json_schema_assertion(self) -> None:
        """Test creating a JSON schema assertion config."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        config = AssertionConfig(type="json_schema", schema=schema)
        assert config.type == "json_schema"
        assert config.schema_ == schema

    def test_latency_budget_assertion(self) -> None:
        """Test creating a latency budget assertion config."""
        config = AssertionConfig(type="latency_budget", budget_ms=500.0)
        assert config.type == "latency_budget"
        assert config.budget_ms == 500.0


class TestTestCase:
    """Tests for TestCase."""

    def test_basic_test_case(self) -> None:
        """Test creating a basic test case."""
        test = TestCase(
            name="test1",
            prompt="Hello",
            assertions=[AssertionConfig(type="contains", value="hi")],
        )
        assert test.name == "test1"
        assert test.prompt == "Hello"
        assert len(test.assertions) == 1

    def test_assertion_shorthand_parsing(self) -> None:
        """Test parsing assertion shorthand strings."""
        test = TestCase(
            name="test1",
            prompt="Hello",
            assertions=["contains:world", "regex:hello.*"],  # type: ignore
        )
        assert len(test.assertions) == 2
        assert test.assertions[0].type == "contains"
        assert test.assertions[0].value == "world"
        assert test.assertions[1].type == "regex"
        assert test.assertions[1].value == "hello.*"

    def test_test_case_with_inputs(self) -> None:
        """Test case with template inputs."""
        test = TestCase(
            name="template_test",
            prompt="Hello {{ name }}",
            inputs={"name": "World"},
            assertions=[AssertionConfig(type="contains", value="hello")],
        )
        assert test.inputs["name"] == "World"

    def test_test_case_with_tags(self) -> None:
        """Test case with tags."""
        test = TestCase(
            name="tagged_test",
            prompt="Test",
            assertions=[AssertionConfig(type="contains", value="test")],
            tags=["smoke", "quick"],
        )
        assert "smoke" in test.tags
        assert "quick" in test.tags


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_basic_provider_config(self) -> None:
        """Test creating a basic provider config."""
        config = ProviderConfig(name="openai", model="gpt-6-luna")
        assert config.name == "openai"
        assert config.model == "gpt-6-luna"

    def test_provider_with_options(self) -> None:
        """Test provider config with additional options."""
        config = ProviderConfig(
            name="mock",
            model="mock-v1",
            options={"latency_ms": 100},
        )
        assert config.options["latency_ms"] == 100


class TestTestSuite:
    """Tests for TestSuite."""

    def test_basic_suite(self) -> None:
        """Test creating a basic test suite."""
        suite = TestSuite(
            name="My Suite",
            tests=[
                TestCase(
                    name="test1",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="hi")],
                )
            ],
        )
        assert suite.name == "My Suite"
        assert len(suite.tests) == 1

    def test_suite_with_string_provider(self) -> None:
        """Test suite with provider as string."""
        suite = TestSuite(
            name="Suite",
            provider="mock",
            tests=[
                TestCase(
                    name="test1",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="hi")],
                )
            ],
        )
        config = suite.get_provider_config()
        assert config.name == "mock"

    def test_suite_with_dict_provider(self) -> None:
        """Test suite with provider as dict."""
        suite = TestSuite(
            name="Suite",
            provider=ProviderConfig(name="openai", model="gpt-6-luna"),
            tests=[
                TestCase(
                    name="test1",
                    prompt="Hello",
                    assertions=[AssertionConfig(type="contains", value="hi")],
                )
            ],
        )
        config = suite.get_provider_config()
        assert config.name == "openai"
        assert config.model == "gpt-6-luna"


class TestLoadSuite:
    """Tests for load_suite function."""

    def test_load_simple_suite(self, tmp_yaml_file: Path) -> None:
        """Test loading a simple suite from YAML."""
        suite = load_suite(tmp_yaml_file)
        assert suite.name == "Test Suite"
        assert len(suite.tests) == 1
        assert suite.tests[0].name == "Simple test"

    def test_load_complex_suite(self, complex_yaml_file: Path) -> None:
        """Test loading a complex suite with multiple tests."""
        suite = load_suite(complex_yaml_file)
        assert suite.name == "Complex Test Suite"
        assert len(suite.tests) == 5

        capital_test = suite.tests[0]
        assert capital_test.name == "Capital test"
        assert capital_test.assertions[0].type == "contains"

        json_test = suite.tests[1]
        assert json_test.assertions[0].type == "json_schema"
        assert json_test.assertions[0].schema_ is not None

    def test_load_nonexistent_file(self) -> None:
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_suite(Path("/nonexistent/file.yaml"))

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML raises error."""
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("name: [invalid yaml: no closing bracket")

        with pytest.raises(yaml.YAMLError):
            load_suite(invalid_file)

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """Empty YAML files should produce a clear error."""
        empty = tmp_path / "empty.yaml"
        empty.write_text("")

        with pytest.raises(ValueError, match="empty"):
            load_suite(empty)

    def test_load_non_mapping(self, tmp_path: Path) -> None:
        """A YAML list is not a valid suite."""
        listed = tmp_path / "list.yaml"
        listed.write_text("- just a list\n")

        with pytest.raises(ValueError, match="mapping"):
            load_suite(listed)

    def test_expand_env_vars_in_suite(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """${VAR} placeholders in YAML should expand from the environment."""
        monkeypatch.setenv("LLM_REGRESS_TEST_MODEL", "gpt-test")
        monkeypatch.delenv("LLM_REGRESS_TEST_UNSET", raising=False)

        suite_file = tmp_path / "env.yaml"
        suite_file.write_text(
            """
name: Env Suite
provider:
  name: mock
  model: ${LLM_REGRESS_TEST_MODEL}
  api_key: ${LLM_REGRESS_TEST_UNSET}
tests:
  - name: one
    prompt: Hello ${LLM_REGRESS_TEST_MODEL}
    assertions:
      - type: contains
        value: Hello
"""
        )
        suite = load_suite(suite_file)
        config = suite.get_provider_config()
        assert config.model == "gpt-test"
        assert config.api_key is None
        assert suite.tests[0].prompt == "Hello gpt-test"

    def test_expand_env_default(self) -> None:
        """${VAR:-default} uses the default when unset."""
        os.environ.pop("LLM_REGRESS_MISSING_DEFAULT", None)
        assert expand_env_vars("x-${LLM_REGRESS_MISSING_DEFAULT:-fallback}") == "x-fallback"


class TestLoadSuitesFromDirectory:
    """Tests for load_suites_from_directory function."""

    def test_load_from_directory(self, tmp_path: Path) -> None:
        """Test loading multiple suites from a directory."""
        suite1 = tmp_path / "suite1.yaml"
        suite2 = tmp_path / "suite2.yaml"

        suite1.write_text("""
name: Suite 1
provider: mock
tests:
  - name: test1
    prompt: Hello
    assertions:
      - type: contains
        value: hi
""")

        suite2.write_text("""
name: Suite 2
provider: mock
tests:
  - name: test2
    prompt: World
    assertions:
      - type: contains
        value: world
""")

        suites = load_suites_from_directory(tmp_path)
        assert len(suites) == 2
        names = {s.name for s in suites}
        assert "Suite 1" in names
        assert "Suite 2" in names

    def test_load_recursive(self, tmp_path: Path) -> None:
        """Test loading suites recursively."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        (tmp_path / "suite1.yaml").write_text("""
name: Suite 1
provider: mock
tests:
  - name: test1
    prompt: Hello
    assertions: [contains:hi]
""")

        (subdir / "suite2.yaml").write_text("""
name: Suite 2
provider: mock
tests:
  - name: test2
    prompt: World
    assertions: [contains:world]
""")

        suites = load_suites_from_directory(tmp_path, recursive=True)
        assert len(suites) == 2

        suites_non_recursive = load_suites_from_directory(tmp_path, recursive=False)
        assert len(suites_non_recursive) == 1

    def test_load_yml_extension(self, tmp_path: Path) -> None:
        """Directories should pick up .yml files as well as .yaml."""
        (tmp_path / "suite.yml").write_text("""
name: Yml Suite
provider: mock
tests:
  - name: test1
    prompt: Hello
    assertions:
      - type: contains
        value: hi
""")
        suites = load_suites_from_directory(tmp_path)
        assert len(suites) == 1
        assert suites[0].name == "Yml Suite"
