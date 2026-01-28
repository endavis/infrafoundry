"""Unit tests for CLI error catalog."""

from __future__ import annotations

import pytest

from infrafoundry.cli.errors import (
    ERROR_CATALOG,
    ErrorCategory,
    ErrorInfo,
    format_error,
    get_error_code,
    get_error_info,
    list_error_codes,
)
from infrafoundry.core.exceptions import (
    CircularDependencyError,
    ConfigurationError,
    EnvironmentNotFoundError,
    InfraFoundryError,
    InvalidConfigurationError,
    MissingConfigurationError,
    PolicyViolationError,
    ProviderError,
    ProviderNotFoundError,
    SecretDecryptionError,
    SecretNotFoundError,
    StateError,
    TerraformError,
    ValidationError,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_all_categories_exist(self):
        """Verify all expected categories are defined."""
        expected = [
            "CONFIG",
            "PROVIDER",
            "RUNNER",
            "STATE",
            "CREDENTIAL",
            "SECRET",
            "POLICY",
            "VALIDATION",
            "DEPENDENCY",
            "API",
            "TEMPLATE",
            "PLUGIN",
            "SYSTEM",
            "GENERAL",
        ]
        actual = [cat.value for cat in ErrorCategory]
        assert set(expected) == set(actual)

    def test_category_is_string(self):
        """Verify categories are string enums."""
        assert ErrorCategory.CONFIG == "CONFIG"
        assert ErrorCategory.PROVIDER.value == "PROVIDER"


class TestErrorInfo:
    """Tests for ErrorInfo dataclass."""

    def test_error_info_creation(self):
        """Test creating an ErrorInfo instance."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="A test error for testing.",
            suggestions=["Try this", "Or that"],
            see_also="docs/test.md",
        )
        assert info.code == "IF-TEST-001"
        assert info.title == "Test Error"
        assert info.description == "A test error for testing."
        assert info.suggestions == ["Try this", "Or that"]
        assert info.see_also == "docs/test.md"

    def test_error_info_immutable(self):
        """Test ErrorInfo is frozen/immutable."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Test",
            suggestions=[],
        )
        with pytest.raises(AttributeError):
            info.code = "IF-TEST-002"  # type: ignore[misc]

    def test_format_message_basic(self):
        """Test basic message formatting."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Test description",
            suggestions=["Do something"],
        )
        message = info.format_message("Original error message")
        assert "[IF-TEST-001] Test Error" in message
        assert "Original error message" in message
        assert "Do something" in message
        assert "Run with --debug" in message

    def test_format_message_with_verbose(self):
        """Test verbose message formatting includes description."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Detailed description here",
            suggestions=["Suggestion 1"],
        )
        message = info.format_message("Error", verbose=True)
        assert "Detailed description here" in message

    def test_format_message_without_verbose(self):
        """Test non-verbose message excludes description."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Detailed description here",
            suggestions=["Suggestion 1"],
        )
        message = info.format_message("Error", verbose=False)
        assert "Detailed description here" not in message

    def test_format_message_with_see_also(self):
        """Test message includes see_also reference."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Test",
            suggestions=[],
            see_also="docs/reference.md",
        )
        message = info.format_message("Error")
        assert "See: docs/reference.md" in message

    def test_format_message_without_see_also(self):
        """Test message without see_also reference."""
        info = ErrorInfo(
            code="IF-TEST-001",
            title="Test Error",
            description="Test",
            suggestions=[],
            see_also=None,
        )
        message = info.format_message("Error")
        assert "See:" not in message


