"""Tests for base provider validation helpers."""

from unittest.mock import Mock, patch

import pytest

from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseProviderValidator, ResourceValidator


class TestBaseProviderValidator:
    """Tests for BaseProviderValidator class."""

    @pytest.fixture
    def env_config(self):
        """Sample environment configuration."""
        return {
            "provider_settings": {
                "test_provider": {
                    "api_url": "https://api.example.com",
                    "api_key": "test-key",
                    "api_secret": "test-secret",
                }
            }
        }

    @pytest.fixture
    def report(self):
        """Mock validation report."""
        return Mock(spec=ValidationReport)

    @pytest.fixture
    def validator(self, env_config, report):
        """Create validator instance."""
        return BaseProviderValidator(
            provider_name="test_provider",
            env_config=env_config,
            report=report,
        )

    def test_init(self, validator, env_config, report):
        """Test validator initialization."""
        assert validator.provider_name == "test_provider"
        assert validator.env_config == env_config
        assert validator.report == report
        assert validator.provider_settings == env_config["provider_settings"]["test_provider"]

    def test_validate_credentials_success(self, validator, report):
        """Test successful credential validation."""
        credentials = validator.validate_credentials(
            required_fields=["api_url", "api_key", "api_secret"]
        )

        assert credentials == {
            "api_url": "https://api.example.com",
            "api_key": "test-key",
            "api_secret": "test-secret",
        }
        report.add_check.assert_not_called()

    def test_validate_credentials_missing_fields(self, validator, report):
        """Test credential validation with missing fields."""
        credentials = validator.validate_credentials(
            required_fields=["api_url", "api_key", "api_secret", "missing_field"]
        )

        assert credentials is None
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["check_name"] == "test_provider_credentials"
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR
        assert "missing_field" in call_args["message"]

    def test_validate_credentials_with_env_vars(self, validator, report):
        """Test credential validation with environment variables."""
        # Remove provider settings
        validator.provider_settings = {}

        with patch.dict(
            "os.environ",
            {
                "TEST_API_URL": "https://env.example.com",
                "TEST_API_KEY": "env-key",
                "TEST_API_SECRET": "env-secret",
            },
        ):
            credentials = validator.validate_credentials(
                required_fields=["api_url", "api_key", "api_secret"],
                env_vars={
                    "api_url": "TEST_API_URL",
                    "api_key": "TEST_API_KEY",
                    "api_secret": "TEST_API_SECRET",
                },
            )

        assert credentials == {
            "api_url": "https://env.example.com",
            "api_key": "env-key",
            "api_secret": "env-secret",
        }

    def test_check_api_connectivity_success(self, validator, report):
        """Test successful API connectivity check."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("requests.request", return_value=mock_response):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is True
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["check_name"] == "test_provider_connectivity"
        assert call_args["passed"] is True
        assert call_args["level"] == ValidationLevel.INFO

    def test_check_api_connectivity_custom_success_message(self, validator, report):
        """Test API connectivity with custom success message."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("requests.request", return_value=mock_response):
            result = validator.check_api_connectivity(
                url="https://api.example.com/status",
                success_message="Custom success message",
            )

        assert result is True
        call_args = report.add_check.call_args[1]
        assert "Custom success message" in call_args["message"]

    def test_check_api_connectivity_unauthorized(self, validator, report):
        """Test API connectivity with 401 Unauthorized."""
        mock_response = Mock()
        mock_response.status_code = 401

        with patch("requests.request", return_value=mock_response):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "401 Unauthorized" in call_args["message"]
        assert call_args["level"] == ValidationLevel.ERROR

    def test_check_api_connectivity_forbidden(self, validator, report):
        """Test API connectivity with 403 Forbidden."""
        mock_response = Mock()
        mock_response.status_code = 403

        with patch("requests.request", return_value=mock_response):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "403 Forbidden" in call_args["message"]

    def test_check_api_connectivity_other_error(self, validator, report):
        """Test API connectivity with other HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 500

        with patch("requests.request", return_value=mock_response):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "HTTP 500" in call_args["message"]

    def test_check_api_connectivity_timeout(self, validator, report):
        """Test API connectivity with timeout."""
        import requests

        with patch("requests.request", side_effect=requests.exceptions.Timeout):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "timeout" in call_args["message"].lower()

    def test_check_api_connectivity_connection_error(self, validator, report):
        """Test API connectivity with connection error."""
        import requests

        with patch(
            "requests.request",
            side_effect=requests.exceptions.ConnectionError("Connection refused"),
        ):
            result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "Connection failed" in call_args["message"]

    def test_check_api_connectivity_no_requests_library(self, validator, report):
        """Test API connectivity when requests library is not installed."""
        with patch.dict("sys.modules", {"requests": None}):
            # Import error will be raised when trying to import requests
            with patch("builtins.__import__", side_effect=ImportError):
                result = validator.check_api_connectivity(url="https://api.example.com/status")

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "requests library" in call_args["message"]

    def test_check_api_connectivity_with_auth(self, validator, report):
        """Test API connectivity with basic auth."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = validator.check_api_connectivity(
                url="https://api.example.com/status",
                auth=("user", "pass"),
            )

        assert result is True
        # Verify auth was passed to requests
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["auth"] == ("user", "pass")

    def test_check_api_connectivity_with_headers(self, validator, report):
        """Test API connectivity with custom headers."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("requests.request", return_value=mock_response) as mock_request:
            result = validator.check_api_connectivity(
                url="https://api.example.com/status",
                headers={"Authorization": "Bearer token"},
            )

        assert result is True
        # Verify headers were passed
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["headers"] == {"Authorization": "Bearer token"}

    def test_add_success_check(self, validator, report):
        """Test adding a success check."""
        validator.add_success_check(
            check_name="test_check",
            message="Everything is OK",
            details={"key": "value"},
        )

        report.add_check.assert_called_once_with(
            check_name="test_check",
            passed=True,
            message="Everything is OK",
            level=ValidationLevel.INFO,
            details={"key": "value"},
        )

    def test_add_error_check(self, validator, report):
        """Test adding an error check."""
        validator.add_error_check(
            check_name="test_check",
            message="Something went wrong",
            level=ValidationLevel.WARNING,
            details={"error": "details"},
        )

        report.add_check.assert_called_once_with(
            check_name="test_check",
            passed=False,
            message="Something went wrong",
            level=ValidationLevel.WARNING,
            details={"error": "details"},
        )

    def test_add_error_check_default_level(self, validator, report):
        """Test adding an error check with default level."""
        validator.add_error_check(
            check_name="test_check",
            message="Something went wrong",
        )

        call_args = report.add_check.call_args[1]
        assert call_args["level"] == ValidationLevel.ERROR

    def test_validate_resource_exists_success(self, validator, report):
        """Test resource validation when resource exists."""
        existing = {"template1", "template2", "template3"}

        result = validator.validate_resource_exists(
            resource_type="template",
            resource_name="template1",
            existing_resources=existing,
        )

        assert result is True
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is True
        assert "template1" in call_args["message"]

    def test_validate_resource_exists_with_parent(self, validator, report):
        """Test resource validation with parent context."""
        existing = {"vlan1", "vlan2"}

        result = validator.validate_resource_exists(
            resource_type="vlan",
            resource_name="vlan1",
            existing_resources=existing,
            parent_resource="firewall_rule_1",
        )

        assert result is True
        call_args = report.add_check.call_args[1]
        assert "firewall_rule_1" in call_args["message"]

    def test_validate_resource_not_found(self, validator, report):
        """Test resource validation when resource doesn't exist."""
        existing = {"template1", "template2"}

        result = validator.validate_resource_exists(
            resource_type="template",
            resource_name="missing_template",
            existing_resources=existing,
        )

        assert result is False
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "not found" in call_args["message"]
        assert call_args["details"]["resource_name"] == "missing_template"

    def test_validate_resource_not_found_with_parent(self, validator, report):
        """Test resource validation failure with parent context."""
        existing = {"alias1", "alias2"}

        result = validator.validate_resource_exists(
            resource_type="alias",
            resource_name="missing_alias",
            existing_resources=existing,
            parent_resource="firewall_rule_2",
        )

        assert result is False
        call_args = report.add_check.call_args[1]
        assert "firewall_rule_2" in call_args["message"]
        assert "not found" in call_args["message"]


