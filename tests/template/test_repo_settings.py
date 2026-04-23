"""Tests for repo_settings.py repository settings functionality."""

from __future__ import annotations

from unittest.mock import patch


class TestConfigureRepositorySettings:
    """Tests for configure_repository_settings function."""

    def test_configure_repository_settings_success(self) -> None:
        """Test successful repository settings configuration."""
        from tools.pyproject_template.repo_settings import configure_repository_settings

        mock_template_settings = {
            "description": "Template description",
            "has_issues": True,
            "has_wiki": False,
            "allow_squash_merge": True,
            # Read-only fields that should be filtered
            "id": 123,
            "node_id": "abc",
            "full_name": "old/name",
        }

        mock_owner_info = {"type": "User"}

        with (
            patch(
                "tools.pyproject_template.repo_settings.GitHubCLI.api",
                side_effect=[mock_template_settings, mock_owner_info, None],
            ) as mock_api,
        ):
            result = configure_repository_settings(
                repo_full="user/repo",
                description="New description",
                visibility="public",
            )

            assert result is True
            # Verify API was called correctly
            assert mock_api.call_count == 3

    def test_configure_repository_settings_failure(self) -> None:
        """Test repository settings configuration handles failure."""
        from subprocess import CalledProcessError

        from tools.pyproject_template.repo_settings import configure_repository_settings

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            side_effect=CalledProcessError(1, "gh", stderr="Error"),
        ):
            result = configure_repository_settings(
                repo_full="user/repo",
                description="Description",
            )

            assert result is False


class TestConfigureBranchProtection:
    """Tests for configure_branch_protection function."""

    def test_configure_branch_protection_creates_new_ruleset(self) -> None:
        """Test creating a new ruleset when none exists."""
        from tools.pyproject_template.repo_settings import configure_branch_protection

        mock_template_rulesets = [{"id": 1, "name": "main-protection"}]
        mock_existing_rulesets: list[dict[str, object]] = []  # No existing rulesets
        mock_full_ruleset = {
            "id": 1,
            "name": "main-protection",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {},
            "rules": [],
        }

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            side_effect=[
                mock_template_rulesets,  # GET template rulesets
                mock_existing_rulesets,  # GET existing rulesets in target repo
                mock_full_ruleset,  # GET full ruleset details
                None,  # POST new ruleset
            ],
        ) as mock_api:
            result = configure_branch_protection(repo_full="user/repo")
            assert result is True
            # Verify POST was used (4th call)
            assert mock_api.call_count == 4
            last_call = mock_api.call_args_list[3]
            assert last_call.kwargs.get("method") == "POST"
            assert "rulesets" in last_call.args[0]
            assert "rulesets/" not in last_call.args[0]  # No ID in URL for POST

    def test_configure_branch_protection_updates_existing_ruleset(self) -> None:
        """Test updating an existing ruleset instead of creating a duplicate."""
        from tools.pyproject_template.repo_settings import configure_branch_protection

        mock_template_rulesets = [{"id": 1, "name": "main-protection"}]
        mock_existing_rulesets = [{"id": 99, "name": "main-protection"}]  # Already exists
        mock_full_ruleset = {
            "id": 1,
            "name": "main-protection",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {},
            "rules": [],
        }

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            side_effect=[
                mock_template_rulesets,  # GET template rulesets
                mock_existing_rulesets,  # GET existing rulesets in target repo
                mock_full_ruleset,  # GET full ruleset details
                None,  # PUT existing ruleset
            ],
        ) as mock_api:
            result = configure_branch_protection(repo_full="user/repo")
            assert result is True
            # Verify PUT was used with correct ID (4th call)
            assert mock_api.call_count == 4
            last_call = mock_api.call_args_list[3]
            assert last_call.kwargs.get("method") == "PUT"
            assert "rulesets/99" in last_call.args[0]  # Uses existing ID

    def test_configure_branch_protection_no_rulesets(self) -> None:
        """Test branch protection when template has no rulesets."""
        from tools.pyproject_template.repo_settings import configure_branch_protection

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            return_value=[],
        ):
            result = configure_branch_protection(repo_full="user/repo")
            assert result is True  # No rulesets is not a failure


