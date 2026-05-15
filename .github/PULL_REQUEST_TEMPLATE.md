## Description

<!-- Describe what this pull request changes and why. Be specific about the problem it solves and the approach taken. -->

Closes #<!-- issue number -->

## Type of Change

<!-- Check the type that applies. Keep the squashed commit message aligned with this selection. -->

- [ ] **feat** — A new feature (adds functionality)
- [ ] **fix** — A bug fix
- [ ] **docs** — Documentation changes (README, API docs, comments)
- [ ] **refactor** — Code restructuring with no behavior change
- [ ] **test** — Adding or fixing tests
- [ ] **style** — Formatting, linting (no logic change)
- [ ] **perf** — Performance improvement
- [ ] **chore** — Maintenance, tooling, dependencies
- [ ] **ci** — CI/CD configuration
- [ ] **build** — Build system or packaging
- [ ] **revert** — Reverts a previous change

## Related Issue

<!-- Link to the GitHub issue this PR addresses, if any. Use "Closes #N" to auto-close. -->

## Checklist

<!-- All items must be checked before requesting review. Run the commands as shown. -->

- [ ] Linter passes: `uv run ruff check`
- [ ] Formatting is correct: `uv run ruff format --check`
- [ ] All tests pass: `uv run pytest`
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`type(scope): description`)
- [ ] Branch name follows conventions (`type/description`, e.g., `feat/duckdb-tag-filters`)
- [ ] Updated README or other documentation if the change affects usage or configuration

## Testing

<!-- Describe what you tested and against which storage backends. -->

- [ ] Tested with **DuckDB** (default backend)
- [ ] Tested with **Postgres**
- [ ] Tested with **both** DuckDB and Postgres
- [ ] Only unit tests (no database backend required)

**Test details**:

<!-- What did you test? Edge cases? Existing test additions? Manual testing steps? -->

```

<!-- Paste relevant test output or coverage summary here -->

```

## Additional Context

<!-- Anything else reviewers should know: design decisions, gotchas, migration notes, performance implications, etc. -->