class TestErrorCatalog:
    """Tests for the error catalog."""

    def test_catalog_not_empty(self):
        """Verify the catalog has entries."""
        assert len(ERROR_CATALOG) > 0

    def test_all_codes_have_correct_format(self):
        """Verify all error codes follow IF-CATEGORY-NNN format."""
        import re

        pattern = re.compile(r"^IF-[A-Z]+-\d{3}$")
        for code in ERROR_CATALOG:
            assert pattern.match(code), f"Invalid code format: {code}"

    def test_all_entries_have_required_fields(self):
        """Verify all catalog entries have required fields."""
        for code, info in ERROR_CATALOG.items():
            assert info.code == code, f"Code mismatch for {code}"
            assert info.title, f"Missing title for {code}"
            assert info.description, f"Missing description for {code}"
            assert isinstance(info.suggestions, list), f"Suggestions not a list for {code}"

    def test_config_error_codes_exist(self):
        """Verify configuration error codes exist."""
        assert "IF-CONFIG-001" in ERROR_CATALOG  # EnvironmentNotFoundError
        assert "IF-CONFIG-002" in ERROR_CATALOG  # InvalidConfigurationError
        assert "IF-CONFIG-003" in ERROR_CATALOG  # MissingConfigurationError

    def test_provider_error_codes_exist(self):
        """Verify provider error codes exist."""
        assert "IF-PROVIDER-001" in ERROR_CATALOG  # ProviderNotFoundError
        assert "IF-PROVIDER-002" in ERROR_CATALOG  # ProviderInitializationError
        assert "IF-PROVIDER-003" in ERROR_CATALOG  # UnsupportedResourceTypeError

    def test_runner_error_codes_exist(self):
        """Verify runner error codes exist."""
        assert "IF-RUNNER-001" in ERROR_CATALOG  # TerraformError
        assert "IF-RUNNER-002" in ERROR_CATALOG  # AnsibleError
        assert "IF-RUNNER-003" in ERROR_CATALOG  # DeploymentError
        assert "IF-RUNNER-004" in ERROR_CATALOG  # RollbackError

    def test_state_error_codes_exist(self):
        """Verify state error codes exist."""
        assert "IF-STATE-001" in ERROR_CATALOG
        assert "IF-STATE-002" in ERROR_CATALOG
        assert "IF-STATE-003" in ERROR_CATALOG
        assert "IF-STATE-004" in ERROR_CATALOG

    def test_system_error_codes_exist(self):
        """Verify system error codes exist."""
        assert "IF-SYSTEM-001" in ERROR_CATALOG  # FileNotFoundError
        assert "IF-SYSTEM-002" in ERROR_CATALOG  # PermissionError
        assert "IF-SYSTEM-003" in ERROR_CATALOG  # IOError
        assert "IF-SYSTEM-004" in ERROR_CATALOG  # Network errors

    def test_general_error_code_exists(self):
        """Verify general fallback error code exists."""
        assert "IF-GENERAL-001" in ERROR_CATALOG


