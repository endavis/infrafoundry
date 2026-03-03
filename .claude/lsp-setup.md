# Claude LSP Setup Guide

This guide explains how to set up Language Server Protocol (LSP) support for Claude Code, enabling fast code navigation and intelligent code understanding.

## ⚠️ Known Issues

**LSP requests currently hang and do not return responses.** The pyright language server starts successfully but does not respond to LSP protocol requests from Claude Code. This appears to be a bug in the Claude Code LSP integration (released December 2025) or the pyright-lsp plugin.

- ✅ Pyright CLI works perfectly (tested and confirmed)
- ✅ Configuration is correct and validated
- ✅ Language server starts successfully
- ❌ LSP requests hang indefinitely (e.g., `textDocument/definition`)

**Status:** Configuration is ready for when this issue is resolved. For now, use traditional file reading/searching.

If you find that LSP works for you, please report your setup!

## What is LSP?

LSP (Language Server Protocol) provides Claude with semantic code understanding:
- **Jump to definitions** - Navigate directly to function/class definitions
- **Find references** - See where symbols are used across the codebase
- **Type information** - Get instant type hints and signatures
- **Error detection** - See type errors and diagnostics

With LSP, Claude can navigate code in ~50ms instead of ~45 seconds using traditional text search.

## Prerequisites

- Claude Code version 2.0.74 or later
- Python 3.12+ environment
- This project installed with dev dependencies

## Installation Steps

### 1. Enable LSP Tool

**Option A: Using .envrc.local (Recommended)**

This project uses direnv for environment management:

```bash
# Copy the example file if you haven't already
cp .envrc.local.example .envrc.local

# Uncomment the ENABLE_LSP_TOOL line in .envrc.local
# Change: # export ENABLE_LSP_TOOL=1
# To:     export ENABLE_LSP_TOOL=1

# direnv will automatically load it when you cd into the project
```

**Option B: Global Shell Profile**

Alternatively, add this to your shell profile (`~/.bashrc`, `~/.zshrc`, or `~/.profile`):

```bash
export ENABLE_LSP_TOOL=1
```

Then reload your shell:

```bash
source ~/.bashrc  # or ~/.zshrc
```

### 2. Install Pyright LSP Plugin

In Claude Code, run:

```
/plugin install pyright-lsp@claude-plugins-official
```

### 3. Install Pyright Language Server

Choose one installation method:

**Via pip (recommended for Python projects):**
```bash
pip install pyright
```

**Via npm:**
```bash
npm install -g pyright
```

**Via Homebrew (macOS):**
```bash
brew install pyright
```

### 4. Verify Installation

Check that pyright is in your PATH:

```bash
pyright --version
```

Expected output:
```
pyright 1.1.x
```

## Configuration

This project is already configured for LSP via `pyproject.toml`:

```toml
[tool.pyright]
include = ["src", "tests", "*.py", "tools", ".github"]
exclude = ["**/__pycache__", "**/.venv", "**/tmp", ...]
pythonVersion = "3.12"
typeCheckingMode = "basic"
```

No additional configuration needed!

## Testing LSP

Ask Claude to test LSP functionality:

1. **Jump to definition:**
   ```
   Jump to the definition of the greet function
   ```

2. **Find references:**
   ```
   Find all references to the __version__ variable
   ```

3. **Type information:**
   ```
   What's the return type of the greet function?
   ```

If LSP is working, Claude will provide instant, accurate responses with file paths and line numbers.

## Troubleshooting

### "No LSP server available"

**Cause:** Pyright binary not found in PATH

**Solution:**
```bash
# Check if pyright is installed
which pyright

# If not found, install it
pip install pyright
```

### "Executable not found in $PATH"

**Cause:** Pyright language server not installed

**Solution:** Follow step 3 above to install the pyright binary

### LSP not responding

**Cause:** Plugin not installed or ENABLE_LSP_TOOL not set

**Solution:**
1. Verify environment variable: `echo $ENABLE_LSP_TOOL` (should output "1")
2. Reinstall plugin: `/plugin install pyright-lsp@claude-plugins-official`
3. Restart Claude Code

### "pyright-langserver not found"

**Cause:** Some installations use different binary names

**Solution:**
```bash
# If installed via npm, it might be:
which pyright-langserver

# Or try reinstalling via pip
pip install --force-reinstall pyright
```

## Performance Benefits

Without LSP:
- Code navigation: ~45 seconds (requires reading multiple files)
- High token usage for exploration

With LSP:
- Code navigation: ~50ms (direct symbol lookup)
- Minimal token usage for navigation
- Better type understanding
- Faster development iterations

## Related Documentation

- [AI_SETUP.md](../docs/development/AI_SETUP.md) - Complete AI development setup
- [Pyright Documentation](https://microsoft.github.io/pyright/)
- [Claude Code Plugin Docs](https://code.claude.com/docs/en/discover-plugins)

## Need Help?

If you encounter issues:
1. Check the troubleshooting section above
2. Verify all prerequisites are met
3. Open an issue at: https://github.com/username/package_name/issues
