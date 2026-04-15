# Contributing to cairn-mail

Thank you for your interest in contributing to cairn-mail! This document provides guidelines and information for contributors.

## Code of Ethics

This project follows a [Code of Ethics](CODE_OF_ETHICS.md) rooted in principles of mutual respect, patience, and dignity. Please read it before contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Set up the development environment:**
   ```bash
   nix develop
   ```
4. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for detailed setup instructions.

## Development Workflow

### OpenSpec Workflow

For significant features or architectural changes, we use the OpenSpec workflow:

1. **Create a proposal** in `openspec/changes/<change-id>/`
2. **Document the change** with `proposal.md`, `tasks.md`, and spec deltas
3. **Validate** with `openspec validate <change-id> --strict`
4. **Get approval** before implementing
5. **Implement** following the approved tasks

For smaller changes (bug fixes, minor improvements), you can skip OpenSpec and go directly to implementation.

### When to Use OpenSpec

Use OpenSpec for:
- New features or capabilities
- Breaking changes to the API
- Architectural modifications
- Changes affecting multiple components

Skip OpenSpec for:
- Bug fixes
- Documentation updates
- Dependency updates
- Minor UI tweaks

## Code Style

### Python

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Format with Black and check with Ruff:
  ```bash
  black src/
  ruff check src/ --fix
  ```

### TypeScript/React

- Use TypeScript strict mode
- Follow ESLint rules (included in project)
- Use functional components with hooks
- Format with Prettier:
  ```bash
  cd web && npm run lint
  ```

### Commit Messages

We use conventional commits:

```
type(scope): description

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, semicolons, etc.)
- `refactor`: Code refactoring
- `test`: Adding or modifying tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(api): add bulk delete endpoint
fix(sync): handle expired OAuth tokens gracefully
docs: update QUICKSTART with IMAP instructions
refactor(providers): extract common auth logic
```

### Branch Naming

Use descriptive branch names:
- `feature/add-outlook-provider`
- `fix/gmail-sync-timeout`
- `docs/update-configuration-guide`
- `refactor/provider-abstraction`

## Pull Request Process

1. **Ensure all tests pass:**
   ```bash
   pytest
   cd web && npm run test
   ```

2. **Update documentation** if your change affects user-facing features

3. **Fill out the PR template** with:
   - Summary of changes
   - Related issues
   - Testing performed
   - Screenshots (for UI changes)

4. **Request review** from maintainers

5. **Address feedback** and update your branch as needed

6. **Squash commits** if requested before merge

### PR Title Format

Follow the same format as commit messages:
```
feat(component): Brief description of change
```

## Testing

### Running Tests

```bash
# Python tests
pytest

# With coverage
pytest --cov=src/cairn_mail

# Frontend tests
cd web && npm run test
```

### Writing Tests

- Add tests for new features
- Update tests for modified behavior
- Aim for meaningful coverage, not just high numbers

### Test Organization

```
tests/
├── api/           # API endpoint tests
├── providers/     # Provider implementation tests
├── config/        # Configuration tests
└── conftest.py    # Shared fixtures
```

## Documentation

### When to Update Docs

Update documentation when you:
- Add new features
- Change configuration options
- Modify API endpoints
- Change user-facing behavior

### Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Project overview, quick start |
| `docs/QUICKSTART.md` | Getting started guide |
| `docs/USER_GUIDE.md` | Complete user documentation |
| `docs/CONFIGURATION.md` | Nix option reference |
| `docs/DEVELOPMENT.md` | Developer setup guide |
| `docs/ARCHITECTURE.md` | Technical deep-dive |

## Reporting Issues

### Bug Reports

Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- System information (NixOS version, browser, etc.)
- Relevant logs

### Feature Requests

Include:
- Use case description
- Proposed solution (if any)
- Alternatives considered

## Questions?

- Open a GitHub Discussion for general questions
- Open an Issue for bugs or feature requests
- Check existing issues and discussions before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to cairn-mail!