class TestGetErrorCode:
    """Tests for get_error_code function."""

    def test_environment_not_found_error(self):
        """Test EnvironmentNotFoundError maps correctly."""
        exc = EnvironmentNotFoundError("dev")
        assert get_error_code(exc) == "IF-CONFIG-001"

    def test_invalid_configuration_error(self):
        """Test InvalidConfigurationError maps correctly."""
        exc = InvalidConfigurationError("Invalid YAML")
        assert get_error_code(exc) == "IF-CONFIG-002"

    def test_missing_configuration_error(self):
        """Test MissingConfigurationError maps correctly."""
        exc = MissingConfigurationError("Missing field")
        assert get_error_code(exc) == "IF-CONFIG-003"

    def test_generic_configuration_error(self):
        """Test generic ConfigurationError falls back correctly."""
        exc = ConfigurationError("Some config error")
        assert get_error_code(exc) == "IF-CONFIG-002"

    def test_provider_not_found_error(self):
        """Test ProviderNotFoundError maps correctly."""
        exc = ProviderNotFoundError("proxmox")
        assert get_error_code(exc) == "IF-PROVIDER-001"

    def test_generic_provider_error(self):
        """Test generic ProviderError falls back correctly."""
        exc = ProviderError("Some provider error")
        assert get_error_code(exc) == "IF-PROVIDER-002"

    def test_terraform_error(self):
        """Test TerraformError maps correctly."""
        exc = TerraformError("Terraform failed")
        assert get_error_code(exc) == "IF-RUNNER-001"

    def test_state_error(self):
        """Test StateError maps correctly."""
        exc = StateError("State error")
        assert get_error_code(exc) == "IF-STATE-001"

    def test_validation_error(self):
        """Test ValidationError maps correctly."""
        exc = ValidationError("Validation failed")
        assert get_error_code(exc) == "IF-VALIDATION-001"

    def test_circular_dependency_error(self):
        """Test CircularDependencyError maps correctly."""
        exc = CircularDependencyError("Cycle detected")
        assert get_error_code(exc) == "IF-DEPENDENCY-001"

    def test_secret_not_found_error(self):
        """Test SecretNotFoundError maps correctly."""
        exc = SecretNotFoundError("secret.yaml")
        assert get_error_code(exc) == "IF-SECRET-001"

    def test_secret_decryption_error(self):
        """Test SecretDecryptionError maps correctly."""
        exc = SecretDecryptionError("Decryption failed")
        assert get_error_code(exc) == "IF-SECRET-002"

    def test_policy_violation_error(self):
        """Test PolicyViolationError maps correctly."""
        exc = PolicyViolationError("Policy violated")
        assert get_error_code(exc) == "IF-POLICY-001"

    def test_file_not_found_error(self):
        """Test Python FileNotFoundError maps correctly."""
        exc = FileNotFoundError("file.yaml")
        assert get_error_code(exc) == "IF-SYSTEM-001"

    def test_permission_error(self):
        """Test Python PermissionError maps correctly."""
        exc = PermissionError("Access denied")
        assert get_error_code(exc) == "IF-SYSTEM-002"

    def test_io_error(self):
        """Test Python IOError maps correctly."""
        exc = OSError("Disk full")
        assert get_error_code(exc) == "IF-SYSTEM-003"

    def test_unknown_exception_returns_general(self):
        """Test unknown exceptions return IF-GENERAL-001."""
        exc = RuntimeError("Unknown error")
        assert get_error_code(exc) == "IF-GENERAL-001"

    def test_custom_exception_returns_general(self):
        """Test custom exceptions without mapping return IF-GENERAL-001."""

        class CustomError(Exception):
            pass

        exc = CustomError("Custom error")
        assert get_error_code(exc) == "IF-GENERAL-001"

    def test_infrafoundry_subclass_uses_parent_mapping(self):
        """Test subclasses of InfraFoundryError use parent's mapping."""

        class CustomConfigError(ConfigurationError):
            pass

        exc = CustomConfigError("Custom config error")
        # Should use ConfigurationError's mapping via MRO
        assert get_error_code(exc) == "IF-CONFIG-002"


class TestGetErrorInfo:
    """Tests for get_error_info function."""

    def test_valid_code_returns_info(self):
        """Test valid error code returns ErrorInfo."""
        info = get_error_info("IF-CONFIG-001")
        assert info is not None
        assert info.code == "IF-CONFIG-001"
        assert info.title == "Environment Not Found"

    def test_invalid_code_returns_none(self):
        """Test invalid error code returns None."""
        info = get_error_info("IF-INVALID-999")
        assert info is None

    def test_general_error_info(self):
        """Test general error info is retrievable."""
        info = get_error_info("IF-GENERAL-001")
        assert info is not None
        assert info.title == "Unknown Error"