class TestReplicateLabels:
    """Tests for replicate_labels function."""

    def test_replicate_labels_success(self) -> None:
        """Test successful label replication."""
        from tools.pyproject_template.repo_settings import replicate_labels

        mock_labels = [
            {"name": "bug", "color": "d73a4a", "description": "Bug report"},
            {"name": "enhancement", "color": "a2eeef", "description": "New feature"},
        ]

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            side_effect=[mock_labels, None, None],
        ):
            result = replicate_labels(repo_full="user/repo")
            assert result is True

    def test_replicate_labels_empty(self) -> None:
        """Test label replication when template has no labels."""
        from tools.pyproject_template.repo_settings import replicate_labels

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            return_value=[],
        ):
            result = replicate_labels(repo_full="user/repo")
            assert result is False


class TestEnableGithubPages:
    """Tests for enable_github_pages function."""

    def test_enable_github_pages_success(self) -> None:
        """Test successful GitHub Pages enablement."""
        from tools.pyproject_template.repo_settings import enable_github_pages

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            return_value=None,
        ):
            result = enable_github_pages(repo_full="user/repo")
            assert result is True

    def test_enable_github_pages_no_branch(self) -> None:
        """Test GitHub Pages when gh-pages branch doesn't exist."""
        from subprocess import CalledProcessError

        from tools.pyproject_template.repo_settings import enable_github_pages

        with patch(
            "tools.pyproject_template.repo_settings.GitHubCLI.api",
            side_effect=CalledProcessError(1, "gh"),
        ):
            result = enable_github_pages(repo_full="user/repo")
            assert result is False


class TestUpdateAllRepoSettings:
    """Tests for update_all_repo_settings convenience function.

    CodeQL scanning is intentionally NOT part of this orchestration: it runs
    from the committed ``.github/workflows/codeql.yml`` workflow file that
    the template generator copies into every new repository. See issue #431
    for the migration from the default-setup API to the workflow file.
    """

    def test_update_all_repo_settings_success(self) -> None:
        """Test that update_all_repo_settings calls all configuration functions."""
        from tools.pyproject_template.repo_settings import update_all_repo_settings

        with (
            patch(
                "tools.pyproject_template.repo_settings.configure_repository_settings",
                return_value=True,
            ) as mock_repo,
            patch(
                "tools.pyproject_template.repo_settings.configure_branch_protection",
                return_value=True,
            ) as mock_branch,
            patch(
                "tools.pyproject_template.repo_settings.replicate_labels",
                return_value=True,
            ) as mock_labels,
            patch(
                "tools.pyproject_template.repo_settings.enable_github_pages",
                return_value=True,
            ) as mock_pages,
        ):
            result = update_all_repo_settings(
                repo_full="user/repo",
                description="Description",
            )

            assert result is True
            mock_repo.assert_called_once()
            mock_branch.assert_called_once()
            mock_labels.assert_called_once()
            mock_pages.assert_called_once()

    def test_update_all_repo_settings_partial_failure(self) -> None:
        """Test that update_all_repo_settings returns False if any step fails."""
        from tools.pyproject_template.repo_settings import update_all_repo_settings

        with (
            patch(
                "tools.pyproject_template.repo_settings.configure_repository_settings",
                return_value=True,
            ),
            patch(
                "tools.pyproject_template.repo_settings.configure_branch_protection",
                return_value=False,  # This one fails
            ),
            patch(
                "tools.pyproject_template.repo_settings.replicate_labels",
                return_value=True,
            ),
            patch(
                "tools.pyproject_template.repo_settings.enable_github_pages",
                return_value=True,
            ),
        ):
            result = update_all_repo_settings(
                repo_full="user/repo",
                description="Description",
            )

            assert result is False
