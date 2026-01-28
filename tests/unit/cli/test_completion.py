"""Tests for shell completion commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from infrafoundry.cli.commands.completion import (
    BASH_SCRIPT,
    COMPLETION_MARKER,
    FISH_SCRIPT,
    ZSH_SCRIPT,
    _detect_shell,
    _find_config_file,
    _get_completion_script,
    _is_completion_installed,
    completion,
)


class TestDetectShell:
    """Tests for shell detection."""

    def test_detect_bash(self) -> None:
        """Should detect bash shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/bash"}):
            assert _detect_shell() == "bash"

    def test_detect_zsh(self) -> None:
        """Should detect zsh shell."""
        with patch.dict("os.environ", {"SHELL": "/usr/bin/zsh"}):
            assert _detect_shell() == "zsh"

    def test_detect_fish(self) -> None:
        """Should detect fish shell."""
        with patch.dict("os.environ", {"SHELL": "/usr/bin/fish"}):
            assert _detect_shell() == "fish"

    def test_detect_unknown(self) -> None:
        """Should return None for unknown shell."""
        with patch.dict("os.environ", {"SHELL": "/bin/sh"}):
            assert _detect_shell() is None

    def test_detect_no_shell_env(self) -> None:
        """Should return None when SHELL not set."""
        with patch.dict("os.environ", {}, clear=True):
            assert _detect_shell() is None


class TestGetCompletionScript:
    """Tests for getting completion scripts."""

    def test_get_bash_script(self) -> None:
        """Should return bash script."""
        script = _get_completion_script("bash")
        assert "bash" in script.lower()
        assert "_FOUNDRY_COMPLETE=bash_source" in script

    def test_get_zsh_script(self) -> None:
        """Should return zsh script."""
        script = _get_completion_script("zsh")
        assert "zsh" in script.lower()
        assert "_FOUNDRY_COMPLETE=zsh_source" in script

    def test_get_fish_script(self) -> None:
        """Should return fish script."""
        script = _get_completion_script("fish")
        assert "fish" in script.lower()
        assert "_FOUNDRY_COMPLETE=fish_source" in script

    def test_get_unknown_script(self) -> None:
        """Should return empty string for unknown shell."""
        assert _get_completion_script("unknown") == ""


class TestFindConfigFile:
    """Tests for finding config files."""

    def test_find_bash_config(self, tmp_path: Path) -> None:
        """Should find bash config file."""
        bashrc = tmp_path / ".bashrc"
        bashrc.touch()

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc]},
        ):
            assert _find_config_file("bash") == bashrc

    def test_find_zsh_config(self, tmp_path: Path) -> None:
        """Should find zsh config file."""
        zshrc = tmp_path / ".zshrc"
        zshrc.touch()

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"zsh": [zshrc]},
        ):
            assert _find_config_file("zsh") == zshrc

    def test_find_fish_config(self, tmp_path: Path) -> None:
        """Should return fish completions path (doesn't need to exist)."""
        fish_path = tmp_path / ".config" / "fish" / "completions" / "foundry.fish"

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"fish": [fish_path]},
        ):
            assert _find_config_file("fish") == fish_path

    def test_find_nonexistent_config(self, tmp_path: Path) -> None:
        """Should return None if no config exists."""
        nonexistent = tmp_path / ".nonexistent"

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [nonexistent]},
        ):
            assert _find_config_file("bash") is None


class TestIsCompletionInstalled:
    """Tests for checking if completion is installed."""

    def test_completion_installed(self, tmp_path: Path) -> None:
        """Should detect installed completion."""
        config_file = tmp_path / ".bashrc"
        config_file.write_text(f"some content\n{COMPLETION_MARKER}\nmore content")

        assert _is_completion_installed(config_file) is True

    def test_completion_not_installed(self, tmp_path: Path) -> None:
        """Should detect when completion is not installed."""
        config_file = tmp_path / ".bashrc"
        config_file.write_text("some content\nno completion here")

        assert _is_completion_installed(config_file) is False

    def test_file_not_exists(self, tmp_path: Path) -> None:
        """Should return False for nonexistent file."""
        config_file = tmp_path / ".nonexistent"

        assert _is_completion_installed(config_file) is False


class TestCompletionBashCommand:
    """Tests for 'foundry completion bash' command."""

    def test_installs_bash_completion(self, tmp_path: Path) -> None:
        """Should install bash completion to ~/.bashrc."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# existing content\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["bash"])

            assert result.exit_code == 0
            assert "installed" in result.output.lower()

            content = bashrc.read_text()
            assert COMPLETION_MARKER in content
            assert "_FOUNDRY_COMPLETE=bash_source" in content

    def test_already_installed(self, tmp_path: Path) -> None:
        """Should report when already installed."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text(f"# existing\n{BASH_SCRIPT}\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["bash"])

            assert result.exit_code == 0
            assert "already installed" in result.output.lower()


