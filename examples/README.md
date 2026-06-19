# Examples

Runnable examples built on [holo-desktop-cli](../README.md). Each example is its own [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) member: it resolves `holo-desktop-cli` from this checkout, has its own dependencies and tests, and is never packaged into the published `holo-desktop-cli` wheel.

| example | what it shows |
|---|---|
| [expense_report](expense_report/) | A deterministically verified multi-app demo: read receipts, fill a LibreOffice Calc ledger, start a Mail draft, and check the result. |
| [software_qa](software_qa/) | A Claude Code QA loop: edit a small React app, ask Holo to test the visible UI, fix the bug Holo reports, and verify again. |

## Running an example

```bash
make setup-examples       # from the repo root: installs holo-desktop-cli + every example
cd examples/<name>
uv run <example-command>  # see the example's own README
```

## Local development

Plain `uv sync` (and `make setup`) provisions only the root `holo-desktop-cli` package and will *uninstall* example-only dependencies from the shared `.venv`. To work on an example, either:

- run `make setup-examples` from the repo root (`uv sync --all-packages --all-groups`), or
- use `uv run` / `make` from inside `examples/<name>/`, which auto-syncs that member on demand.

## Adding a new example

1. Create `examples/<name>/` with the runnable demo files and a `README.md`.
2. For Python examples, add a local `pyproject.toml` and depend on holo-desktop-cli via the workspace:

   ```toml
   [project]
   dependencies = ["holo-desktop-cli", ...]

   [tool.uv.sources]
   holo-desktop-cli = { workspace = true }
   ```

3. Add Python example packages to `[tool.uv.workspace]` in the root `pyproject.toml`. Non-Python examples should keep their own package manager files inside their example directory.
