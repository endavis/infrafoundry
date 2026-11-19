"""Unit tests for the 'migrate' CLI command."""

import warnings
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.exceptions import PartialExtractionError
from infrafoundry.core.orchestrator import Orchestrator


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


@pytest.fixture
def mock_orchestrator() -> Mock:
    """Mock orchestrator for testing."""
    mock = Mock(spec=Orchestrator)
    mock.providers = {}
    return mock


@pytest.fixture
def real_opnsense_provider(tmp_path: Path) -> Any:
    """Concrete OPNsense provider instance.

    Instantiating populates the extractor registry as a side effect, so
    tests that exercise the registry-driven CLI dispatch pick up
    ``"opnsense"`` and its 10 components automatically.
    """
    from infrafoundry.providers.opnsense import OPNsenseProvider

    return OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)


@pytest.fixture
def mock_opnsense_provider(real_opnsense_provider: Any) -> Mock:
    """Mock OPNsense provider whose presence triggers registry population.

    The real provider is instantiated alongside the mock so the registry
    is populated, but CLI migrate dispatch goes through the registry —
    not the provider mock — so the mock's ``migrate_*`` methods are
    only relevant for the deprecated-shim back-compat tests.
    """
    del real_opnsense_provider  # required for its registry-population side effect

    from infrafoundry.providers.opnsense import OPNsenseProvider

    mock = Mock(spec=OPNsenseProvider)
    mock.migrate_kea_dhcp.return_value = "# Migrated Kea DHCP config\ndhcp: []"
    mock.migrate_isc_to_kea.return_value = "# Migrated ISC to Kea config\ndhcp: []"
    return mock


