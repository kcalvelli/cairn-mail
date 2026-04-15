# Development Guide

Guide for setting up and contributing to cairn-mail.

## Table of Contents

- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Backend Development](#backend-development)
- [Frontend Development](#frontend-development)
- [Database Migrations](#database-migrations)
- [Testing](#testing)
- [Building & Packaging](#building--packaging)
- [Adding a New Provider](#adding-a-new-provider)

---

## Development Environment

### Prerequisites

- **Nix** with flakes enabled
- **Ollama** for AI classification testing
- **Node.js 20+** (provided by nix develop)
- **Python 3.11+** (provided by nix develop)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/kcalvelli/cairn-mail
cd cairn-mail

# Enter development shell
nix develop

# Start backend
python -m cairn_mail.api.main

# In another terminal, start frontend
cd web
npm install
npm run dev
```

### Development Shell

The `nix develop` shell provides:
- Python 3.11 with all dependencies
- Node.js 20 with npm
- Development tools (black, ruff, mypy, pytest)
- Database tools (alembic, sqlite3)

```bash
nix develop

# Available commands:
python --version   # Python 3.11.x
node --version     # v20.x.x
npm --version      # 10.x.x
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `~/.local/share/cairn-mail/mail.db` | SQLite database path |
| `CONFIG_PATH` | `~/.config/cairn-mail/config.yaml` | Runtime config path |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Project Structure

```
cairn-mail/
├── src/cairn_mail/           # Python backend
│   ├── api/                     # FastAPI application
│   │   ├── main.py             # App entry point
│   │   ├── routes/             # API route handlers
│   │   └── websocket.py        # WebSocket manager
│   ├── db/                      # Database layer
│   │   ├── database.py         # SQLAlchemy setup
│   │   ├── models.py           # ORM models
│   │   └── queries.py          # Query functions
│   ├── providers/               # Email providers
│   │   ├── base.py             # Abstract base class
│   │   ├── factory.py          # Provider factory
│   │   ├── registry.py         # Provider registry
│   │   └── implementations/    # Gmail, IMAP, etc.
│   ├── config/                  # Configuration
│   │   └── loader.py           # Config file loader
│   ├── cli/                     # CLI commands
│   │   ├── main.py             # CLI entry point
│   │   ├── sync.py             # Sync command
│   │   └── auth.py             # Auth commands
│   ├── ai_classifier.py         # LLM integration
│   ├── sync_engine.py           # Sync orchestration
│   └── credentials.py           # Credential handling
├── web/                         # React frontend
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── hooks/              # Custom hooks
│   │   ├── api/                # API client (cairn)
│   │   ├── store/              # Zustand state
│   │   └── pages/              # Page components
│   ├── public/                  # Static assets
│   └── package.json
├── modules/                     # Nix modules
│   └── home-manager/           # Home Manager module
├── alembic/                     # Database migrations
│   ├── versions/               # Migration scripts
│   └── alembic.ini
├── tests/                       # Test suites
├── docs/                        # Documentation
├── flake.nix                    # Nix flake
└── pyproject.toml               # Python project config
```

---

## Backend Development

### Running the API Server

```bash
# Development mode (auto-reload)
nix develop
uvicorn cairn_mail.api.main:app --reload --port 8080

# Or using the module
python -m cairn_mail.api.main
```

API available at http://localhost:8080

### API Documentation

FastAPI auto-generates OpenAPI docs:
- **Swagger UI:** http://localhost:8080/docs
- **ReDoc:** http://localhost:8080/redoc
- **OpenAPI JSON:** http://localhost:8080/openapi.json

### Code Style

```bash
# Format code
black src/
ruff check src/ --fix

# Type checking
mypy src/cairn_mail

# All checks
black src/ && ruff check src/ && mypy src/
```

### Adding API Endpoints

1. Create route handler in `src/cairn_mail/api/routes/`
2. Register router in `src/cairn_mail/api/main.py`
3. Add tests in `tests/api/`

Example:

```python
# src/cairn_mail/api/routes/example.py
from fastapi import APIRouter, Depends
from ..dependencies import get_db

router = APIRouter(prefix="/example", tags=["example"])

@router.get("/")
async def list_examples(db=Depends(get_db)):
    return {"examples": []}
```

```python
# src/cairn_mail/api/main.py
from .routes import example
app.include_router(example.router)
```

---

## Frontend Development

### Running the Dev Server

```bash
cd web
npm install
npm run dev
```

Frontend available at http://localhost:5173 (proxies API to 8080)

### Build for Production

```bash
npm run build
# Output in web/dist/
```

### Component Structure

Components follow this pattern:

```typescript
// src/components/ExampleComponent.tsx
import { Box, Typography } from '@mui/material';
import { useExampleQuery } from '../hooks/useExampleQuery';

interface ExampleComponentProps {
  id: string;
}

export function ExampleComponent({ id }: ExampleComponentProps) {
  const { data, isLoading, error } = useExampleQuery(id);

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">{error.message}</Alert>;

  return (
    <Box>
      <Typography>{data?.name}</Typography>
    </Box>
  );
}
```

### State Management

Using Zustand for global state:

```typescript
// src/store/appStore.ts
import { create } from 'zustand';

interface AppState {
  selectedFolder: string;
  setSelectedFolder: (folder: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedFolder: 'INBOX',
  setSelectedFolder: (folder) => set({ selectedFolder: folder }),
}));
```

### API Hooks

Using React Query for data fetching:

```typescript
// src/hooks/useMessages.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { messagesApi } from '../api/messages';

export function useMessages(folder: string) {
  return useQuery({
    queryKey: ['messages', folder],
    queryFn: () => messagesApi.list(folder),
  });
}

export function useDeleteMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: messagesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['messages'] });
    },
  });
}
```

---

## Database Migrations

### Running Migrations

```bash
# Apply all migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history
```

### Creating Migrations

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "Add new column"

# Manual migration
alembic revision -m "Custom migration"
```

### Migration Best Practices

1. Test migrations on a copy of production data
2. Include both upgrade and downgrade functions
3. Use batch operations for large tables
4. Add indexes in separate migrations

Example migration:

```python
# alembic/versions/xxx_add_priority_column.py
def upgrade():
    op.add_column('messages',
        sa.Column('priority', sa.String(20), nullable=True))

def downgrade():
    op.drop_column('messages', 'priority')
```

---

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src/cairn_mail --cov-report=html

# Specific test file
pytest tests/api/test_messages.py

# Verbose output
pytest -v
```

### Test Structure

```
tests/
├── api/                  # API endpoint tests
│   ├── test_messages.py
│   └── test_sync.py
├── providers/            # Provider tests
│   ├── test_gmail.py
│   └── test_imap.py
├── config/               # Config tests
│   └── test_loader.py
├── conftest.py           # Shared fixtures
└── __init__.py
```

### Writing Tests

```python
# tests/api/test_messages.py
import pytest
from fastapi.testclient import TestClient
from cairn_mail.api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_list_messages(client):
    response = client.get("/api/messages")
    assert response.status_code == 200
    assert "messages" in response.json()

def test_delete_message(client, test_message):
    response = client.delete(f"/api/messages/{test_message.id}")
    assert response.status_code == 200
```

---

## Building & Packaging

### Nix Build

```bash
# Build the package
nix build

# Run from build output
./result/bin/cairn-mail --help

# Build specific outputs
nix build .#cairn-mail-web  # Frontend only
```

### Development Build

```bash
# Python package (editable)
pip install -e .

# Frontend build
cd web && npm run build
```

### Docker (Optional)

```bash
# Build image
docker build -t cairn-mail .

# Run container
docker run -p 8080:8080 cairn-mail
```

---

## Adding a New Provider

To add support for a new email provider:

### 1. Create Provider Class

```python
# src/cairn_mail/providers/implementations/outlook.py
from dataclasses import dataclass
from ..base import BaseEmailProvider, ProviderConfig

@dataclass
class OutlookConfig(ProviderConfig):
    """Outlook-specific configuration."""
    tenant_id: str = "common"

class OutlookProvider(BaseEmailProvider):
    """Microsoft Outlook/Office365 provider."""

    def __init__(self, config: OutlookConfig):
        super().__init__(config)
        self.config = config

    def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API."""
        # Implementation here
        pass

    def fetch_messages(self, folder: str, max_results: int = 100):
        """Fetch messages from Outlook."""
        # Implementation here
        pass

    def update_labels(self, message_id: str, labels: list[str]) -> bool:
        """Update message categories."""
        # Implementation here
        pass
```

### 2. Register Provider

```python
# src/cairn_mail/providers/__init__.py
from .implementations.outlook import OutlookProvider
from .registry import ProviderRegistry

ProviderRegistry.register("outlook", OutlookProvider)
```

### 3. Update Factory

```python
# src/cairn_mail/providers/factory.py
elif account.provider == "outlook":
    config = OutlookConfig(
        account_id=account.id,
        email=account.email,
        credential_file=account.settings.get("credential_file", ""),
    )
    return ProviderRegistry.get_provider("outlook", config)
```

### 4. Add Nix Module Options

```nix
# modules/home-manager/default.nix
provider = mkOption {
  type = types.enum [ "gmail" "imap" "outlook" ];  # Add here
  ...
};
```

### 5. Add Auth Wizard

```python
# src/cairn_mail/cli/auth.py
@auth.command()
@click.option("--account", required=True)
def outlook(account: str):
    """Set up Outlook OAuth authentication."""
    # Implementation here
    pass
```

### 6. Write Tests

```python
# tests/providers/test_outlook.py
import pytest
from cairn_mail.providers.implementations.outlook import OutlookProvider

def test_outlook_authentication():
    # Test implementation
    pass
```

### 7. Update Documentation

- Add to `docs/QUICKSTART.md`
- Add to `docs/CONFIGURATION.md`
- Update README provider list

---

## Debugging Tips

### Backend Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or per-module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
```

### Frontend Debugging

```typescript
// React Query Devtools
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';

// Add to App.tsx
<ReactQueryDevtools initialIsOpen={false} />
```

### Database Inspection

```bash
# SQLite CLI
sqlite3 ~/.local/share/cairn-mail/mail.db

# Useful queries
.tables
.schema messages
SELECT COUNT(*) FROM messages;
SELECT * FROM messages LIMIT 5;
```

### API Request Logging

```bash
# Enable verbose logging
LOG_LEVEL=DEBUG python -m cairn_mail.api.main
```
