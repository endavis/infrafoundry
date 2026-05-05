"""Unit tests for ``AliasManager``.

Coverage:
    - ``migrate`` delegates to ``AliasService.export_to_yaml``.
    - ``migrate`` instantiates the service via ``from_environment``
      with the right ``(env_name, provider_name, config_dir)`` triple.
    - Default ``provider_name`` is ``"opnsense"``; non-default is
      threaded through unchanged.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from infrafoundry.providers.opnsense.components.alias import AliasManager

SERVICE_PATH = "infrafoundry.providers.opnsense.components.alias.AliasService"


class TestMigrate:
    def test_migrate_delegates_to_export_to_yaml(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("test-env")

        assert result == "resources: []\n"
        service_mock.export_to_yaml.assert_called_once_with()
        svc_cls.from_environment.assert_called_once_with("test-env", "opnsense", tmp_path)

    def test_migrate_passes_provider_name_through(self, tmp_path: Path) -> None:
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        service_mock.export_to_yaml.return_value = "resources: []\n"
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            manager.migrate("test-env", provider_name="alt-provider")

        svc_cls.from_environment.assert_called_once_with("test-env", "alt-provider", tmp_path)

    def test_migrate_returns_yaml_verbatim(self, tmp_path: Path) -> None:
        # The manager is a thin pass-through; whatever the service emits
        # is what the operator gets — no transformation.
        manager = AliasManager(tmp_path)
        service_mock = MagicMock()
        payload = "resources:\n- provider: opnsense\n  type: aliases\n  name: web\n"
        service_mock.export_to_yaml.return_value = payload
        with patch(SERVICE_PATH) as svc_cls:
            svc_cls.from_environment.return_value = service_mock
            result = manager.migrate("env")
        assert result == payload