def test_migrate_kea_dhcp(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test migrate command for Kea DHCP via the extractor registry."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-kea_dhcp.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# Kea DHCP YAML\ndhcp: []"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea_dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Migration complete!" in result.output
        assert output_file.exists()
        fake_extractor.extract.assert_called_once_with("test")


def test_migrate_isc_to_kea(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test migrate command for ISC to Kea DHCP via the extractor registry."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-isc_to_kea.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# ISC->Kea YAML\ndhcp: []"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "isc_to_kea",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Migration complete!" in result.output
        assert output_file.exists()
        fake_extractor.extract.assert_called_once_with("test")


def test_migrate_with_interfaces(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test migrate command with specific interfaces.

    The CLI must convert click's ``tuple[str, ...]`` to a ``list[str]``
    and forward via ``kwargs={"interfaces": [...]}`` to the extractor.
    """
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-interfaces.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML\nx: y"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "isc_to_kea",
                "-i",
                "lan",
                "-i",
                "wan",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert output_file.exists()
        fake_extractor.extract.assert_called_once_with("test", interfaces=["lan", "wan"])


def test_migrate_vlans_via_registry(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test that the registry-driven path reaches new components.

    Before #726 this would have failed with ``Invalid value for '--component'``;
    after, the registry is the source of truth and ``vlans`` (one of the
    ten components OPNsense registers) becomes immediately reachable.
    """
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "migrated-vlans.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# VLANs YAML\nvlans: []"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "interfaces.vlans",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert output_file.exists()
        fake_extractor.extract.assert_called_once_with("test")


def test_migrate_with_dry_run(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test migrate command with dry-run flag."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "dry-run-output.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# Dry-run YAML\ndhcp: []"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea_dhcp",
                "--output",
                str(output_file),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Dry-run mode" in result.output
        assert "Generated configuration:" in result.output
        assert "Migration complete!" in result.output
        # In dry-run mode, file should not be created
        assert not output_file.exists()


def test_migrate_with_custom_output(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Test migrate command with custom output path."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "custom-output.yaml"

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML"

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea_dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0, result.output
        assert output_file.exists()
        assert "Configuration written to:" in result.output


def test_migrate_default_output_uses_snake_case_component(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Default output filename uses the snake-case component verbatim.

    Before #726 the default filename ran ``component.replace("/", "-")``
    which produced ``migrated-kea-dhcp.yaml``. With the breaking
    ``kea/dhcp`` → ``kea_dhcp`` rename the replace is gone — the filename
    is now ``migrated-kea_dhcp.yaml``.
    """
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML"

    config_dir = tmp_path / "config_dir"
    config_dir.mkdir()

    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=fake_extractor,
        ),
    ):
        result = cli_runner.invoke(
            main,
            [
                "-c",
                str(config_dir),
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea_dhcp",
            ],
        )

        assert result.exit_code == 0, result.output
        expected = config_dir / "envs" / "test" / "resources" / "migrated-kea_dhcp.yaml"
        assert expected.exists()


def test_migrate_provider_not_found(
    cli_runner: CliRunner, mock_orchestrator: Mock, tmp_path: Path
) -> None:
    """Test migrate command when provider is not loaded for the env.

    The registry knows ``opnsense`` because some prior fixture loaded it,
    but the (mocked) orchestrator's ``providers`` dict is empty for this
    env. The CLI must fail loudly rather than silently no-op.
    """
    # Trigger registry population so the provider name is registered.
    from infrafoundry.providers.opnsense import OPNsenseProvider

    OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    output_file = tmp_path / "should-not-exist.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea_dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code != 0
        assert "provider not found" in result.output.lower()
        assert not output_file.exists()


def test_migrate_unsupported_component_lists_registered(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """An unknown component fails with a message listing registered ones."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "should-not-exist.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "not_a_real_component",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code != 0
        # Helpful error: must list at least one of the registered components.
        # We assert ``vlans`` (a registered OPNsense component) appears in
        # the error rather than every name to keep the test robust to
        # additional registrations.
        assert "Unsupported component" in result.output
        assert "interfaces.vlans" in result.output
        assert not output_file.exists()


def test_migrate_unsupported_provider_lists_registered(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """An unknown provider fails with a message listing registered ones."""
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "should-not-exist.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "definitely_not_a_provider",
                "--component",
                "kea_dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code != 0
        assert "Unsupported provider" in result.output
        # ``opnsense`` must appear in the registered-providers list.
        assert "opnsense" in result.output
        assert not output_file.exists()


def test_provider_migrate_kea_dhcp_shim_emits_deprecation_warning(tmp_path: Path) -> None:
    """The deprecated ``migrate_kea_dhcp`` shim must warn and still work."""
    from infrafoundry.providers.opnsense import OPNsenseProvider

    provider = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML from extractor"

    # Patch the global ``get_extractor`` used by the shim.
    with (
        patch(
            "infrafoundry.core.extractors.get_extractor",
            return_value=fake_extractor,
        ),
        warnings.catch_warnings(record=True) as caught,
    ):
        warnings.simplefilter("always")
        result = provider.migrate_kea_dhcp("test_env")

    assert result == "# YAML from extractor"
    fake_extractor.extract.assert_called_once_with("test_env")
    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) >= 1
    assert "migrate_kea_dhcp" in str(deprecation_warnings[0].message)


def test_provider_migrate_isc_to_kea_shim_passes_interfaces(tmp_path: Path) -> None:
    """The deprecated ``migrate_isc_to_kea`` shim must forward ``interfaces``."""
    from infrafoundry.providers.opnsense import OPNsenseProvider

    provider = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML"

    with (
        patch(
            "infrafoundry.core.extractors.get_extractor",
            return_value=fake_extractor,
        ),
        warnings.catch_warnings(record=True) as caught,
    ):
        warnings.simplefilter("always")
        result = provider.migrate_isc_to_kea("test_env", ["lan", "wan"])

    assert result == "# YAML"
    fake_extractor.extract.assert_called_once_with("test_env", interfaces=["lan", "wan"])
    deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecation_warnings) >= 1


def test_provider_migrate_isc_to_kea_shim_no_interfaces(tmp_path: Path) -> None:
    """The shim must omit ``interfaces`` kwarg when no list is provided."""
    from infrafoundry.providers.opnsense import OPNsenseProvider

    provider = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)

    fake_extractor = MagicMock()
    fake_extractor.extract.return_value = "# YAML"

    with (
        patch(
            "infrafoundry.core.extractors.get_extractor",
            return_value=fake_extractor,
        ),
        warnings.catch_warnings(record=True),
    ):
        warnings.simplefilter("always")
        provider.migrate_isc_to_kea("test_env")

    # No ``interfaces`` kwarg when the caller didn't pass a list.
    fake_extractor.extract.assert_called_once_with("test_env")


def test_migrate_kea_dhcp_no_underscore_alias_for_legacy_name(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """Legacy ``kea/dhcp`` (with slash) must fail — no transparent alias.

    The breaking CLI rename is intentional. ``kea/dhcp`` is no longer a
    registered component, so the CLI must fail loudly rather than rewrite
    the slash form to an underscore.
    """
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    output_file = tmp_path / "should-not-exist.yaml"

    with patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator):
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "kea/dhcp",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code != 0
        assert "Unsupported component" in result.output
        # Path-style component must not be silently rewritten — the
        # operator gets a list of valid options including ``kea_dhcp``.
        assert "kea_dhcp" in result.output
        assert not output_file.exists()


# ---------------------------------------------------------------------------
# --include-legacy / --allow-partial (#1497)
# ---------------------------------------------------------------------------

_PARTIAL_ISSUES = ('rule #7 "Scheduled access": sched: has no counterpart', "rule #11: interface")
_PARTIAL_YAML = "# Legacy rule fields not exported \u2014 review before apply:\nopnsense: {}\n"


def _invoke_legacy(
    cli_runner: CliRunner,
    mock_orchestrator: Mock,
    mock_opnsense_provider: Mock,
    extractor: MagicMock,
    extra_args: list[str],
    *,
    component: str = "firewall.rules",
) -> Any:
    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(
            "infrafoundry.cli.commands.config.migrate.get_extractor",
            return_value=extractor,
        ),
    ):
        return cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                component,
                *extra_args,
            ],
        )


def _partial_extractor() -> MagicMock:
    extractor = MagicMock()
    extractor.extract.side_effect = PartialExtractionError(
        "partial", yaml_content=_PARTIAL_YAML, issues=_PARTIAL_ISSUES
    )
    return extractor


def test_include_legacy_forwards_the_option_only_when_set(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    out = tmp_path / "rules.yaml"
    plain = MagicMock()
    plain.extract.return_value = "a: b\n"
    result = _invoke_legacy(
        cli_runner, mock_orchestrator, mock_opnsense_provider, plain, ["-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    plain.extract.assert_called_once_with("test")

    legacy = MagicMock()
    legacy.extract.return_value = "a: b\n"
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        legacy,
        ["--include-legacy", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    legacy.extract.assert_called_once_with("test", include_legacy=True)


def test_include_legacy_clean_export_exits_zero_and_writes(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    out = tmp_path / "rules.yaml"
    extractor = MagicMock()
    extractor.extract.return_value = "opnsense: {}\n"
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        extractor,
        ["--include-legacy", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.read_text() == "opnsense: {}\n"


def test_partial_export_without_allow_partial_fails_and_writes_nothing(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    out = tmp_path / "rules.yaml"
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        _partial_extractor(),
        ["--include-legacy", "-o", str(out)],
    )
    assert result.exit_code == 1
    assert not out.exists()
    for issue in _PARTIAL_ISSUES:
        assert issue in result.output
    assert "--allow-partial" in result.output


def test_partial_export_with_allow_partial_writes_the_yaml_with_header(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    out = tmp_path / "rules.yaml"
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        _partial_extractor(),
        ["--include-legacy", "--allow-partial", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.read_text() == _PARTIAL_YAML
    for issue in _PARTIAL_ISSUES:
        assert issue in result.output


def test_partial_export_dry_run_without_allow_partial_fails(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    out = tmp_path / "rules.yaml"
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        _partial_extractor(),
        ["--include-legacy", "--dry-run", "-o", str(out)],
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_include_legacy_is_rejected_for_other_components(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    extractor = MagicMock()
    result = _invoke_legacy(
        cli_runner,
        mock_orchestrator,
        mock_opnsense_provider,
        extractor,
        ["--include-legacy", "-o", str(tmp_path / "x.yaml")],
        component="interfaces.vlans",
    )
    assert result.exit_code != 0
    assert "--include-legacy only applies" in result.output
    extractor.extract.assert_not_called()


def test_include_legacy_path_makes_no_write_calls(
    cli_runner: CliRunner, mock_orchestrator: Mock, mock_opnsense_provider: Mock, tmp_path: Path
) -> None:
    """End to end through the real extractor: only the search and the backup GET run."""
    from infrafoundry.providers.opnsense.services.config_backup import ConfigBackupService
    from infrafoundry.providers.opnsense.services.firewall_rule import FirewallRuleService

    clean = (
        Path(__file__).parent / "providers/opnsense/fixtures/legacy_filter_config_clean.xml"
    ).read_text()
    client = MagicMock()
    client.request.return_value = {"rows": []}
    client.get_text.return_value = clean
    service = FirewallRuleService(client)
    service._category_uuid = "marker-uuid"
    component = "infrafoundry.providers.opnsense.components.firewall_rule"
    out = tmp_path / "rules.yaml"

    mock_orchestrator.providers["opnsense"] = mock_opnsense_provider
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=mock_orchestrator),
        patch(f"{component}.FirewallRuleService") as svc_cls,
        patch(f"{component}.ConfigBackupService") as backup_cls,
        patch(f"{component}.env_provider_resources", return_value=[]),
    ):
        svc_cls.from_environment.return_value = service
        backup_cls.from_environment.return_value = ConfigBackupService(client)
        result = cli_runner.invoke(
            main,
            [
                "config",
                "migrate",
                "--env",
                "test",
                "--provider",
                "opnsense",
                "--component",
                "firewall.rules",
                "--include-legacy",
                "-o",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    assert "allow-web" in out.read_text()
    assert [c.args[0] for c in client.request.call_args_list] == ["POST"]
    client.get_text.assert_called_once_with("core/backup/download/this")
