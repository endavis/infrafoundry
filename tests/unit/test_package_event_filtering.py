"""Tests for package-level and resource-owner event filtering (#427, #442).

When --package is specified, only event handlers from that package should fire.
Handlers from other packages should be skipped.

When _resource_owner is set on a handler, it should only fire when that
specific resource is in the target_resources list, preventing cross-provider
false positives for resources with the same name.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from infrafoundry.core.config.package_loader import PackageLoader
from infrafoundry.core.events import EventContext, EventType, UnifiedEventBus
from infrafoundry.core.events.handlers.base import BaseHandler

# --- BaseHandler.matches_package() ---


class TestMatchesPackage:
    """Tests for BaseHandler.matches_package()."""

    def test_no_filter_returns_true(self) -> None:
        """No package_filter means all handlers fire."""
        handler = _make_handler(package="minio")
        assert handler.matches_package(None) is True

    def test_no_package_on_handler_returns_true(self) -> None:
        """Handler without _package fires regardless of filter."""
        handler = _make_handler(package=None)
        assert handler.matches_package("k3s-cluster") is True

    def test_matching_package_returns_true(self) -> None:
        """Handler fires when its package matches the filter."""
        handler = _make_handler(package="k3s-cluster")
        assert handler.matches_package("k3s-cluster") is True

    def test_different_package_returns_false(self) -> None:
        """Handler is skipped when its package differs from the filter."""
        handler = _make_handler(package="minio")
        assert handler.matches_package("k3s-cluster") is False


# --- Package tagging in PackageLoader ---


class TestPackageTagging:
    """Tests for _package tagging in PackageLoader.load_package()."""

    def test_load_package_tags_handlers(self, tmp_path: Path) -> None:
        """load_package() adds _package field to each handler config."""
        env_dir = tmp_path / "test-env"
        provider_dir = env_dir / "kubernetes"
        pkg_dir = provider_dir / "k3s-cluster"
        pkg_dir.mkdir(parents=True)

        # Create manifest with events
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: k3s-cluster\n"
            "resources:\n  - vm.yaml\n"
            "events:\n"
            "  after_apply:\n"
            "    - type: script\n"
            "      name: setup-k3s\n"
            "      script: scripts/setup.sh\n"
            "    - type: script\n"
            "      name: deploy-apps\n"
            "      script: scripts/deploy.sh\n"
        )
        (pkg_dir / "vm.yaml").write_text("vm:\n  - name: k3s-node\n    cores: 4\n")

        loader = PackageLoader(base_dir=tmp_path)
        _resources, events, _variables = loader.load_package(pkg_dir, "kubernetes", "test-env")

        # All handlers should have _package set
        assert "after_apply" in events
        for handler in events["after_apply"]:
            assert handler["_package"] == "k3s-cluster"

    def test_load_package_tags_multiple_event_types(self, tmp_path: Path) -> None:
        """_package is set across all event types."""
        env_dir = tmp_path / "test-env"
        provider_dir = env_dir / "proxmox"
        pkg_dir = provider_dir / "minio"
        pkg_dir.mkdir(parents=True)

        (pkg_dir / "infrafoundry.yml").write_text(
            "name: minio\n"
            "resources:\n  - vm.yaml\n"
            "events:\n"
            "  before_plan:\n"
            "    - type: script\n"
            "      name: pre-check\n"
            "      script: scripts/check.sh\n"
            "  after_apply:\n"
            "    - type: script\n"
            "      name: configure-minio\n"
            "      script: scripts/configure.sh\n"
        )
        (pkg_dir / "vm.yaml").write_text("vm:\n  - name: minio-srv\n    cores: 2\n")

        loader = PackageLoader(base_dir=tmp_path)
        _resources, events, _variables = loader.load_package(pkg_dir, "proxmox", "test-env")

        for event_key, handlers in events.items():
            for handler in handlers:
                assert handler["_package"] == "minio", f"Handler in {event_key} missing _package"


# --- Event bus integration ---


class TestEventBusPackageFiltering:
    """Integration tests for package filtering in UnifiedEventBus.emit()."""

    def test_filter_skips_other_package_handlers(self) -> None:
        """emit() with package_filter skips handlers from other packages."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "k3s-cluster"},
        )
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "minio"},
        )

        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            package_filter="k3s-cluster",
        )
        # Both handlers will fail to execute (dummy module), but we can check
        # how many were attempted by examining the results count
        results = bus.emit(ctx, abort_on_failure=False)
        # Only the k3s-cluster handler should have been attempted
        assert len(results) == 1

    def test_no_filter_fires_all_handlers(self) -> None:
        """emit() without package_filter fires all handlers."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "k3s-cluster"},
        )
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "minio"},
        )

        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            # No package_filter
        )
        results = bus.emit(ctx, abort_on_failure=False)
        assert len(results) == 2

    def test_handler_without_package_always_fires(self) -> None:
        """Handlers without _package fire regardless of filter."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler"},
        )
        bus.register_handler(
            EventType.AFTER_APPLY,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "minio"},
        )

        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            package_filter="k3s-cluster",
        )
        results = bus.emit(ctx, abort_on_failure=False)
        # The handler without _package fires; the minio handler does not
        assert len(results) == 1

    def test_emit_event_passes_package_filter(self) -> None:
        """emit_event() convenience method passes package_filter to context."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.BEFORE_PLAN,
            {"type": "python", "module": "dummy", "function": "handler", "_package": "minio"},
        )

        results = bus.emit_event(
            EventType.BEFORE_PLAN,
            "prod",
            package_filter="k3s-cluster",
        )
        # minio handler should be skipped
        assert len(results) == 0


# --- BaseHandler.matches_resources() with _resource_owner (#442) ---


class TestResourceOwnerScoping:
    """Tests for _resource_owner scoping in BaseHandler.matches_resources()."""

    def test_no_owner_no_targets_returns_true(self) -> None:
        """Handler without _resource_owner fires when no target filter."""
        handler = _make_handler_with_owner(resource_owner=None)
        assert handler.matches_resources(None) is True

    def test_no_owner_with_targets_returns_true(self) -> None:
        """Handler without _resource_owner defers to existing logic."""
        handler = _make_handler_with_owner(resource_owner=None)
        # No resources/requires config, so returns True for any targets
        assert handler.matches_resources(["web-server"]) is True

    def test_owner_matches_target(self) -> None:
        """Handler fires when its _resource_owner is in target_resources."""
        handler = _make_handler_with_owner(resource_owner="web-server")
        assert handler.matches_resources(["web-server", "db-server"]) is True

    def test_owner_does_not_match_target(self) -> None:
        """Handler is skipped when _resource_owner is not in target_resources."""
        handler = _make_handler_with_owner(resource_owner="web-server")
        assert handler.matches_resources(["db-server"]) is False

    def test_owner_with_no_target_filter(self) -> None:
        """Handler fires when target_resources is None (no -r flag)."""
        handler = _make_handler_with_owner(resource_owner="web-server")
        assert handler.matches_resources(None) is True

    def test_same_name_different_owner_blocked(self) -> None:
        """Two handlers with different _resource_owner values are scoped correctly.

        This is the core bug from #442: a DHCP reservation handler with
        _resource_owner="web-server" should NOT fire when the target is
        a VM also named "web-server" from a different provider.
        """
        vm_handler = _make_handler_with_owner(resource_owner="web-server")
        dhcp_handler = _make_handler_with_owner(resource_owner="web-server-dhcp")

        # When VM "web-server" is the target, only vm_handler fires
        assert vm_handler.matches_resources(["web-server"]) is True
        assert dhcp_handler.matches_resources(["web-server"]) is False

    def test_owner_with_resources_config_still_checks_owner_first(self) -> None:
        """_resource_owner check takes precedence over resources config."""
        handler = _make_handler_with_owner(
            resource_owner="web-server",
            resources=["web-server", "db-server"],
        )
        # Owner is "web-server" but target only has "db-server" — blocked
        assert handler.matches_resources(["db-server"]) is False


# --- BaseHandler.is_resource_scoped property (#539) ---


class TestIsResourceScoped:
    """Tests for BaseHandler.is_resource_scoped property."""

    def test_handler_with_resource_owner_is_scoped(self) -> None:
        """Handler with _resource_owner is resource-scoped."""
        handler = _make_handler_with_owner(resource_owner="web-server")
        assert handler.is_resource_scoped is True

    def test_handler_without_resource_owner_is_not_scoped(self) -> None:
        """Handler without _resource_owner is not resource-scoped."""
        handler = _make_handler_with_owner(resource_owner=None)
        assert handler.is_resource_scoped is False

    def test_package_level_handler_is_not_scoped(self) -> None:
        """Package-level handler (with _package but no _resource_owner) is not scoped."""
        handler = _make_handler(package="k3s-cluster")
        assert handler.is_resource_scoped is False


# --- resource_scoped emit (#539) ---


class TestResourceScopedEmit:
    """Tests for resource_scoped parameter in UnifiedEventBus.emit()."""

    def test_resource_scoped_skips_package_level_handler(self) -> None:
        """emit() with resource_scoped=True skips handlers without _resource_owner."""
        bus = UnifiedEventBus()
        # Package-level handler with requires (the bug scenario)
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "pkg-handler",
                "requires": ["aiqum"],
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["aiqum"],
        )
        results = bus.emit(ctx, abort_on_failure=False, resource_scoped=True)
        assert len(results) == 0

    def test_resource_scoped_fires_resource_level_handler(self) -> None:
        """emit() with resource_scoped=True fires handlers with _resource_owner."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "res-handler",
                "_resource_owner": "aiqum",
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["aiqum"],
        )
        results = bus.emit(ctx, abort_on_failure=False, resource_scoped=True)
        assert len(results) == 1

    def test_non_resource_scoped_fires_all(self) -> None:
        """emit() without resource_scoped fires both package and resource handlers."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "pkg-handler",
                "requires": ["aiqum"],
            },
        )
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "res-handler",
                "_resource_owner": "aiqum",
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["aiqum"],
        )
        results = bus.emit(ctx, abort_on_failure=False, resource_scoped=False)
        assert len(results) == 2

    def test_emit_event_passes_resource_scoped(self) -> None:
        """emit_event() convenience method passes resource_scoped to emit()."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "pkg-handler",
                "requires": ["aiqum"],
            },
        )

        results = bus.emit_event(
            EventType.RESOURCE_CREATED,
            "prod",
            {"action": "create"},
            resource_scoped=True,
            target_resources=["aiqum"],
        )
        assert len(results) == 0

    def test_resource_scoped_mixed_handlers(self) -> None:
        """resource_scoped=True: only resource-level handler fires, not package-level.

        This is the exact scenario from issue #539: a package-level on_create
        handler with requires: ["aiqum"] should NOT fire when a DHCP
        reservation named "aiqum" triggers a per-resource RESOURCE_CREATED event.
        """
        bus = UnifiedEventBus()
        # Package-level handler (no _resource_owner) — should be skipped
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "pkg-on-create",
                "requires": ["aiqum"],
            },
        )
        # Resource-level handler (has _resource_owner) — should fire
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "res-on-create",
                "_resource_owner": "aiqum",
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["opnsense:aiqum", "aiqum"],
        )
        results = bus.emit(ctx, abort_on_failure=False, resource_scoped=True)
        assert len(results) == 1


