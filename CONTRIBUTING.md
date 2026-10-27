# Contributing

`holo` lives in [`hai-agents-python`](https://github.com/hcompai/hai-agents-python). Open CLI issues and PRs there.

This repo holds only the `holo-desktop-cli` package metadata, and the installers in `install/`.

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