class TestResourceValidatorSchema:
    """Tests for ResourceValidator schema checks."""

    def test_validate_schema_success(self):
        """Valid schema passes and records info-level success."""
        report = Mock(spec=ValidationReport)
        rv = ResourceValidator("test", report)

        result = rv.validate_schema(
            resource={"name": "vm1", "cpu": 2},
            schema={"type": dict, "required": ["name", "cpu"]},
            check_name="schema_vm",
        )

        assert result is True
        report.add_check.assert_called_once()
        args = report.add_check.call_args[1]
        assert args["passed"] is True
        assert args["level"] == ValidationLevel.INFO

    def test_validate_schema_missing_field(self):
        """Missing fields are reported as errors."""
        report = Mock(spec=ValidationReport)
        rv = ResourceValidator("test", report)

        result = rv.validate_schema(
            resource={"name": "vm1"},
            schema={"type": dict, "required": ["name", "cpu"]},
            check_name="schema_vm",
        )

        assert result is False
        args = report.add_check.call_args[1]
        assert args["passed"] is False
        assert "cpu" in args["message"]
        assert args["level"] == ValidationLevel.ERROR

    def test_validate_schema_type_mismatch(self):
        """Type mismatches are reported as errors."""
        report = Mock(spec=ValidationReport)
        rv = ResourceValidator("test", report)

        result = rv.validate_schema(
            resource=["not a dict"],
            schema={"type": dict, "required": ["name"]},
            check_name="schema_vm",
        )

        assert result is False
        args = report.add_check.call_args[1]
        assert args["passed"] is False
        assert "Invalid type" in args["message"]
        assert args["level"] == ValidationLevel.ERROR