class TestEventBusResourceOwnerFiltering:
    """Integration tests for _resource_owner filtering in UnifiedEventBus.emit()."""

    def test_owner_scoped_handler_skipped_for_other_resource(self) -> None:
        """Handler with _resource_owner is skipped when target doesn't match."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "_resource_owner": "web-server",
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["db-server"],
        )
        results = bus.emit(ctx, abort_on_failure=False)
        assert len(results) == 0

    def test_owner_scoped_handler_fires_for_matching_resource(self) -> None:
        """Handler with _resource_owner fires when target matches."""
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "_resource_owner": "web-server",
            },
        )

        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["web-server"],
        )
        results = bus.emit(ctx, abort_on_failure=False)
        assert len(results) == 1

    def test_mixed_owner_and_unowned_handlers(self) -> None:
        """Unowned handlers fire for any target; owned handlers are scoped."""
        bus = UnifiedEventBus()
        # Owned handler — only fires for "web-server"
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "_resource_owner": "web-server",
                "name": "vm-setup",
            },
        )
        # Unowned handler — fires for anything
        bus.register_handler(
            EventType.RESOURCE_CREATED,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "name": "global-notify",
            },
        )

        # Target is "db-server" — only unowned handler fires
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="prod",
            target_resources=["db-server"],
        )
        results = bus.emit(ctx, abort_on_failure=False)
        assert len(results) == 1


# --- Helpers ---


class _StubHandler(BaseHandler):
    """Minimal concrete handler for unit testing matches_package()."""

    def execute(self, context: EventContext) -> Any:
        return MagicMock(success=True)

    def validate_config(self) -> list[str]:
        return []


def _make_handler(package: str | None) -> _StubHandler:
    """Create a handler with the given _package value."""
    config: dict[str, Any] = {"name": "test-handler"}
    if package is not None:
        config["_package"] = package
    return _StubHandler(config)


def _make_handler_with_owner(
    resource_owner: str | None,
    resources: list[str] | None = None,
    package: str | None = None,
) -> _StubHandler:
    """Create a handler with optional _resource_owner and resources config."""
    config: dict[str, Any] = {"name": "test-handler"}
    if resource_owner is not None:
        config["_resource_owner"] = resource_owner
    if resources is not None:
        config["resources"] = resources
    if package is not None:
        config["_package"] = package
    return _StubHandler(config)


def _make_scoped_handler(
    package: str | None = "pkg-a",
    package_resources: list[str] | None = None,
    package_providers: list[str] | None = None,
    **extra: Any,
) -> _StubHandler:
    """Create a handler tagged with package scope the way PackageLoader does."""
    config: dict[str, Any] = {"name": "scoped-handler", **extra}
    if package is not None:
        config["_package"] = package
    if package_resources is not None:
        config["_package_resources"] = package_resources
    if package_providers is not None:
        config["_package_providers"] = package_providers
    return _StubHandler(config)


class TestPackageResourceScoping:
    """Package-level handlers run only for operations covering their resources."""

    def test_skipped_when_target_excludes_package_resources(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"])
        assert handler.matches_resources(["node-a"]) is False

    def test_fires_when_target_includes_package_resource(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"])
        assert handler.matches_resources(["pkg-a-vm", "node-a"]) is True

    def test_fires_for_whole_environment(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"])
        assert handler.matches_resources(None) is True

    def test_untagged_handler_unaffected(self) -> None:
        handler = _make_scoped_handler(package=None)
        assert handler.matches_resources(["node-a"]) is True

    def test_explicit_resources_keep_semantics(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"], resources=["node-a"])
        assert handler.matches_resources(["node-a"]) is True
        assert handler.matches_resources(["other"]) is False

    def test_explicit_requires_keep_semantics(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"], requires=["node-a"])
        assert handler.matches_resources(["node-a"]) is True
        assert handler.matches_resources(["pkg-a-vm"]) is False


class TestPackageProviderScoping:
    """Package-level handlers run only for operations covering their providers."""

    def test_skipped_when_provider_not_targeted(self) -> None:
        handler = _make_scoped_handler(package_providers=["oci"])
        assert handler.matches_providers(["aws"]) is False

    def test_fires_when_provider_targeted(self) -> None:
        handler = _make_scoped_handler(package_providers=["oci"])
        assert handler.matches_providers(["oci"]) is True
        assert handler.matches_providers(["aws", "oci"]) is True

    def test_fires_without_provider_filter(self) -> None:
        handler = _make_scoped_handler(package_providers=["oci"])
        assert handler.matches_providers(None) is True

    def test_handler_without_providers_always_fires(self) -> None:
        handler = _make_scoped_handler(package=None)
        assert handler.matches_providers(["aws"]) is True


class TestMatchesScope:
    """BaseHandler.matches_scope combines -p, -r and -P."""

    def test_environment_handler_fires_under_every_filter(self) -> None:
        handler = _make_scoped_handler(package=None)
        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            target_resources=["node-a"],
            package_filter="pkg-b",
            provider_filter=["aws"],
        )
        assert handler.matches_scope(ctx) is True

    def test_package_filter_selects_own_package_only(self) -> None:
        pkg_a = _make_scoped_handler(package="pkg-a", package_resources=["pkg-a-vm"])
        pkg_b = _make_scoped_handler(package="pkg-b", package_resources=["pkg-b-vm"])
        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            target_resources=["pkg-a-vm"],
            package_filter="pkg-a",
        )
        assert pkg_a.matches_scope(ctx) is True
        assert pkg_b.matches_scope(ctx) is False

    def test_all_filters_must_match(self) -> None:
        handler = _make_scoped_handler(package_resources=["pkg-a-vm"], package_providers=["oci"])
        ctx = EventContext(
            event_type=EventType.AFTER_APPLY,
            environment="prod",
            target_resources=["pkg-a-vm"],
            provider_filter=["aws"],
        )
        assert handler.matches_scope(ctx) is False


class TestEventBusProviderScoping:
    """UnifiedEventBus.emit honours provider_filter and package resource scope."""

    @staticmethod
    def _bus(**tags: Any) -> UnifiedEventBus:
        bus = UnifiedEventBus()
        bus.register_handler(
            EventType.BEFORE_DESTROY,
            {
                "type": "python",
                "module": "dummy",
                "function": "handler",
                "_package": "pkg-a",
                **tags,
            },
        )
        return bus

    def test_provider_filter_skips_other_provider_package(self) -> None:
        bus = self._bus(_package_providers=["oci"])
        ctx = EventContext(
            event_type=EventType.BEFORE_DESTROY, environment="prod", provider_filter=["aws"]
        )
        assert bus.emit(ctx, abort_on_failure=False) == []

    def test_provider_filter_runs_matching_package(self) -> None:
        bus = self._bus(_package_providers=["oci"])
        ctx = EventContext(
            event_type=EventType.BEFORE_DESTROY, environment="prod", provider_filter=["oci"]
        )
        assert len(bus.emit(ctx, abort_on_failure=False)) == 1

    def test_resource_filter_skips_package_handler(self) -> None:
        bus = self._bus(_package_resources=["pkg-a-vm"])
        ctx = EventContext(
            event_type=EventType.BEFORE_DESTROY, environment="prod", target_resources=["node-a"]
        )
        assert bus.emit(ctx, abort_on_failure=False) == []

    def test_whole_environment_runs_package_handler(self) -> None:
        bus = self._bus(_package_resources=["pkg-a-vm"], _package_providers=["oci"])
        ctx = EventContext(event_type=EventType.BEFORE_DESTROY, environment="prod")
        assert len(bus.emit(ctx, abort_on_failure=False)) == 1

    def test_aggregate_emit_fires_each_package_for_its_own_group(self) -> None:
        bus = UnifiedEventBus()
        for pkg, res in (("pkg-a", "pkg-a-vm"), ("pkg-b", "pkg-b-vm")):
            bus.register_handler(
                EventType.BEFORE_DESTROY,
                {
                    "type": "python",
                    "module": "dummy",
                    "function": "handler",
                    "name": f"{pkg}-handler",
                    "_package": pkg,
                    "_package_resources": [res],
                },
            )
        ctx = EventContext(
            event_type=EventType.BEFORE_DESTROY,
            environment="prod",
            target_resources=["pkg-a-vm"],
        )
        results = bus.emit(ctx, abort_on_failure=False)
        assert [r.handler_name for r in results] == ["pkg-a-handler"]

    def test_emit_event_passes_provider_filter_into_context(self) -> None:
        bus = UnifiedEventBus()
        seen: list[EventContext] = []
        bus.emit = lambda context, **_kw: seen.append(context) or []  # type: ignore[method-assign,func-returns-value]
        bus.emit_event(EventType.BEFORE_APPLY, "prod", provider_filter=["aws"])
        assert seen[0].provider_filter == ["aws"]


class TestPackageScopeTagging:
    """PackageLoader tags package-level handlers with resources and providers."""

    def _load(self, tmp_path: Path, resources: bool = True) -> dict[str, list[dict[str, Any]]]:
        pkg_dir = tmp_path / "test-env" / "proxmox" / "pkg-a"
        pkg_dir.mkdir(parents=True)
        manifest = "name: pkg-a\n"
        if resources:
            manifest += "resources:\n  - vm.yaml\n"
        manifest += (
            "events:\n  after_apply:\n    - type: script\n      name: h\n"
            "      script: scripts/h.sh\n"
        )
        (pkg_dir / "infrafoundry.yml").write_text(manifest)
        if resources:
            (pkg_dir / "vm.yaml").write_text("vm:\n  - name: node-a\n    cores: 2\n")
        loader = PackageLoader(base_dir=tmp_path)
        _res, events, _vars = loader.load_package(pkg_dir, "proxmox", "test-env")
        return events

    def test_tags_resources_and_providers(self, tmp_path: Path) -> None:
        handler = self._load(tmp_path)["after_apply"][0]
        assert handler["_package_resources"] == ["node-a"]
        assert handler["_package_providers"] == ["proxmox"]

    def test_package_without_resources_gets_manifest_provider(self, tmp_path: Path) -> None:
        handler = self._load(tmp_path, resources=False)["after_apply"][0]
        assert handler["_package_resources"] == []
        assert handler["_package_providers"] == ["proxmox"]
