# Development Setup - FIXED ✅

## What Changed

Fixed the development environment to properly support `pip install -e .` by adding `venvShellHook`.

## How to Use

### 1. Enter Development Environment

```bash
cd /home/keith/Projects/cairn-mail
nix develop
```

**What happens automatically:**
- Creates Python virtual environment in `./.venv`
- Activates the venv
- Runs `pip install -e .[dev]` to install package in editable mode
- Installs all dev dependencies (pytest, black, ruff, mypy, etc.)
- Shows welcome message with available commands

### 2. The Package is Now Available

```bash
# CLI is automatically available
cairn-mail --help
cairn-mail --version

# Python package is importable
python3 -c "from cairn_mail import __version__; print(__version__)"
```

### 3. Make Changes and Test

Since the package is installed in editable mode (`-e`), any changes you make to the code are immediately available:

```python
# Edit src/cairn_mail/ai_classifier.py
# Changes are immediately reflected without reinstalling

# Test your changes
python3 -c "from cairn_mail.ai_classifier import AIClassifier; print('OK')"
```

### 4. Code Quality Tools

All tools are pre-installed in the venv:

```bash
# Format code
black src/cairn_mail

# Lint
ruff check src/cairn_mail

# Type check
mypy src/cairn_mail

# Run tests (when we write them)
pytest tests/

# Interactive Python REPL with all dependencies
ipython
```

## Key Files Updated

1. **`flake.nix`**
   - Added `venvShellHook` for proper virtual environment
   - Added `pip` to packages
   - Added `postVenvCreation` hook to auto-install package
   - Added nice welcome message with instructions

2. **`.gitignore`**
   - Ignores `.venv/` directory
   - Standard Python ignores (__pycache__, *.pyc, etc.)
   - Project-specific ignores (*.db, *.log)

3. **`pyproject.toml`**
   - Added `ipython` to dev dependencies
   - Added `all` extras group for convenience

## Troubleshooting

### Virtual environment not activating

```bash
# Exit and re-enter the dev shell
exit
nix develop
```

### Package not found after changes

```bash
# Reinstall in editable mode (usually not needed)
pip install -e .[dev]
```

### Old .venv conflicts

```bash
# Remove old venv and recreate
rm -rf .venv
exit
nix develop
```

## What's in the Virtual Environment

```bash
# Check what's installed
pip list

# Should include:
# - cairn-mail (editable)
# - All runtime dependencies (pydantic, sqlalchemy, etc.)
# - All dev dependencies (pytest, black, ruff, mypy)
```

## Testing the Setup

```bash
# Quick smoke test
python3 << 'EOF'
from cairn_mail.db.database import Database
from cairn_mail.credentials import Credentials
from cairn_mail.ai_classifier import AIClassifier, AIConfig
from cairn_mail.providers.base import BaseEmailProvider
print("✅ All imports successful!")
print(f"✅ Package installed: cairn-mail")
EOF

# Test CLI
cairn-mail --help
echo "✅ CLI working!"
```

## Next Steps

1. ✅ Dev environment is ready
2. 📝 See `QUICKSTART.md` for first-time OAuth setup
3. 🧪 See `IMPLEMENTATION.md` for testing instructions
4. 📖 See `PHASE1_COMPLETE.md` for architecture overview

## Additional Development Commands

### Building the Package

```bash
# Build with Nix (creates result/ symlink)
nix build

# Run from Nix build
./result/bin/cairn-mail --help

# Run as flake app
nix run . -- --help
```

### Testing Individual Components

```bash
# Test database
python3 -c "from cairn_mail.db.database import Database; db = Database('/tmp/test.db'); accounts = db.list_accounts(); print(f'✅ Database OK ({len(accounts)} accounts)')"

# Test credentials (requires a token file)
python3 -c "from cairn_mail.credentials import Credentials; import os; print('✅ Credentials module OK')"

# Test AI classifier (requires Ollama running)
python3 -c "from cairn_mail.ai_classifier import AIClassifier; print('✅ AI Classifier module OK')"
```

### Interactive Development

```bash
# Start IPython with all modules loaded
ipython

# Then in IPython:
from cairn_mail.db.database import Database
from cairn_mail.providers.implementations.gmail import GmailProvider, GmailConfig
from cairn_mail.ai_classifier import AIClassifier, AIConfig
from cairn_mail.sync_engine import SyncEngine

# Now you can interactively test components!
```

## Environment Details

- **Python Version**: 3.11
- **Virtual Environment**: `./.venv` (auto-created)
- **Editable Install**: Changes to `src/` are immediately reflected
- **Dependencies**: All installed from `pyproject.toml`
- **Tools**: black, ruff, mypy, pytest, ipython

Enjoy developing! 🚀
