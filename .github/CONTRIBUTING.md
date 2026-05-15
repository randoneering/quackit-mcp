# Contributing to quackit

Thank you for your interest in contributing to **quackit** — local-first session memory for coding agents, backed by DuckDB or Postgres.

This project is community-driven, and contributions of all kinds are welcome: new features, bug fixes, documentation improvements, tests, and ideas.

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/3/0/code_of_conduct/). By participating, you agree to uphold a welcoming and inclusive environment.

## Getting Started

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Development Setup

1. Fork and clone the repository:

   ```bash
   git clone https://github.com/randoneering/quackit-mcp.git
   cd quackit-mcp
   ```

2. Install dependencies with `uv`:

   ```bash
   uv sync
   ```

   This creates a virtual environment and installs all project dependencies (including dev dependencies for testing and linting).

3. Verify the setup:

   ```bash
   uv run ruff check
   uv run pytest
   ```

### Running the Server

```bash
uv run quackit
```

Set `QUACKIT_STORAGE_MODE=duckdb` (default) or `QUACKIT_STORAGE_MODE=postgres` to choose your backend. See the README for configuration details.

## Conventional Commits

This project enforces [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/). Every commit message must use the following format:

```
<type>[optional scope]: <description>

[optional body]
[optional footer(s)]
```

### Types

| Type       | Usage                                    | Quackit example                                      |
|------------|------------------------------------------|------------------------------------------------------|
| `feat`     | A new feature                            | `feat(session): add session tagging support`         |
| `fix`      | A bug fix                                | `fix(storage): handle empty DuckDB result sets`      |
| `chore`    | Maintenance, tooling, dependencies       | `chore(deps): bump fastmcp to 2.14.0`                |
| `docs`     | Documentation changes                    | `docs: add migration guide for Postgres backend`     |
| `test`     | Adding or fixing tests                   | `test(memory): add unit tests for recall queries`    |
| `refactor` | Code restructuring (no behavior change)  | `refactor(server): extract tool registration`        |
| `style`    | Formatting, linting (no logic change)    | `style: apply ruff format to storage module`         |
| `perf`     | Performance improvement                  | `perf(session): batch memory insert in DuckDB`       |
| `ci`       | CI/CD configuration                      | `ci: add pytest workflow for DuckDB and Postgres`    |
| `build`    | Build system or packaging                | `build: migrate from setuptools to hatchling`        |
| `revert`   | Reverting a previous change              | `revert: restore old session serialization format`   |

### Scopes

The optional scope should reference the module or area of change:

- `session` — session lifecycle and management
- `memory` — memory creation, recall, and storage
- `project` — project-level operations
- `skill` — skill registration and execution
- `storage` — DuckDB/Postgres storage backends
- `server` — MCP server setup and tool registration
- `cli` — command-line interface
- `config` — configuration loading and validation
- `auth` — authentication and access control
- `deps` — dependency updates
- `release` — release preparation

### Examples

```
feat(memory): add recall by temporal range
fix(storage): close dangling Postgres connections on error
docs: add quickstart tutorial for DuckDB backend
test(project): verify project creation with duplicate slug
refactor(server): extract tool registration into registry module
chore(deps): update duckdb to 1.3.1
```

## Branch Naming

Branches should follow the pattern `type/description`, where `type` is one of the following:

| Branch prefix    | When to use                                    |
|------------------|-------------------------------------------------|
| `feat/`          | New features                                   |
| `feature/`       | New features (alternative to `feat/`)           |
| `fix/`           | Bug fixes                                      |
| `chore/`         | Maintenance tasks, dependency updates           |
| `doc/`           | Documentation changes                          |
| `docs/`          | Documentation changes (alternative to `doc/`)   |
| `test/`          | Adding or fixing tests                         |
| `refactor/`      | Code restructuring without behavior changes     |

Examples:

```
feat/duckdb-tag-filters
fix/postgres-connection-pool-race
docs/update-readme-with-env-vars
test/memory-recall-edge-cases
refactor/server-tool-registration
```

## Pull Request Process

1. Create a branch following the naming convention above:

   ```bash
   git checkout -b feat/my-feature
   ```

2. Make your changes. Keep commits focused and follow Conventional Commits.

3. Run the linter and tests before committing:

   ```bash
   uv run ruff check
   uv run ruff format --check
   uv run pytest
   ```

4. Push your branch and open a pull request against `main`. Use the PR template — it will guide you through the required information.

5. Ensure CI passes. The project runs `ruff check` and `pytest` on every pull request.

6. At least one maintainer must approve before merging.

7. Squash-merge is preferred to keep the commit history clean. The final squashed commit message should follow Conventional Commits format.

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest

# Run only unit tests (no database required)
uv run pytest tests/unit/

# Run integration tests (requires DuckDB and/or Postgres)
uv run pytest tests/integration/

# Run tests with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/unit/test_session.py
```

### Test Structure

- **`tests/unit/`** — Unit tests that mock storage backends and test business logic in isolation. No live database required.
- **`tests/integration/`** — Integration tests that exercise the full stack against real DuckDB and Postgres instances.
- **`tests/conftest.py`** — Shared fixtures and configuration for test infrastructure.

### Test Markers

The project uses pytest markers to categorize tests:

```bash
# Run only DuckDB-backed tests
uv run pytest -m duckdb

# Run only Postgres-backed tests
uv run pytest -m postgres

# Run slow tests (integration-heavy)
uv run pytest -m slow
```

See `pyproject.toml` for the full marker definitions.

### Linting and Formatting

This project uses [ruff](https://docs.astral.sh/ruff/) for both linting and formatting:

```bash
# Check for linting issues
uv run ruff check

# Auto-fix linting issues
uv run ruff check --fix

# Check formatting
uv run ruff format --check

# Format code
uv run ruff format
```

Run `ruff check` and `ruff format --check` before every commit. CI will block PRs that fail either check.

## Questions?

Open an [issue](https://github.com/randoneering/quackit-mcp/issues) or reach out through the channels listed in the README.

---

Thank you for considering being a contributor to this tool! 