class TestCompletionZshCommand:
    """Tests for 'foundry completion zsh' command."""

    def test_installs_zsh_completion(self, tmp_path: Path) -> None:
        """Should install zsh completion to ~/.zshrc."""
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# existing content\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"zsh": [zshrc]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["zsh"])

            assert result.exit_code == 0
            assert "installed" in result.output.lower()

            content = zshrc.read_text()
            assert COMPLETION_MARKER in content
            assert "_FOUNDRY_COMPLETE=zsh_source" in content


class TestCompletionFishCommand:
    """Tests for 'foundry completion fish' command."""

    def test_installs_fish_completion(self, tmp_path: Path) -> None:
        """Should install fish completion (creates file)."""
        fish_path = tmp_path / "completions" / "foundry.fish"

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"fish": [fish_path]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["fish"])

            assert result.exit_code == 0
            assert fish_path.exists()
            assert "_FOUNDRY_COMPLETE=fish_source" in fish_path.read_text()


class TestCompletionUninstallCommand:
    """Tests for 'foundry completion uninstall' command."""

    def test_uninstall_single_shell(self, tmp_path: Path) -> None:
        """Should uninstall when only one shell has completion."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text(f"# before\n{BASH_SCRIPT}\n# after\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc], "zsh": [tmp_path / ".zshrc"], "fish": [tmp_path / "f.fish"]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["uninstall"])

            assert result.exit_code == 0
            assert "removed" in result.output.lower()

            content = bashrc.read_text()
            assert COMPLETION_MARKER not in content

    def test_uninstall_multiple_shells_select_one(self, tmp_path: Path) -> None:
        """Should prompt when multiple shells have completion."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text(f"# before\n{BASH_SCRIPT}\n")
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text(f"# before\n{ZSH_SCRIPT}\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc], "zsh": [zshrc], "fish": [tmp_path / "f.fish"]},
        ):
            runner = CliRunner()
            # Select option 1 (bash)
            result = runner.invoke(completion, ["uninstall"], input="1\n")

            assert result.exit_code == 0
            assert COMPLETION_MARKER not in bashrc.read_text()
            # zsh should still have it
            assert COMPLETION_MARKER in zshrc.read_text()

    def test_uninstall_multiple_shells_select_all(self, tmp_path: Path) -> None:
        """Should uninstall all when 'all' selected."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text(f"# before\n{BASH_SCRIPT}\n")
        zshrc = tmp_path / ".zshrc"
        zshrc.write_text(f"# before\n{ZSH_SCRIPT}\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc], "zsh": [zshrc], "fish": [tmp_path / "f.fish"]},
        ):
            runner = CliRunner()
            # Select option 3 (all) - bash=1, zsh=2, all=3
            result = runner.invoke(completion, ["uninstall"], input="3\n")

            assert result.exit_code == 0
            assert COMPLETION_MARKER not in bashrc.read_text()
            assert COMPLETION_MARKER not in zshrc.read_text()

    def test_uninstall_none_installed(self, tmp_path: Path) -> None:
        """Should handle when nothing is installed."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# no completion here\n")

        with patch(
            "infrafoundry.cli.commands.completion.SHELL_CONFIGS",
            {"bash": [bashrc], "zsh": [tmp_path / ".zshrc"], "fish": [tmp_path / "f.fish"]},
        ):
            runner = CliRunner()
            result = runner.invoke(completion, ["uninstall"])

            assert result.exit_code == 0
            assert "no shell completions" in result.output.lower()


class TestScriptContents:
    """Tests for script content correctness."""

    def test_bash_script_has_marker(self) -> None:
        """Bash script should have completion marker."""
        assert COMPLETION_MARKER in BASH_SCRIPT
        assert "bash_source" in BASH_SCRIPT

    def test_zsh_script_has_marker(self) -> None:
        """Zsh script should have completion marker."""
        assert COMPLETION_MARKER in ZSH_SCRIPT
        assert "zsh_source" in ZSH_SCRIPT

    def test_fish_script_has_marker(self) -> None:
        """Fish script should have completion marker."""
        assert COMPLETION_MARKER in FISH_SCRIPT
        assert "fish_source" in FISH_SCRIPT

    def test_scripts_use_foundry_command(self) -> None:
        """All scripts should reference 'foundry' command."""
        assert "foundry" in BASH_SCRIPT
        assert "foundry" in ZSH_SCRIPT
        assert "foundry" in FISH_SCRIPT