class TestFormatError:
    """Tests for format_error function."""

    def test_format_infrafoundry_error(self):
        """Test formatting an InfraFoundryError."""
        exc = EnvironmentNotFoundError("production")
        result = format_error(exc)
        assert "[IF-CONFIG-001]" in result
        assert "Environment Not Found" in result
        assert "production" in result

    def test_format_with_action(self):
        """Test formatting with action prefix."""
        exc = TerraformError("Init failed")
        result = format_error(exc, action="Apply failed")
        assert "Apply failed" in result
        assert "Init failed" in result

    def test_format_verbose_includes_description(self):
        """Test verbose formatting includes description."""
        exc = ValidationError("Schema mismatch")
        result = format_error(exc, verbose=True)
        # Description should be included in verbose mode
        assert "validation" in result.lower()

    def test_format_unknown_error(self):
        """Test formatting unknown error uses general code."""
        exc = RuntimeError("Something unexpected")
        result = format_error(exc)
        assert "[IF-GENERAL-001]" in result
        assert "Unknown Error" in result

    def test_format_includes_suggestions(self):
        """Test formatting includes suggestions."""
        exc = EnvironmentNotFoundError("dev")
        result = format_error(exc)
        assert "Suggestions:" in result
        assert "foundry config envs" in result

    def test_format_includes_debug_hint(self):
        """Test formatting includes debug hint."""
        exc = StateError("State corrupted")
        result = format_error(exc)
        assert "--debug" in result

    def test_format_error_with_message_attribute(self):
        """Test formatting error that has message attribute."""
        exc = InfraFoundryError("Custom message", context={"key": "value"})
        result = format_error(exc)
        assert "Custom message" in result

    def test_format_python_builtin_error(self):
        """Test formatting Python built-in error."""
        exc = FileNotFoundError("config.yaml not found")
        result = format_error(exc)
        assert "[IF-SYSTEM-001]" in result
        assert "File Not Found" in result


class TestListErrorCodes:
    """Tests for list_error_codes function."""

    def test_list_all_codes(self):
        """Test listing all error codes."""
        codes = list_error_codes()
        assert len(codes) == len(ERROR_CATALOG)

    def test_list_config_codes(self):
        """Test listing CONFIG category codes."""
        codes = list_error_codes(ErrorCategory.CONFIG)
        assert len(codes) >= 3  # At least 3 config errors
        for info in codes:
            assert info.code.startswith("IF-CONFIG-")

    def test_list_provider_codes(self):
        """Test listing PROVIDER category codes."""
        codes = list_error_codes(ErrorCategory.PROVIDER)
        assert len(codes) >= 3
        for info in codes:
            assert info.code.startswith("IF-PROVIDER-")

    def test_list_runner_codes(self):
        """Test listing RUNNER category codes."""
        codes = list_error_codes(ErrorCategory.RUNNER)
        assert len(codes) >= 4
        for info in codes:
            assert info.code.startswith("IF-RUNNER-")

    def test_list_system_codes(self):
        """Test listing SYSTEM category codes."""
        codes = list_error_codes(ErrorCategory.SYSTEM)
        assert len(codes) >= 4
        for info in codes:
            assert info.code.startswith("IF-SYSTEM-")

    def test_list_general_codes(self):
        """Test listing GENERAL category codes."""
        codes = list_error_codes(ErrorCategory.GENERAL)
        assert len(codes) >= 1
        for info in codes:
            assert info.code.startswith("IF-GENERAL-")


class TestErrorCatalogCompleteness:
    """Tests to ensure all exceptions have error codes."""

    def test_all_core_exceptions_mapped(self):
        """Verify all core exception classes have error code mappings."""
        from infrafoundry.core import exceptions

        # Get all exception classes from the module
        exception_classes = [
            name
            for name in dir(exceptions)
            if isinstance(getattr(exceptions, name), type)
            and issubclass(getattr(exceptions, name), Exception)
            and name != "Exception"
        ]

        # Verify each has a mapping (either direct or via parent)
        for exc_name in exception_classes:
            exc_class = getattr(exceptions, exc_name)
            if exc_class is Exception:
                continue
            # Create instance and check it gets a code
            try:
                exc = exc_class("test")
            except TypeError:
                # Some exceptions need additional args
                continue
            code = get_error_code(exc)
            assert code is not None, f"No error code for {exc_name}"
            assert code != "IF-GENERAL-001" or exc_name == "InfraFoundryError", (
                f"Exception {exc_name} should have specific code, not IF-GENERAL-001"
            )
